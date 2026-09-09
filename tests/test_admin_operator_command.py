"""Operator-facing tests for the administrator identity command."""

from __future__ import annotations

import base64
import re
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import jobs.manage_admin_operator as command
from db import Base
from services.admin_identity_service import (
    authenticate_operator,
    begin_operator_enrollment,
    confirm_operator_enrollment,
    totp_code,
)


MFA_KEY = base64.urlsafe_b64encode(b"c" * 32).decode("ascii")


def test_enroll_then_activate_command_issues_working_recovery_codes(
    monkeypatch,
    capsys,
):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(command, "SessionLocal", session_factory)
    monkeypatch.setattr(command, "ADMIN_MFA_ENCRYPTION_KEY", MFA_KEY)
    passwords = iter(
        ("operator password is long enough", "operator password is long enough")
    )
    monkeypatch.setattr(command.getpass, "getpass", lambda _prompt: next(passwords))

    assert command.main(
        [
            "enroll",
            "--operator-id",
            "operations.user@example.com",
            "--display-name",
            "Operations User",
            "--role",
            "OPERATOR",
        ]
    ) == 0
    enrollment_output = capsys.readouterr().out
    secret = re.search(
        r"AUTHENTICATOR_SETUP_KEY=([A-Z2-7]+)",
        enrollment_output,
    ).group(1)
    code = totp_code(secret, timestamp=datetime.now(timezone.utc))
    monkeypatch.setattr("builtins.input", lambda _prompt: code)

    assert command.main(
        ["activate", "--operator-id", "operations.user@example.com"]
    ) == 0
    activation_output = capsys.readouterr().out
    recovery_code = re.search(
        r"RECOVERY_CODE_1=([A-Z0-9-]+)",
        activation_output,
    ).group(1)

    db = session_factory()
    try:
        authenticated = authenticate_operator(
            db,
            operator_id="operations.user@example.com",
            password="operator password is long enough",
            second_factor=recovery_code,
            encryption_key=MFA_KEY,
        )
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert authenticated.authenticated is True
    assert authenticated.method == "recovery_code"


def test_list_and_disable_commands_expose_no_mfa_secret(
    monkeypatch,
    capsys,
):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    now = datetime.now(timezone.utc)
    try:
        for operator_id, role in (
            ("security.admin@example.com", "ADMIN"),
            ("operations.user@example.com", "OPERATOR"),
        ):
            enrollment = begin_operator_enrollment(
                db,
                operator_id=operator_id,
                display_name=operator_id,
                role=role,
                password="operator password is long enough",
                encryption_key=MFA_KEY,
                now=now,
            )
            confirm_operator_enrollment(
                db,
                operator_id=operator_id,
                verification_code=totp_code(
                    enrollment.secret,
                    timestamp=now,
                ),
                encryption_key=MFA_KEY,
                now=now,
            )
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(command, "SessionLocal", session_factory)
    monkeypatch.setattr(command, "ADMIN_MFA_ENCRYPTION_KEY", MFA_KEY)

    assert command.main(["list"]) == 0
    listed = capsys.readouterr().out
    assert "operations.user@example.com" in listed
    assert "STATUS=ACTIVE" in listed
    assert "AUTHENTICATOR_SETUP_KEY" not in listed
    assert "RECOVERY_CODE" not in listed

    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: "DISABLE operations.user@example.com",
    )
    assert command.main(
        [
            "disable",
            "--operator-id",
            "operations.user@example.com",
            "--actor-id",
            "security.admin@example.com",
        ]
    ) == 0

    db = session_factory()
    try:
        disabled = authenticate_operator(
            db,
            operator_id="operations.user@example.com",
            password="operator password is long enough",
            second_factor="000000",
            encryption_key=MFA_KEY,
        )
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
    assert disabled.authenticated is False


def test_reset_password_command_invalidates_old_password(
    monkeypatch,
):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    now = datetime.now(timezone.utc)
    target_secret = ""
    try:
        for operator_id, role in (
            ("security.admin@example.com", "ADMIN"),
            ("operations.user@example.com", "OPERATOR"),
        ):
            enrollment = begin_operator_enrollment(
                db,
                operator_id=operator_id,
                display_name=operator_id,
                role=role,
                password="original password is long enough",
                encryption_key=MFA_KEY,
                now=now,
            )
            confirm_operator_enrollment(
                db,
                operator_id=operator_id,
                verification_code=totp_code(
                    enrollment.secret,
                    timestamp=now,
                ),
                encryption_key=MFA_KEY,
                now=now,
            )
            if role == "OPERATOR":
                target_secret = enrollment.secret
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(command, "SessionLocal", session_factory)
    monkeypatch.setattr(command, "ADMIN_MFA_ENCRYPTION_KEY", MFA_KEY)
    passwords = iter(
        ("replacement password is long enough",) * 2
    )
    monkeypatch.setattr(command.getpass, "getpass", lambda _prompt: next(passwords))
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: "RESET PASSWORD operations.user@example.com",
    )

    assert command.main(
        [
            "reset-password",
            "--operator-id",
            "operations.user@example.com",
            "--actor-id",
            "security.admin@example.com",
        ]
    ) == 0

    db = session_factory()
    try:
        code = totp_code(target_secret, timestamp=datetime.now(timezone.utc))
        old = authenticate_operator(
            db,
            operator_id="operations.user@example.com",
            password="original password is long enough",
            second_factor=code,
            encryption_key=MFA_KEY,
        )
        replacement = authenticate_operator(
            db,
            operator_id="operations.user@example.com",
            password="replacement password is long enough",
            second_factor=code,
            encryption_key=MFA_KEY,
        )
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert old.authenticated is False
    assert replacement.authenticated is True


