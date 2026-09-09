"""Named administrator identity, MFA and recovery controls."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from models import AdminOperator, AdminRecoveryCode


_OPERATOR_PATTERN = re.compile(r"^[A-Za-z0-9._@+-]{2,120}$")
_ROLES = frozenset({"ADMIN", "OPERATOR", "VIEWER"})
_RECOVERY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_DUMMY_PASSWORD_HASH = generate_password_hash(
    "not-a-real-operator-password",
    method="scrypt",
)


@dataclass(frozen=True)
class OperatorEnrollment:
    operator_id: str
    secret: str
    provisioning_uri: str


@dataclass(frozen=True)
class AuthenticationResult:
    authenticated: bool
    operator_db_id: int | None = None
    operator_id: str | None = None
    display_name: str | None = None
    role: str | None = None
    session_version: int | None = None
    method: str | None = None
    reason_code: str = "INVALID_CREDENTIALS"


def _utc_naive(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is not None:
        current = current.astimezone(timezone.utc).replace(tzinfo=None)
    return current


def _timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _normalized_operator_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _OPERATOR_PATTERN.fullmatch(normalized):
        raise ValueError("invalid_operator_id")
    return normalized


def _fernet(encryption_key: str) -> Fernet:
    try:
        return Fernet(str(encryption_key or "").strip().encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ValueError("invalid_admin_mfa_encryption_key") from exc


def _recovery_digest(code: str, encryption_key: str) -> str:
    normalized = "".join(
        character
        for character in str(code or "").upper()
        if character.isalnum()
    )
    try:
        key = base64.urlsafe_b64decode(
            str(encryption_key or "").strip().encode("ascii")
        )
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ValueError("invalid_admin_mfa_encryption_key") from exc
    if len(key) != 32 or len(normalized) != 12:
        raise ValueError("invalid_recovery_code")
    return hmac.new(
        key,
        b"nyaysetu-admin-recovery:" + normalized.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _new_recovery_code() -> str:
    compact = "".join(
        secrets.choice(_RECOVERY_ALPHABET) for _ in range(12)
    )
    return "-".join(compact[index : index + 4] for index in range(0, 12, 4))


def totp_code(
    secret: str,
    *,
    timestamp: int | float | datetime,
    digits: int = 6,
    period_seconds: int = 30,
) -> str:
    """Return the RFC 6238 SHA-1 code for one timestamp."""

    if isinstance(timestamp, datetime):
        timestamp = timestamp.timestamp()
    if digits not in {6, 7, 8}:
        raise ValueError("unsupported_totp_digits")
    if period_seconds <= 0:
        raise ValueError("invalid_totp_period")

    normalized = "".join(str(secret or "").split()).upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    try:
        key = base64.b32decode(normalized + padding, casefold=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid_totp_secret") from exc
    if not key:
        raise ValueError("invalid_totp_secret")

    counter = int(timestamp) // period_seconds
    digest = hmac.new(
        key,
        struct.pack(">Q", counter),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0]
    value = (binary & 0x7FFFFFFF) % (10**digits)
    return str(value).zfill(digits)


def _matching_totp_counter(
    secret: str,
    provided: str,
    *,
    now: datetime,
) -> int | None:
    normalized = "".join(str(provided or "").split())
    if not re.fullmatch(r"\d{6}", normalized):
        return None
    current_counter = int(_timestamp(now)) // 30
    for offset in (-1, 0, 1):
        counter = current_counter + offset
        expected = totp_code(secret, timestamp=counter * 30)
        if hmac.compare_digest(normalized, expected):
            return counter
    return None


def begin_operator_enrollment(
    db,
    *,
    operator_id: str,
    display_name: str,
    role: str,
    password: str,
    encryption_key: str,
    now: datetime | None = None,
) -> OperatorEnrollment:
    """Create an inactive identity and return its one-time MFA enrollment data."""

    normalized_id = _normalized_operator_id(operator_id)
    normalized_name = " ".join(str(display_name or "").strip().split())
    normalized_role = str(role or "").strip().upper()
    if not normalized_name or len(normalized_name) > 160:
        raise ValueError("invalid_display_name")
    if normalized_role not in _ROLES:
        raise ValueError("invalid_operator_role")
    if not 16 <= len(password or "") <= 128 or "\x00" in password:
        raise ValueError("invalid_operator_password")
    if (
        db.query(AdminOperator.id)
        .filter(func.lower(AdminOperator.operator_id) == normalized_id)
        .first()
        is not None
    ):
        raise ValueError("operator_id_exists")

    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    encrypted_secret = _fernet(encryption_key).encrypt(
        secret.encode("ascii")
    ).decode("ascii")
    current = _utc_naive(now)
    operator = AdminOperator(
        operator_id=normalized_id,
        display_name=normalized_name,
        role=normalized_role,
        password_hash=generate_password_hash(password, method="scrypt"),
        totp_secret_ciphertext=encrypted_secret,
        active=False,
        failed_attempts=0,
        password_changed_at=current,
        created_at=current,
        updated_at=current,
    )
    db.add(operator)
    db.flush()

    issuer = "NyaySetu Operations"
    label = quote(f"{issuer}:{normalized_id}", safe="")
    provisioning_uri = (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer, safe='')}&algorithm=SHA1&digits=6&period=30"
    )
    return OperatorEnrollment(
        operator_id=normalized_id,
        secret=secret,
        provisioning_uri=provisioning_uri,
    )


def confirm_operator_enrollment(
    db,
    *,
    operator_id: str,
    verification_code: str,
    encryption_key: str,
    now: datetime | None = None,
) -> list[str]:
    """Activate a pending identity after authenticator proof."""

    normalized_id = _normalized_operator_id(operator_id)
    operator = (
        db.query(AdminOperator)
        .filter(AdminOperator.operator_id == normalized_id)
        .with_for_update()
        .one_or_none()
    )
    if operator is None or operator.active:
        raise ValueError("operator_enrollment_not_pending")
    try:
        secret = _fernet(encryption_key).decrypt(
            operator.totp_secret_ciphertext.encode("ascii")
        ).decode("ascii")
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
        raise ValueError("operator_mfa_secret_unavailable") from exc

    current = now or datetime.now(timezone.utc)
    if _matching_totp_counter(secret, verification_code, now=current) is None:
        raise ValueError("invalid_totp_code")

    recovery_codes = [_new_recovery_code() for _ in range(8)]
    created_at = _utc_naive(current)
    for code in recovery_codes:
        db.add(
            AdminRecoveryCode(
                operator_id=operator.id,
                code_hash=_recovery_digest(code, encryption_key),
                created_at=created_at,
            )
        )
    operator.active = True
    operator.mfa_enrolled_at = created_at
    operator.failed_attempts = 0
    operator.locked_until = None
    operator.updated_at = created_at
    db.flush()
    return recovery_codes


def _failed_authentication(operator: AdminOperator, now: datetime) -> None:
    operator.failed_attempts = int(operator.failed_attempts or 0) + 1
    if operator.failed_attempts >= 5:
        operator.locked_until = now + timedelta(minutes=15)
    operator.updated_at = now


def authenticate_operator(
    db,
    *,
    operator_id: str,
    password: str,
    second_factor: str,
    encryption_key: str,
    now: datetime | None = None,
) -> AuthenticationResult:
    """Authenticate one active named operator using password and MFA."""

    try:
        normalized_id = _normalized_operator_id(operator_id)
    except ValueError:
        normalized_id = ""
    operator = (
        db.query(AdminOperator)
        .filter(AdminOperator.operator_id == normalized_id)
        .with_for_update()
        .one_or_none()
        if normalized_id
        else None
    )
    if operator is None:
        check_password_hash(_DUMMY_PASSWORD_HASH, password or "")
        return AuthenticationResult(authenticated=False)

    current_aware = now or datetime.now(timezone.utc)
    current = _utc_naive(current_aware)
    if operator.locked_until and operator.locked_until > current:
        return AuthenticationResult(
            authenticated=False,
            reason_code="ACCOUNT_LOCKED",
        )
    if operator.locked_until:
        operator.locked_until = None
        operator.failed_attempts = 0

    password_valid = check_password_hash(
        operator.password_hash,
        password or "",
    )
    if not operator.active or not operator.mfa_enrolled_at or not password_valid:
        _failed_authentication(operator, current)
        db.flush()
        return AuthenticationResult(authenticated=False)

    method = None
    matched_counter = None
    try:
        secret = _fernet(encryption_key).decrypt(
            operator.totp_secret_ciphertext.encode("ascii")
        ).decode("ascii")
        matched_counter = _matching_totp_counter(
            secret,
            second_factor,
            now=current_aware,
        )
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError, ValueError):
        matched_counter = None

    if matched_counter is not None and (
        operator.last_totp_counter is None
        or matched_counter > operator.last_totp_counter
    ):
        method = "totp"
    else:
        try:
            recovery_hash = _recovery_digest(second_factor, encryption_key)
        except ValueError:
            recovery_hash = ""
        recovery = None
        for candidate in (
            db.query(AdminRecoveryCode)
            .filter(
                AdminRecoveryCode.operator_id == operator.id,
                AdminRecoveryCode.used_at.is_(None),
            )
            .all()
        ):
            if hmac.compare_digest(candidate.code_hash, recovery_hash):
                recovery = candidate
        if recovery is not None:
            recovery.used_at = current
            method = "recovery_code"

    if method is None:
        _failed_authentication(operator, current)
        db.flush()
        return AuthenticationResult(authenticated=False)

    if method == "totp":
        operator.last_totp_counter = matched_counter
    operator.failed_attempts = 0
    operator.locked_until = None
    operator.last_login_at = current
    operator.updated_at = current
    db.flush()
    return AuthenticationResult(
        authenticated=True,
        operator_db_id=operator.id,
        operator_id=operator.operator_id,
        display_name=operator.display_name,
        role=operator.role,
        session_version=int(operator.session_version or 0),
        method=method,
        reason_code="AUTHENTICATED",
    )


def set_operator_active(
    db,
    *,
    operator_id: str,
    active: bool,
    now: datetime | None = None,
) -> None:
    """Enable or disable one identity while retaining an active administrator."""

    normalized_id = _normalized_operator_id(operator_id)
    operators = (
        db.query(AdminOperator)
        .order_by(AdminOperator.id)
        .with_for_update()
        .all()
    )
    operator = next(
        (
            candidate
            for candidate in operators
            if candidate.operator_id == normalized_id
        ),
        None,
    )
    if operator is None:
        raise ValueError("operator_not_found")
    target_state = bool(active)
    if target_state and not operator.mfa_enrolled_at:
        raise ValueError("operator_enrollment_not_confirmed")
    if operator.active and not target_state and operator.role == "ADMIN":
        active_admins = sum(
            1
            for candidate in operators
            if candidate.active and candidate.role == "ADMIN"
        )
        if active_admins <= 1:
            raise ValueError("last_active_admin_required")
    if operator.active != target_state:
        operator.session_version = int(operator.session_version or 0) + 1
    operator.active = target_state
    operator.updated_at = _utc_naive(now)
    if not target_state:
        operator.locked_until = None
        operator.failed_attempts = 0
    db.flush()


def admin_identity_readiness(db) -> dict[str, object]:
    """Return privacy-safe named-account readiness for health reporting."""

    total = int(db.query(func.count(AdminOperator.id)).scalar() or 0)
    active_named = int(
        db.query(func.count(AdminOperator.id))
        .filter(
            AdminOperator.active.is_(True),
            AdminOperator.mfa_enrolled_at.is_not(None),
            AdminOperator.role.in_(_ROLES),
        )
        .scalar()
        or 0
    )
    active_admins = int(
        db.query(func.count(AdminOperator.id))
        .filter(
            AdminOperator.active.is_(True),
            AdminOperator.mfa_enrolled_at.is_not(None),
            AdminOperator.role == "ADMIN",
        )
        .scalar()
        or 0
    )
    return {
        "mode": "named_mfa" if total else "legacy_bootstrap",
        "active_named_operators": active_named,
        "active_admins": active_admins,
        "production_compatible": bool(
            active_named >= 2 and active_admins >= 1
        ),
    }


def change_operator_password(
    db,
    *,
    operator_id: str,
    password: str,
    now: datetime | None = None,
) -> None:
    """Replace one password and invalidate all of that identity's sessions."""

    normalized_id = _normalized_operator_id(operator_id)
    if not 16 <= len(password or "") <= 128 or "\x00" in password:
        raise ValueError("invalid_operator_password")
    operator = (
        db.query(AdminOperator)
        .filter(AdminOperator.operator_id == normalized_id)
        .with_for_update()
        .one_or_none()
    )
    if operator is None:
        raise ValueError("operator_not_found")
    current = _utc_naive(now)
    operator.password_hash = generate_password_hash(password, method="scrypt")
    operator.password_changed_at = current
    operator.session_version = int(operator.session_version or 0) + 1
    operator.failed_attempts = 0
    operator.locked_until = None
    operator.updated_at = current
    db.flush()


