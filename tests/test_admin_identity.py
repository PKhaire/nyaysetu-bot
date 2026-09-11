"""Behavioral tests for named operations identities and MFA."""

import base64
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import Base
from models import AdminOperator, Advocate
from services.admin_identity_service import (
    admin_identity_readiness,
    authenticate_operator,
    begin_operator_enrollment,
    confirm_operator_enrollment,
    set_operator_active,
    totp_code,
)


MFA_KEY = base64.urlsafe_b64encode(b"m" * 32).decode("ascii")


@pytest.fixture
def identity_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_totp_code_matches_the_rfc6238_sha1_example():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    assert totp_code(secret, timestamp=59, digits=8) == "94287082"


def test_named_operator_must_prove_totp_enrollment_before_authentication(
    identity_db,
):
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    enrollment = begin_operator_enrollment(
        identity_db,
        operator_id="Prashant.Admin@example.com",
        display_name="Prashant Khaire",
        role="ADMIN",
        password="correct horse battery staple",
        encryption_key=MFA_KEY,
        now=now,
    )

    before_confirmation = authenticate_operator(
        identity_db,
        operator_id="prashant.admin@example.com",
        password="correct horse battery staple",
        second_factor="000000",
        encryption_key=MFA_KEY,
        now=now,
    )
    assert before_confirmation.authenticated is False

    recovery_codes = confirm_operator_enrollment(
        identity_db,
        operator_id="prashant.admin@example.com",
        verification_code=totp_code(enrollment.secret, timestamp=now),
        encryption_key=MFA_KEY,
        now=now,
    )
    authenticated = authenticate_operator(
        identity_db,
        operator_id="prashant.admin@example.com",
        password="correct horse battery staple",
        second_factor=totp_code(enrollment.secret, timestamp=now),
        encryption_key=MFA_KEY,
        now=now,
    )

    assert len(recovery_codes) == 8
    assert authenticated.authenticated is True
    assert authenticated.operator_id == "prashant.admin@example.com"
    assert authenticated.role == "ADMIN"
    assert authenticated.method == "totp"


def test_operator_can_be_disabled_without_removing_the_last_active_admin(
    identity_db,
):
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    secrets_by_id = {}
    for operator_id in ("first.admin@example.com", "second.admin@example.com"):
        enrollment = begin_operator_enrollment(
            identity_db,
            operator_id=operator_id,
            display_name=operator_id,
            role="ADMIN",
            password="correct horse battery staple",
            encryption_key=MFA_KEY,
            now=now,
        )
        confirm_operator_enrollment(
            identity_db,
            operator_id=operator_id,
            verification_code=totp_code(enrollment.secret, timestamp=now),
            encryption_key=MFA_KEY,
            now=now,
        )
        secrets_by_id[operator_id] = enrollment.secret

    set_operator_active(
        identity_db,
        operator_id="first.admin@example.com",
        active=False,
        now=now,
    )
    disabled = authenticate_operator(
        identity_db,
        operator_id="first.admin@example.com",
        password="correct horse battery staple",
        second_factor=totp_code(
            secrets_by_id["first.admin@example.com"],
            timestamp=now,
        ),
        encryption_key=MFA_KEY,
        now=now,
    )

    assert disabled.authenticated is False
    with pytest.raises(ValueError, match="last_active_admin_required"):
        set_operator_active(
            identity_db,
            operator_id="second.admin@example.com",
            active=False,
            now=now,
        )


def test_production_identity_readiness_requires_admin_and_operator_redundancy(
    identity_db,
):
    before = admin_identity_readiness(identity_db)
    assert before == {
        "mode": "legacy_bootstrap",
        "active_named_operators": 0,
        "active_admins": 0,
        "production_compatible": False,
    }

    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    for operator_id, role in (
        ("security.admin@example.com", "ADMIN"),
        ("operations.user@example.com", "OPERATOR"),
    ):
        enrollment = begin_operator_enrollment(
            identity_db,
            operator_id=operator_id,
            display_name=operator_id,
            role=role,
            password="correct horse battery staple",
            encryption_key=MFA_KEY,
            now=now,
        )
        confirm_operator_enrollment(
            identity_db,
            operator_id=operator_id,
            verification_code=totp_code(enrollment.secret, timestamp=now),
            encryption_key=MFA_KEY,
            now=now,
        )

    after = admin_identity_readiness(identity_db)
    assert after == {
        "mode": "named_mfa",
        "active_named_operators": 2,
        "active_admins": 1,
        "production_compatible": True,
    }


def test_identity_readiness_ignores_active_rows_without_valid_mfa_and_role(
    identity_db,
):
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    for operator_id, role in (
        ("unenrolled.admin@example.com", "ADMIN"),
        ("invalid.role@example.com", "OPERATOR"),
    ):
        begin_operator_enrollment(
            identity_db,
            operator_id=operator_id,
            display_name=operator_id,
            role=role,
            password="correct horse battery staple",
            encryption_key=MFA_KEY,
            now=now,
        )
    unenrolled, invalid_role = (
        identity_db.query(AdminOperator).order_by(AdminOperator.id).all()
    )
    unenrolled.active = True
    invalid_role.active = True
    invalid_role.mfa_enrolled_at = now.replace(tzinfo=None)
    invalid_role.role = "UNRECOGNIZED"
    identity_db.flush()

    readiness = admin_identity_readiness(identity_db)

    assert readiness == {
        "mode": "named_mfa",
        "active_named_operators": 0,
        "active_admins": 0,
        "production_compatible": False,
    }