def test_reset_mfa_command_replaces_secret_and_recovery_codes(
    monkeypatch,
    capsys,
):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    now = datetime.now(timezone.utc)
    old_secret = ""
    old_recovery_code = ""
    try:
        for operator_id, role in (
            ("security.admin@example.com", "ADMIN"),
            ("operations.user@example.com", "OPERATOR"),
        ):
            enrollment = begin_operator_enrollment(
                db,
                operator_id=operator_id,
                display_name=operator_id,
                role=role,
                password="operator password is long enough",
                encryption_key=MFA_KEY,
                now=now,
            )
            recovery_codes = confirm_operator_enrollment(
                db,
                operator_id=operator_id,
                verification_code=totp_code(
                    enrollment.secret,
                    timestamp=now,
                ),
                encryption_key=MFA_KEY,
                now=now,
            )
            if role == "OPERATOR":
                old_secret = enrollment.secret
                old_recovery_code = recovery_codes[0]
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(command, "SessionLocal", session_factory)
    monkeypatch.setattr(command, "ADMIN_MFA_ENCRYPTION_KEY", MFA_KEY)
    state = {"new_secret": ""}

    def answer(prompt):
        if "authenticator code" in prompt:
            output = capsys.readouterr().out
            state["new_secret"] = re.search(
                r"AUTHENTICATOR_SETUP_KEY=([A-Z2-7]+)",
                output,
            ).group(1)
            return totp_code(
                state["new_secret"],
                timestamp=datetime.now(timezone.utc),
            )
        return "RESET MFA operations.user@example.com"

    monkeypatch.setattr("builtins.input", answer)
    assert command.main(
        [
            "reset-mfa",
            "--operator-id",
            "operations.user@example.com",
            "--actor-id",
            "security.admin@example.com",
        ]
    ) == 0

    db = session_factory()
    try:
        old_totp = authenticate_operator(
            db,
            operator_id="operations.user@example.com",
            password="operator password is long enough",
            second_factor=totp_code(
                old_secret,
                timestamp=datetime.now(timezone.utc),
            ),
            encryption_key=MFA_KEY,
        )
        old_recovery = authenticate_operator(
            db,
            operator_id="operations.user@example.com",
            password="operator password is long enough",
            second_factor=old_recovery_code,
            encryption_key=MFA_KEY,
        )
        replacement = authenticate_operator(
            db,
            operator_id="operations.user@example.com",
            password="operator password is long enough",
            second_factor=totp_code(
                state["new_secret"],
                timestamp=datetime.now(timezone.utc),
            ),
            encryption_key=MFA_KEY,
        )
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert old_totp.authenticated is False
    assert old_recovery.authenticated is False
    assert replacement.authenticated is True


def test_enrollment_requires_existing_admin_actor_after_bootstrap(
    monkeypatch,
):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    now = datetime.now(timezone.utc)
    try:
        enrollment = begin_operator_enrollment(
            db,
            operator_id="security.admin@example.com",
            display_name="Security Administrator",
            role="ADMIN",
            password="administrator password is long enough",
            encryption_key=MFA_KEY,
            now=now,
        )
        confirm_operator_enrollment(
            db,
            operator_id=enrollment.operator_id,
            verification_code=totp_code(enrollment.secret, timestamp=now),
            encryption_key=MFA_KEY,
            now=now,
        )
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(command, "SessionLocal", session_factory)
    monkeypatch.setattr(command, "ADMIN_MFA_ENCRYPTION_KEY", MFA_KEY)
    passwords = iter(("new operator password value",) * 2)
    monkeypatch.setattr(command.getpass, "getpass", lambda _prompt: next(passwords))

    blocked = command.main(
        [
            "enroll",
            "--operator-id",
            "new.operator@example.com",
            "--display-name",
            "New Operator",
            "--role",
            "OPERATOR",
        ]
    )

    db = session_factory()
    try:
        assert db.query(command.AdminOperator).count() == 1
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
    assert blocked == 2


def test_activation_requires_existing_admin_actor_after_bootstrap(
    monkeypatch,
):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    now = datetime.now(timezone.utc)
    try:
        administrator = begin_operator_enrollment(
            db,
            operator_id="security.admin@example.com",
            display_name="Security Administrator",
            role="ADMIN",
            password="administrator password is long enough",
            encryption_key=MFA_KEY,
            now=now,
        )
        confirm_operator_enrollment(
            db,
            operator_id=administrator.operator_id,
            verification_code=totp_code(administrator.secret, timestamp=now),
            encryption_key=MFA_KEY,
            now=now,
        )
        pending = begin_operator_enrollment(
            db,
            operator_id="new.operator@example.com",
            display_name="New Operator",
            role="OPERATOR",
            password="new operator password value",
            encryption_key=MFA_KEY,
            now=now,
        )
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(command, "SessionLocal", session_factory)
    monkeypatch.setattr(command, "ADMIN_MFA_ENCRYPTION_KEY", MFA_KEY)
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: totp_code(
            pending.secret,
            timestamp=datetime.now(timezone.utc),
        ),
    )

    blocked = command.main(
        ["activate", "--operator-id", "new.operator@example.com"]
    )

    db = session_factory()
    try:
        pending_operator = (
            db.query(command.AdminOperator)
            .filter(
                command.AdminOperator.operator_id
                == "new.operator@example.com"
            )
            .one()
        )
        assert pending_operator.active is False
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
    assert blocked == 2
