"""Application configuration sourced from environment variables.

Keep parsing and defaults in this module so services do not interpret the same
environment variable differently. Invalid numeric and boolean values fail fast
at startup instead of silently changing production behaviour.
"""

from __future__ import annotations

import os
from typing import Iterable


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def env_str(name: str, default: str = "", *, allow_empty: bool = True) -> str:
    """Return a stripped string environment value."""

    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip()
    if not value and not allow_empty:
        return default
    return value


def env_bool(name: str, default: bool = False) -> bool:
    """Parse a strict, human-friendly boolean environment value."""

    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default

    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ValueError(
        f"{name} must be one of: "
        f"{', '.join(sorted(_TRUE_VALUES | _FALSE_VALUES))}"
    )


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Parse an integer and enforce optional inclusive bounds."""

    raw = os.getenv(name)
    try:
        value = default if raw is None or not raw.strip() else int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc

    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


def env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Parse a float and enforce optional inclusive bounds."""

    raw = os.getenv(name)
    try:
        value = default if raw is None or not raw.strip() else float(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc

    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


def env_csv(
    name: str,
    default: Iterable[str] = (),
) -> list[str]:
    """Parse a comma-separated environment value into non-empty strings."""

    raw = os.getenv(name)
    values = default if raw is None else raw.split(",")
    return [str(value).strip() for value in values if str(value).strip()]


def env_int_set(
    name: str,
    default: Iterable[int],
    *,
    minimum: int,
    maximum: int,
) -> frozenset[int]:
    """Parse a comma-separated set of bounded integers."""

    raw_values = env_csv(name, (str(value) for value in default))
    parsed: set[int] = set()
    for raw_value in raw_values:
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ValueError(f"{name} must contain only integers") from exc
        if value < minimum or value > maximum:
            raise ValueError(
                f"{name} values must be between {minimum} and {maximum}"
            )
        parsed.add(value)
    if not parsed:
        raise ValueError(f"{name} must contain at least one value")
    return frozenset(parsed)


def normalize_database_url(value: str) -> str:
    """Select psycopg for provider-style PostgreSQL URLs."""

    value = value.strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


# Application identity and locale.
ENV = env_str("ENV", "production", allow_empty=False).lower()
APP_TIMEZONE = env_str("APP_TIMEZONE", "Asia/Kolkata", allow_empty=False)
LOG_LEVEL = env_str("LOG_LEVEL", "INFO", allow_empty=False).upper()

# Maintenance mode.
MAINTENANCE_MODE = env_bool("MAINTENANCE_MODE", False)
MAINTENANCE_ADMIN_BYPASS = env_str("MAINTENANCE_ADMIN_BYPASS")

# Customer support and privacy contacts. Empty defaults avoid publishing
# unverified contact details; production should provide these explicitly.
SUPPORT_PHONE = env_str("SUPPORT_PHONE")
SUPPORT_EMAIL = env_str("SUPPORT_EMAIL")
PRIVACY_EMAIL = env_str("PRIVACY_EMAIL", SUPPORT_EMAIL)
PRIVACY_POLICY_URL = env_str("PRIVACY_POLICY_URL")
TERMS_OF_SERVICE_URL = env_str("TERMS_OF_SERVICE_URL")
REFUND_POLICY_URL = env_str("REFUND_POLICY_URL")
CANCELLATION_POLICY_URL = env_str(
    "CANCELLATION_POLICY_URL",
    REFUND_POLICY_URL,
)
AI_CONSENT_VERSION = env_str(
    "AI_CONSENT_VERSION",
    "ai-privacy-2026-07",
    allow_empty=False,
)
BOOKING_TERMS_VERSION = env_str(
    "BOOKING_TERMS_VERSION",
    "booking-terms-2026-07",
    allow_empty=False,
)
LEGAL_CONTENT_VERSION = env_str(
    "LEGAL_CONTENT_VERSION",
    "legal-content-2026-07",
    allow_empty=False,
)
LEGAL_CONTENT_REVIEWED_ON = env_str("LEGAL_CONTENT_REVIEWED_ON")

BOOKING_NOTIFICATION_EMAILS = env_csv(
    "BOOKING_NOTIFICATION_EMAILS",
    (),
)
SUPPORT_NOTIFICATION_EMAILS = env_csv(
    "SUPPORT_NOTIFICATION_EMAILS",
    (),
)
SUPPORT_SLA_HOURS = env_int(
    "SUPPORT_SLA_HOURS",
    24,
    minimum=1,
    maximum=168,
)

# Transactional/internal email transport.
SENDGRID_API_KEY = env_str("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = env_str("SENDGRID_FROM_EMAIL")
SENDGRID_CONNECT_TIMEOUT_SECONDS = env_float(
    "SENDGRID_CONNECT_TIMEOUT_SECONDS",
    5.0,
    minimum=1.0,
    maximum=30.0,
)
SENDGRID_READ_TIMEOUT_SECONDS = env_float(
    "SENDGRID_READ_TIMEOUT_SECONDS",
    15.0,
    minimum=1.0,
    maximum=60.0,
)

# WhatsApp / Meta.
WHATSAPP_TOKEN = env_str("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = (
    env_str("WHATSAPP_PHONE_ID")
    or env_str("WHATSAPP_PHONE_NUMBER_ID")
    or env_str("PHONE_NUMBER_ID")
)
WHATSAPP_API_VERSION = env_str(
    "WHATSAPP_API_VERSION",
    "v24.0",
    allow_empty=False,
)
WHATSAPP_API_URL = (
    f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/"
    f"{WHATSAPP_PHONE_ID}/messages"
    if WHATSAPP_PHONE_ID
    else ""
)
WHATSAPP_VERIFY_TOKEN = env_str("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_APP_SECRET = env_str("WHATSAPP_APP_SECRET")
WHATSAPP_APP_SECRET_PREVIOUS = env_str("WHATSAPP_APP_SECRET_PREVIOUS")
ALLOW_INSECURE_WEBHOOKS = env_bool("ALLOW_INSECURE_WEBHOOKS", False)

# Consultation reminders are disabled unless both values for a specific
# reminder/language pair are populated with an approved Meta template. There
# is deliberately no cross-language fallback: sending an English template to a
# Hindi or Marathi user would be a surprising product and consent boundary.
CONSULTATION_REMINDER_TEMPLATES = {
    "24h": {
        "en": {
            "name": env_str("WHATSAPP_REMINDER_24H_TEMPLATE_EN"),
            "language_code": env_str(
                "WHATSAPP_REMINDER_24H_LANGUAGE_EN"
            ),
        },
        "hi": {
            "name": env_str("WHATSAPP_REMINDER_24H_TEMPLATE_HI"),
            "language_code": env_str(
                "WHATSAPP_REMINDER_24H_LANGUAGE_HI"
            ),
        },
        "mr": {
            "name": env_str("WHATSAPP_REMINDER_24H_TEMPLATE_MR"),
            "language_code": env_str(
                "WHATSAPP_REMINDER_24H_LANGUAGE_MR"
            ),
        },
    },
    "2h": {
        "en": {
            "name": env_str("WHATSAPP_REMINDER_2H_TEMPLATE_EN"),
            "language_code": env_str(
                "WHATSAPP_REMINDER_2H_LANGUAGE_EN"
            ),
        },
        "hi": {
            "name": env_str("WHATSAPP_REMINDER_2H_TEMPLATE_HI"),
            "language_code": env_str(
                "WHATSAPP_REMINDER_2H_LANGUAGE_HI"
            ),
        },
        "mr": {
            "name": env_str("WHATSAPP_REMINDER_2H_TEMPLATE_MR"),
            "language_code": env_str(
                "WHATSAPP_REMINDER_2H_LANGUAGE_MR"
            ),
        },
    },
}
CONSULTATION_REMINDER_CATCHUP_MINUTES = env_int(
    "CONSULTATION_REMINDER_CATCHUP_MINUTES",
    30,
    minimum=5,
    maximum=120,
)
CONSULTATION_REMINDER_BATCH_SIZE = env_int(
    "CONSULTATION_REMINDER_BATCH_SIZE",
    100,
    minimum=1,
    maximum=500,
)

# Webhook limits, replay tolerance, and durable-event retention.
WEBHOOK_MAX_PAYLOAD_BYTES = env_int(
    "WEBHOOK_MAX_PAYLOAD_BYTES",
    1_048_576,
    minimum=1_024,
)
WEBHOOK_REPLAY_WINDOW_SECONDS = env_int(
    "WEBHOOK_REPLAY_WINDOW_SECONDS",
    0,
    minimum=0,
)
WEBHOOK_EVENT_TTL_DAYS = env_int(
    "WEBHOOK_EVENT_TTL_DAYS",
    30,
    minimum=1,
)
PROCESSED_MESSAGE_TTL_DAYS = env_int(
    "PROCESSED_MESSAGE_TTL_DAYS",
    30,
    minimum=1,
)
INBOUND_MESSAGE_LEASE_SECONDS = env_int(
    "INBOUND_MESSAGE_LEASE_SECONDS",
    120,
    minimum=30,
    maximum=900,
)
INBOUND_USER_LOCK_TIMEOUT_SECONDS = env_int(
    "INBOUND_USER_LOCK_TIMEOUT_SECONDS",
    25,
    minimum=1,
    maximum=55,
)
USER_MESSAGE_LIMIT = env_int(
    "USER_MESSAGE_LIMIT",
    10,
    minimum=1,
    maximum=100,
)
USER_MESSAGE_WINDOW_SECONDS = env_int(
    "USER_MESSAGE_WINDOW_SECONDS",
    60,
    minimum=1,
    maximum=3_600,
)
AI_CALL_COOLDOWN_SECONDS = env_float(
    "AI_CALL_COOLDOWN_SECONDS",
    2.0,
    minimum=0.0,
    maximum=60.0,
)
GLOBAL_REQUEST_LIMIT = env_int(
    "GLOBAL_REQUEST_LIMIT",
    600,
    minimum=10,
    maximum=100_000,
)
GLOBAL_REQUEST_WINDOW_SECONDS = env_int(
    "GLOBAL_REQUEST_WINDOW_SECONDS",
    60,
    minimum=1,
    maximum=3_600,
)

# AI providers.
OPENAI_API_KEY = env_str("OPENAI_API_KEY")
OPENAI_MODEL = env_str("OPENAI_MODEL", "gpt-4o-mini", allow_empty=False)
OPENAI_FALLBACK_MODEL = env_str(
    "OPENAI_FALLBACK_MODEL",
    OPENAI_MODEL,
    allow_empty=False,
)
AI_RESPONSE_CACHE_TTL_SECONDS = env_int(
    "AI_RESPONSE_CACHE_TTL_SECONDS",
    20,
    minimum=0,
)
AI_SAFETY_IDENTIFIER_SECRET = env_str("AI_SAFETY_IDENTIFIER_SECRET")

# Razorpay.
RAZORPAY_KEY_ID = env_str("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = env_str("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = env_str("RAZORPAY_WEBHOOK_SECRET")
RAZORPAY_WEBHOOK_SECRET_PREVIOUS = env_str(
    "RAZORPAY_WEBHOOK_SECRET_PREVIOUS"
)
RAZORPAY_MODE = env_str("RAZORPAY_MODE", "live", allow_empty=False).lower()
RAZORPAY_API_TIMEOUT_SECONDS = env_float(
    "RAZORPAY_API_TIMEOUT_SECONDS",
    12.0,
    minimum=2.0,
    maximum=60.0,
)
PAYMENT_RECONCILIATION_LOOKBACK_DAYS = env_int(
    "PAYMENT_RECONCILIATION_LOOKBACK_DAYS",
    14,
    minimum=1,
    maximum=90,
)
PAYMENT_LINK_TTL_MINUTES = env_int(
    "PAYMENT_LINK_TTL_MINUTES",
    16,
    minimum=16,
)
AUTO_SEND_RECEIPTS = env_bool("AUTO_SEND_RECEIPTS", False)
OUTBOX_MAX_ATTEMPTS = env_int("OUTBOX_MAX_ATTEMPTS", 12, minimum=1)
OUTBOX_RETRY_BASE_SECONDS = env_int(
    "OUTBOX_RETRY_BASE_SECONDS",
    60,
    minimum=1,
)
OUTBOX_RETRY_MAX_SECONDS = env_int(
    "OUTBOX_RETRY_MAX_SECONDS",
    3_600,
    minimum=60,
)
OUTBOX_RUNNING_LEASE_SECONDS = env_int(
    "OUTBOX_RUNNING_LEASE_SECONDS",
    900,
    minimum=60,
)
OUTBOX_COMPLETED_TTL_DAYS = env_int(
    "OUTBOX_COMPLETED_TTL_DAYS",
    30,
    minimum=1,
)

# Booking rules and capacity.
BOOKING_PRICE = env_int("BOOKING_PRICE", 499, minimum=1)
BOOKING_CUTOFF_HOURS = env_float(
    "BOOKING_CUTOFF_HOURS",
    2.0,
    minimum=0.0,
)
BOOKING_MAX_AHEAD_DAYS = env_int(
    "BOOKING_MAX_AHEAD_DAYS",
    30,
    minimum=1,
)
BOOKING_MAX_PER_DAY = env_int("BOOKING_MAX_PER_DAY", 8, minimum=1)
BOOKING_MAX_PER_SLOT = env_int("BOOKING_MAX_PER_SLOT", 1, minimum=1)
BOOKING_WORKING_WEEKDAYS = env_int_set(
    "BOOKING_WORKING_WEEKDAYS",
    (0, 1, 2, 3, 4, 5),
    minimum=0,
    maximum=6,
)
BOOKING_DATE_CHOICES = env_int(
    "BOOKING_DATE_CHOICES",
    7,
    minimum=1,
    maximum=10,
)
# Descriptive compatibility alias for new code.
BOOKING_SLOT_CAPACITY = BOOKING_MAX_PER_SLOT

# Admin. ADMIN_PASSWORD is retained because the legacy admin module imports it.
ADMIN_TOKEN = env_str("ADMIN_TOKEN")
ADMIN_PASSWORD = env_str("ADMIN_PASSWORD", ADMIN_TOKEN)

# Database.
DATABASE_URL = normalize_database_url(
    env_str(
        "DATABASE_URL",
        "sqlite:///./nyaysetu.db",
        allow_empty=False,
    )
)
AUTO_CREATE_SCHEMA = env_bool("AUTO_CREATE_SCHEMA", ENV != "production")
DB_POOL_PRE_PING = env_bool("DB_POOL_PRE_PING", True)
DB_POOL_SIZE = env_int("DB_POOL_SIZE", 5, minimum=1)
DB_MAX_OVERFLOW = env_int("DB_MAX_OVERFLOW", 10, minimum=0)
DB_POOL_RECYCLE_SECONDS = env_int(
    "DB_POOL_RECYCLE_SECONDS",
    1_800,
    minimum=0,
)
DB_CONNECT_TIMEOUT_SECONDS = env_int(
    "DB_CONNECT_TIMEOUT_SECONDS",
    10,
    minimum=1,
)
SQLITE_BUSY_TIMEOUT_SECONDS = env_int(
    "SQLITE_BUSY_TIMEOUT_SECONDS",
    30,
    minimum=1,
)

# Analytics retention and payload bounds.
ANALYTICS_EVENT_TTL_DAYS = env_int(
    "ANALYTICS_EVENT_TTL_DAYS",
    90,
    minimum=1,
)
ANALYTICS_MAX_PROPERTY_BYTES = env_int(
    "ANALYTICS_MAX_PROPERTY_BYTES",
    8_192,
    minimum=256,
)
