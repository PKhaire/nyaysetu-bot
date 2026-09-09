"""Interactive lifecycle management for named administrator identities."""

from __future__ import annotations

import argparse
import getpass
import json
import sys

from config import ADMIN_MFA_ENCRYPTION_KEY
from db import SessionLocal
from models import AdminAuditEvent, AdminOperator
from services.admin_identity_service import (
    begin_operator_enrollment,
    change_operator_password,
    confirm_operator_enrollment,
    prepare_operator_mfa_replacement,
    replace_operator_mfa,
    set_operator_active,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage NyaySetu named operations identities.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    enroll = commands.add_parser(
        "enroll",
        help="Create an inactive identity and issue its authenticator key.",
    )
    enroll.add_argument("--operator-id", required=True)
    enroll.add_argument("--display-name", required=True)
    enroll.add_argument("--actor-id")
    enroll.add_argument(
        "--role",
        required=True,
        choices=("ADMIN", "OPERATOR", "VIEWER"),
    )

    activate = commands.add_parser(
        "activate",
        help="Confirm authenticator enrollment and issue recovery codes.",
    )
    activate.add_argument("--operator-id", required=True)
    activate.add_argument("--actor-id")

    commands.add_parser(
        "list",
        help="List identity status without displaying authentication secrets.",
    )
    for command_name in ("disable", "enable"):
        lifecycle = commands.add_parser(
            command_name,
            help=f"{command_name.title()} one enrolled identity.",
        )
        lifecycle.add_argument("--operator-id", required=True)
        lifecycle.add_argument(
            "--actor-id",
            required=True,
            help="Active ADMIN accountable for this platform operation.",
        )
    reset_password = commands.add_parser(
        "reset-password",
        help="Replace an identity password and invalidate its browser sessions.",
    )
    reset_password.add_argument("--operator-id", required=True)
    reset_password.add_argument("--actor-id", required=True)
    reset_mfa = commands.add_parser(
        "reset-mfa",
        help="Replace MFA and recovery codes, invalidating browser sessions.",
    )
    reset_mfa.add_argument("--operator-id", required=True)
    reset_mfa.add_argument("--actor-id", required=True)
    return parser


def _enroll(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        active_admins = int(
            db.query(AdminOperator)
            .filter(
                AdminOperator.active.is_(True),
                AdminOperator.role == "ADMIN",
            )
            .count()
        )
        actor = None
        if active_admins:
            actor = (
                db.query(AdminOperator)
                .filter(
                    AdminOperator.operator_id
                    == str(args.actor_id or "").strip().lower(),
                    AdminOperator.active.is_(True),
                    AdminOperator.role == "ADMIN",
                )
                .one_or_none()
            )
            if actor is None:
                raise ValueError("active_admin_actor_required")
    except ValueError as exc:
        db.close()
        print(f"ERROR={exc}", file=sys.stderr)
        return 2

    password = getpass.getpass("New password (minimum 16 characters): ")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        db.close()
        print("ERROR=password_confirmation_mismatch", file=sys.stderr)
        return 2

    try:
        enrollment = begin_operator_enrollment(
            db,
            operator_id=args.operator_id,
            display_name=args.display_name,
            role=args.role,
            password=password,
            encryption_key=ADMIN_MFA_ENCRYPTION_KEY,
        )
        db.add(
            AdminAuditEvent(
                operator_id=(actor.operator_id if actor else enrollment.operator_id),
                action="admin_operator.enroll",
                target_type="admin_operator",
                target_id=enrollment.operator_id,
                before_json="{}",
                after_json=json.dumps(
                    {"role": args.role, "status": "PENDING"},
                    sort_keys=True,
                ),
            )
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        print(f"ERROR={exc}", file=sys.stderr)
        return 2
    finally:
        db.close()

    print(f"OPERATOR_ID={enrollment.operator_id}")
    print("STATUS=PENDING_MFA_CONFIRMATION")
    print(f"AUTHENTICATOR_SETUP_KEY={enrollment.secret}")
    print(f"AUTHENTICATOR_URI={enrollment.provisioning_uri}")
    print("Run the activate command after adding this account to the app.")
    print("Do not screenshot, paste, or retain this setup output in logs.")
    return 0


def _activate(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        active_admins = int(
            db.query(AdminOperator)
            .filter(
                AdminOperator.active.is_(True),
                AdminOperator.role == "ADMIN",
            )
            .count()
        )
        actor = None
        if active_admins:
            actor = (
                db.query(AdminOperator)
                .filter(
                    AdminOperator.operator_id
                    == str(args.actor_id or "").strip().lower(),
                    AdminOperator.active.is_(True),
                    AdminOperator.role == "ADMIN",
                )
                .one_or_none()
            )
            if actor is None:
                raise ValueError("active_admin_actor_required")
        verification_code = input(
            "Current 6-digit authenticator code: "
        ).strip()
        recovery_codes = confirm_operator_enrollment(
            db,
            operator_id=args.operator_id,
            verification_code=verification_code,
            encryption_key=ADMIN_MFA_ENCRYPTION_KEY,
        )
        activated_id = args.operator_id.strip().lower()
        db.add(
            AdminAuditEvent(
                operator_id=(actor.operator_id if actor else activated_id),
                action="admin_operator.activate",
                target_type="admin_operator",
                target_id=activated_id,
                before_json=json.dumps({"active": False}, sort_keys=True),
                after_json=json.dumps({"active": True}, sort_keys=True),
            )
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        print(f"ERROR={exc}", file=sys.stderr)
        return 2
    finally:
        db.close()

    print("STATUS=ACTIVE")
    print("Store these one-use recovery codes offline; they are never shown again.")
    for index, code in enumerate(recovery_codes, start=1):
        print(f"RECOVERY_CODE_{index}={code}")
    return 0


def _list_operators() -> int:
    db = SessionLocal()
    try:
        operators = db.query(AdminOperator).order_by(AdminOperator.operator_id).all()
        for operator in operators:
            status = "ACTIVE" if operator.active else "INACTIVE"
            print(
                f"OPERATOR_ID={operator.operator_id} "
                f"DISPLAY_NAME={operator.display_name} "
                f"ROLE={operator.role} STATUS={status}"
            )
        print(f"OPERATOR_COUNT={len(operators)}")
    finally:
        db.close()
    return 0


def _change_active_state(args: argparse.Namespace, *, active: bool) -> int:
    action = "ENABLE" if active else "DISABLE"
    confirmation = input(
        f"Type {action} {args.operator_id.strip().lower()}: "
    ).strip()
    if confirmation != f"{action} {args.operator_id.strip().lower()}":
        print("ERROR=confirmation_mismatch", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        actor = (
            db.query(AdminOperator)
            .filter(
                AdminOperator.operator_id == args.actor_id.strip().lower(),
                AdminOperator.active.is_(True),
                AdminOperator.role == "ADMIN",
            )
            .one_or_none()
        )
        if actor is None:
            raise ValueError("active_admin_actor_required")
        target = (
            db.query(AdminOperator)
            .filter(
                AdminOperator.operator_id == args.operator_id.strip().lower()
            )
            .one_or_none()
        )
        before = {"active": bool(target.active)} if target else {}
        set_operator_active(
            db,
            operator_id=args.operator_id,
            active=active,
        )
        db.add(
            AdminAuditEvent(
                operator_id=actor.operator_id,
                action=f"admin_operator.{action.lower()}",
                target_type="admin_operator",
                target_id=args.operator_id.strip().lower(),
                before_json=json.dumps(before, sort_keys=True),
                after_json=json.dumps({"active": active}, sort_keys=True),
            )
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        print(f"ERROR={exc}", file=sys.stderr)
        return 2
    finally:
        db.close()
    print(f"STATUS={'ACTIVE' if active else 'INACTIVE'}")
    return 0


def _reset_password(args: argparse.Namespace) -> int:
    password = getpass.getpass("Replacement password (minimum 16 characters): ")
    confirmation = getpass.getpass("Confirm replacement password: ")
    if password != confirmation:
        print("ERROR=password_confirmation_mismatch", file=sys.stderr)
        return 2
    expected = f"RESET PASSWORD {args.operator_id.strip().lower()}"
    if input(f"Type {expected}: ").strip() != expected:
        print("ERROR=confirmation_mismatch", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        actor = (
            db.query(AdminOperator)
            .filter(
                AdminOperator.operator_id == args.actor_id.strip().lower(),
                AdminOperator.active.is_(True),
                AdminOperator.role == "ADMIN",
            )
            .one_or_none()
        )
        if actor is None:
            raise ValueError("active_admin_actor_required")
        change_operator_password(
            db,
            operator_id=args.operator_id,
            password=password,
        )
        db.add(
            AdminAuditEvent(
                operator_id=actor.operator_id,
                action="admin_operator.reset_password",
                target_type="admin_operator",
                target_id=args.operator_id.strip().lower(),
                before_json="{}",
                after_json=json.dumps(
                    {"sessions_invalidated": True},
                    sort_keys=True,
                ),
            )
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        print(f"ERROR={exc}", file=sys.stderr)
        return 2
    finally:
        db.close()
    print("STATUS=PASSWORD_RESET")
    return 0


def _reset_mfa(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        actor = (
            db.query(AdminOperator)
            .filter(
                AdminOperator.operator_id == args.actor_id.strip().lower(),
                AdminOperator.active.is_(True),
                AdminOperator.role == "ADMIN",
            )
            .one_or_none()
        )
        target = (
            db.query(AdminOperator)
            .filter(
                AdminOperator.operator_id == args.operator_id.strip().lower(),
                AdminOperator.active.is_(True),
            )
            .one_or_none()
        )
        if actor is None:
            raise ValueError("active_admin_actor_required")
        if target is None:
            raise ValueError("active_operator_required")

        setup = prepare_operator_mfa_replacement(target.operator_id)
        print(f"AUTHENTICATOR_SETUP_KEY={setup.secret}")
        print(f"AUTHENTICATOR_URI={setup.provisioning_uri}")
        verification_code = input("Current authenticator code: ").strip()
        expected = f"RESET MFA {target.operator_id}"
        if input(f"Type {expected}: ").strip() != expected:
            raise ValueError("confirmation_mismatch")
        recovery_codes = replace_operator_mfa(
            db,
            operator_id=target.operator_id,
            secret=setup.secret,
            verification_code=verification_code,
            encryption_key=ADMIN_MFA_ENCRYPTION_KEY,
        )
        db.add(
            AdminAuditEvent(
                operator_id=actor.operator_id,
                action="admin_operator.reset_mfa",
                target_type="admin_operator",
                target_id=target.operator_id,
                before_json="{}",
                after_json=json.dumps(
                    {"sessions_invalidated": True},
                    sort_keys=True,
                ),
            )
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        print(f"ERROR={exc}", file=sys.stderr)
        return 2
    finally:
        db.close()

    print("STATUS=MFA_RESET")
    print("Store these replacement recovery codes offline.")
    for index, code in enumerate(recovery_codes, start=1):
        print(f"RECOVERY_CODE_{index}={code}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not ADMIN_MFA_ENCRYPTION_KEY:
        print("ERROR=admin_mfa_encryption_key_required", file=sys.stderr)
        return 2
    if args.command == "enroll":
        return _enroll(args)
    if args.command == "activate":
        return _activate(args)
    if args.command == "list":
        return _list_operators()
    if args.command == "disable":
        return _change_active_state(args, active=False)
    if args.command == "enable":
        return _change_active_state(args, active=True)
    if args.command == "reset-password":
        return _reset_password(args)
    if args.command == "reset-mfa":
        return _reset_mfa(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