def prepare_operator_mfa_replacement(operator_id: str) -> OperatorEnrollment:
    """Create transient enrollment material without changing stored identity."""

    normalized_id = _normalized_operator_id(operator_id)
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    issuer = "NyaySetu Operations"
    label = quote(f"{issuer}:{normalized_id}", safe="")
    provisioning_uri = (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer, safe='')}&algorithm=SHA1&digits=6&period=30"
    )
    return OperatorEnrollment(
        operator_id=normalized_id,
        secret=secret,
        provisioning_uri=provisioning_uri,
    )


def replace_operator_mfa(
    db,
    *,
    operator_id: str,
    secret: str,
    verification_code: str,
    encryption_key: str,
    now: datetime | None = None,
) -> list[str]:
    """Replace MFA only after proving possession of the replacement seed."""

    normalized_id = _normalized_operator_id(operator_id)
    operator = (
        db.query(AdminOperator)
        .filter(AdminOperator.operator_id == normalized_id)
        .with_for_update()
        .one_or_none()
    )
    if operator is None or not operator.active:
        raise ValueError("active_operator_required")
    current_aware = now or datetime.now(timezone.utc)
    if _matching_totp_counter(secret, verification_code, now=current_aware) is None:
        raise ValueError("invalid_totp_code")

    encrypted_secret = _fernet(encryption_key).encrypt(
        secret.encode("ascii")
    ).decode("ascii")
    current = _utc_naive(current_aware)
    db.query(AdminRecoveryCode).filter(
        AdminRecoveryCode.operator_id == operator.id
    ).delete(synchronize_session=False)
    recovery_codes = [_new_recovery_code() for _ in range(8)]
    for code in recovery_codes:
        db.add(
            AdminRecoveryCode(
                operator_id=operator.id,
                code_hash=_recovery_digest(code, encryption_key),
                created_at=current,
            )
        )
    operator.totp_secret_ciphertext = encrypted_secret
    operator.mfa_enrolled_at = current
    operator.last_totp_counter = None
    operator.session_version = int(operator.session_version or 0) + 1
    operator.failed_attempts = 0
    operator.locked_until = None
    operator.updated_at = current
    db.flush()
    return recovery_codes