def test_advocate_identity_requires_verified_link_and_not_admin_readiness(
    identity_db,
):
    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    advocate = Advocate(
        name="Synthetic Verified Advocate",
        email="verified.advocate@example.com",
        category="banking",
        district="Mumbai",
        active=True,
        verification_status="VERIFIED",
        verification_ref="synthetic-identity-check",
        verified_at=now.replace(tzinfo=None),
        authority_scope_json=(
            '{"version":"synthetic-v1",'
            '"product_codes":["synthetic_advocate_notice"]}'
        ),
    )
    identity_db.add(advocate)
    identity_db.flush()

    with pytest.raises(ValueError, match="verified_advocate_link_required"):
        begin_operator_enrollment(
            identity_db,
            operator_id="unlinked.advocate@example.com",
            display_name="Unlinked Advocate",
            role="ADVOCATE",
            password="correct horse battery staple",
            encryption_key=MFA_KEY,
            now=now,
        )

    enrollment = begin_operator_enrollment(
        identity_db,
        operator_id="verified.advocate@example.com",
        display_name="Synthetic Verified Advocate",
        role="ADVOCATE",
        advocate_id=advocate.id,
        password="correct horse battery staple",
        encryption_key=MFA_KEY,
        now=now,
    )
    confirm_operator_enrollment(
        identity_db,
        operator_id=enrollment.operator_id,
        verification_code=totp_code(enrollment.secret, timestamp=now),
        encryption_key=MFA_KEY,
        now=now,
    )

    identity = identity_db.query(AdminOperator).one()
    authenticated = authenticate_operator(
        identity_db,
        operator_id=enrollment.operator_id,
        password="correct horse battery staple",
        second_factor=totp_code(enrollment.secret, timestamp=now),
        encryption_key=MFA_KEY,
        now=now,
    )

    assert identity.advocate_id == advocate.id
    assert authenticated.authenticated is True
    assert authenticated.role == "ADVOCATE"
    assert admin_identity_readiness(identity_db) == {
        "mode": "named_mfa",
        "active_named_operators": 0,
        "active_admins": 0,
        "production_compatible": False,
    }


def test_recovery_code_is_valid_exactly_once(identity_db):
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    enrollment = begin_operator_enrollment(
        identity_db,
        operator_id="recovery.admin@example.com",
        display_name="Recovery Administrator",
        role="ADMIN",
        password="correct horse battery staple",
        encryption_key=MFA_KEY,
        now=now,
    )
    recovery_codes = confirm_operator_enrollment(
        identity_db,
        operator_id=enrollment.operator_id,
        verification_code=totp_code(enrollment.secret, timestamp=now),
        encryption_key=MFA_KEY,
        now=now,
    )

    first = authenticate_operator(
        identity_db,
        operator_id=enrollment.operator_id,
        password="correct horse battery staple",
        second_factor=recovery_codes[0],
        encryption_key=MFA_KEY,
        now=now,
    )
    second = authenticate_operator(
        identity_db,
        operator_id=enrollment.operator_id,
        password="correct horse battery staple",
        second_factor=recovery_codes[0],
        encryption_key=MFA_KEY,
        now=now,
    )

    assert first.authenticated is True
    assert first.method == "recovery_code"
    assert second.authenticated is False


def test_totp_code_cannot_be_replayed(identity_db):
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    enrollment = begin_operator_enrollment(
        identity_db,
        operator_id="replay.admin@example.com",
        display_name="Replay Administrator",
        role="ADMIN",
        password="correct horse battery staple",
        encryption_key=MFA_KEY,
        now=now,
    )
    confirm_operator_enrollment(
        identity_db,
        operator_id=enrollment.operator_id,
        verification_code=totp_code(enrollment.secret, timestamp=now),
        encryption_key=MFA_KEY,
        now=now,
    )
    code = totp_code(enrollment.secret, timestamp=now)

    first = authenticate_operator(
        identity_db,
        operator_id=enrollment.operator_id,
        password="correct horse battery staple",
        second_factor=code,
        encryption_key=MFA_KEY,
        now=now,
    )
    replay = authenticate_operator(
        identity_db,
        operator_id=enrollment.operator_id,
        password="correct horse battery staple",
        second_factor=code,
        encryption_key=MFA_KEY,
        now=now,
    )

    assert first.authenticated is True
    assert replay.authenticated is False


def test_five_failed_attempts_lock_account_for_fifteen_minutes(identity_db):
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    enrollment = begin_operator_enrollment(
        identity_db,
        operator_id="locked.admin@example.com",
        display_name="Locked Administrator",
        role="ADMIN",
        password="correct horse battery staple",
        encryption_key=MFA_KEY,
        now=now,
    )
    confirm_operator_enrollment(
        identity_db,
        operator_id=enrollment.operator_id,
        verification_code=totp_code(enrollment.secret, timestamp=now),
        encryption_key=MFA_KEY,
        now=now,
    )
    for _attempt in range(5):
        failed = authenticate_operator(
            identity_db,
            operator_id=enrollment.operator_id,
            password="incorrect password value",
            second_factor="000000",
            encryption_key=MFA_KEY,
            now=now,
        )
        assert failed.authenticated is False

    while_locked = authenticate_operator(
        identity_db,
        operator_id=enrollment.operator_id,
        password="correct horse battery staple",
        second_factor=totp_code(enrollment.secret, timestamp=now),
        encryption_key=MFA_KEY,
        now=now,
    )
    after_lock = now.replace(minute=16)
    after_timeout = authenticate_operator(
        identity_db,
        operator_id=enrollment.operator_id,
        password="correct horse battery staple",
        second_factor=totp_code(enrollment.secret, timestamp=after_lock),
        encryption_key=MFA_KEY,
        now=after_lock,
    )

    assert while_locked.reason_code == "ACCOUNT_LOCKED"
    assert after_timeout.authenticated is True
