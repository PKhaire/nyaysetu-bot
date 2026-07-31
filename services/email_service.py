"""Privacy-minimised operational email delivery through Amazon SES.

The public helpers in this module intentionally retain their boolean contract:
the durable outbox owns delayed retries and calls each helper until it reports
that SES accepted the message. Provider calls are made through the SES v2 HTTPS
API, and logs never include credentials, recipients, subjects, or bodies.
"""

from __future__ import annotations

import logging
import re
from threading import Lock
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import BotoCoreError, ClientError

from config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN,
    BOOKING_NOTIFICATION_EMAILS,
    ENV,
    PAYMENT_RECONCILIATION_EMAILS,
    SES_CONFIGURATION_SET,
    SES_CONNECT_TIMEOUT_SECONDS,
    SES_FROM_EMAIL,
    SES_READ_TIMEOUT_SECONDS,
    SES_REGION,
    SUPPORT_NOTIFICATION_EMAILS,
)
from models import PaymentReconciliation, SupportRequest


logger = logging.getLogger(__name__)

_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)
_SES_REGION_PATTERN = re.compile(r"[a-z]{2}(?:-[a-z0-9]+)+-\d+")
_TAG_VALUE_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")
_MAX_SES_RECIPIENTS = 50
_MAX_SUBJECT_CHARACTERS = 200
_MAX_BODY_CHARACTERS = 100_000
_SES_CLIENT: Any | None = None
_SES_CLIENT_LOCK = Lock()

# Botocore DEBUG output can include a fully serialized SendEmail request.
# Keep transport logging below that threshold even if application diagnostics
# are temporarily made more verbose.
for _sdk_logger_name in ("boto3", "botocore", "urllib3"):
    logging.getLogger(_sdk_logger_name).setLevel(logging.WARNING)


def _configured() -> bool:
    return bool(
        SES_REGION
        and SES_FROM_EMAIL
        and AWS_ACCESS_KEY_ID
        and AWS_SECRET_ACCESS_KEY
        and _SES_REGION_PATTERN.fullmatch(SES_REGION)
        and _valid_email(SES_FROM_EMAIL)
        and (
            ENV not in {"staging", "production"}
            or bool(SES_CONFIGURATION_SET)
        )
    )


def _valid_email(value: str) -> bool:
    normalized = str(value or "").strip()
    local_part = normalized.partition("@")[0]
    return bool(
        normalized
        and normalized.isascii()
        and len(normalized) <= 254
        and _EMAIL_PATTERN.fullmatch(normalized)
        and not local_part.startswith(".")
        and not local_part.endswith(".")
        and ".." not in local_part
    )


def _normalize_recipients(recipients: list[str]) -> list[str]:
    """Return unique valid addresses, failing closed on any invalid value."""

    normalized = [
        str(recipient or "").strip()
        for recipient in recipients
        if str(recipient or "").strip()
    ]
    if not normalized or not all(_valid_email(value) for value in normalized):
        return []
    return list(dict.fromkeys(normalized))


def _safe_tag_value(value: object) -> str:
    """Create a bounded ASCII SES tag that contains no user narrative."""

    normalized = _TAG_VALUE_PATTERN.sub("_", str(value or "unknown"))
    return normalized[:256] or "unknown"


def _build_ses_client():
    credentials: dict[str, str] = {
        "aws_access_key_id": AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
    }
    if AWS_SESSION_TOKEN:
        credentials["aws_session_token"] = AWS_SESSION_TOKEN

    # One SDK attempt per outbox execution makes retry timing observable and
    # avoids an invisible immediate duplicate after an ambiguous timeout.
    client_config = BotocoreConfig(
        connect_timeout=SES_CONNECT_TIMEOUT_SECONDS,
        read_timeout=SES_READ_TIMEOUT_SECONDS,
        tcp_keepalive=True,
        retries={
            "mode": "standard",
            "total_max_attempts": 1,
        },
    )
    return boto3.client(
        "sesv2",
        region_name=SES_REGION,
        config=client_config,
        **credentials,
    )


def _get_ses_client():
    """Lazily create one thread-safe SDK client for the single web process."""

    global _SES_CLIENT
    if _SES_CLIENT is not None:
        return _SES_CLIENT

    with _SES_CLIENT_LOCK:
        if _SES_CLIENT is None:
            _SES_CLIENT = _build_ses_client()
    return _SES_CLIENT


def _send_via_ses(
    subject: str,
    body: str,
    recipients: list[str],
    *,
    event_type: str = "operational",
    event_id: object = "unknown",
) -> bool:
    """Submit one private-recipient message to Amazon SES.

    SES has no provider-side idempotency token for ``SendEmail``. A single BCC
    destination therefore gives this outbox attempt one provider request,
    avoids exposing recipient addresses, and limits partial-send ambiguity.
    """

    if not _configured():
        logger.warning("Amazon SES environment variables are not configured")
        return False

    normalized_recipients = _normalize_recipients(recipients)
    if not normalized_recipients:
        logger.warning("Email skipped because no valid recipients are configured")
        return False
    if len(normalized_recipients) > _MAX_SES_RECIPIENTS:
        logger.error(
            "Email skipped because the Amazon SES recipient limit was exceeded"
        )
        return False
    if (
        not str(subject).strip()
        or len(str(subject)) > _MAX_SUBJECT_CHARACTERS
        or len(str(body)) > _MAX_BODY_CHARACTERS
    ):
        logger.error("Email skipped because its content bounds are invalid")
        return False

    request: dict[str, object] = {
        "FromEmailAddress": SES_FROM_EMAIL,
        "Destination": {
            "BccAddresses": normalized_recipients,
        },
        "Content": {
            "Simple": {
                "Subject": {
                    "Data": str(subject),
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {
                        "Data": str(body),
                        "Charset": "UTF-8",
                    }
                },
            }
        },
        "EmailTags": [
            {
                "Name": "nyaysetu_event_type",
                "Value": _safe_tag_value(event_type),
            },
            {
                "Name": "nyaysetu_event_id",
                "Value": _safe_tag_value(event_id),
            },
        ],
    }
    if SES_CONFIGURATION_SET:
        request["ConfigurationSetName"] = SES_CONFIGURATION_SET

    try:
        response = _get_ses_client().send_email(**request)
        message_id = str(response.get("MessageId") or "").strip()
        if not message_id:
            logger.error("Amazon SES accepted no message identifier")
            return False

        logger.info(
            "Email accepted by Amazon SES | recipient_count=%s",
            len(normalized_recipients),
        )
        return True
    except ClientError as exc:
        error_code = _safe_tag_value(
            exc.response.get("Error", {}).get("Code", "ClientError")
        )
        logger.error("Amazon SES rejected email | code=%s", error_code)
        return False
    except BotoCoreError as exc:
        logger.error(
            "Amazon SES email transport failed | reason=%s",
            type(exc).__name__,
        )
        return False
    except Exception as exc:
        # Never log the exception message: provider/client exceptions can echo
        # request data, credentials, recipient addresses, or message content.
        logger.error(
            "Amazon SES email send failed | reason=%s",
            type(exc).__name__,
        )
        return False


def send_booking_notification_email(booking) -> bool:
    """Notify operations that one verified paid booking needs fulfilment."""

    try:
        subject = f"NyaySetu booking confirmed #{booking.id}"
        body = (
            "A paid consultation booking is ready for operations.\n\n"
            f"Booking ID : {booking.id}\n"
            f"Date       : {booking.date}\n"
            f"Time Slot  : {booking.slot_readable}\n"
            "Payment    : CONFIRMED\n\n"
            "Open the authenticated NyaySetu operations interface for "
            "contact and case details."
        )
        return _send_via_ses(
            subject=subject,
            body=body,
            recipients=BOOKING_NOTIFICATION_EMAILS,
            event_type="booking_confirmation",
            event_id=booking.id,
        )
    except Exception as exc:
        logger.error(
            "Booking notification email failed | booking_id=%s | reason=%s",
            getattr(booking, "id", "unknown"),
            type(exc).__name__,
        )
        return False


def send_support_request_email(support_request: SupportRequest) -> bool:
    """Notify operations without copying contact data or case narrative."""

    subject = f"NyaySetu support request #{support_request.id}"
    body = (
        "A new user support request was recorded.\n\n"
        f"Ticket ID : NSH-{support_request.id:06d}\n"
        f"Case ID   : {support_request.case_id or 'N/A'}\n"
        f"Type      : {support_request.request_type}\n"
        f"Priority  : {support_request.priority}\n"
        f"SLA Due   : {support_request.sla_due_at or 'N/A'} UTC\n\n"
        "Open the authenticated NyaySetu operations interface to review "
        "the request and contact information."
    )
    return _send_via_ses(
        subject,
        body,
        SUPPORT_NOTIFICATION_EMAILS,
        event_type="support_request",
        event_id=support_request.id,
    )


def send_payment_reconciliation_email(
    reconciliation: PaymentReconciliation,
) -> bool:
    """Alert operations without copying provider tokens or user data."""

    expected_amount = (
        reconciliation.expected_amount
        if reconciliation.expected_amount is not None
        else "N/A"
    )
    received_amount = (
        reconciliation.received_amount
        if reconciliation.received_amount is not None
        else "N/A"
    )
    subject = f"NyaySetu payment review required #{reconciliation.id}"
    body = (
        "A captured payment needs operational review.\n\n"
        f"Reconciliation ID : {reconciliation.id}\n"
        f"Booking ID        : {reconciliation.booking_id or 'UNMATCHED'}\n"
        f"Reason            : {reconciliation.reason}\n"
        f"Expected (paise)  : {expected_amount}\n"
        f"Received (paise)  : {received_amount}\n"
        f"Currency          : {reconciliation.currency or 'N/A'}\n\n"
        "Open the authenticated NyaySetu operations interface to review "
        "provider identifiers and record a disposition."
    )
    return _send_via_ses(
        subject,
        body,
        PAYMENT_RECONCILIATION_EMAILS,
        event_type="payment_reconciliation",
        event_id=reconciliation.id,
    )


def send_email(
    subject: str,
    body: str,
    recipients: list[str] | None = None,
) -> bool:
    """Compatibility helper used by scheduled operational reports."""

    return _send_via_ses(
        subject,
        body,
        BOOKING_NOTIFICATION_EMAILS if recipients is None else recipients,
        event_type="scheduled_report",
        event_id="daily_appointments",
    )


def send_new_booking_email(booking) -> None:
    """Reserved compatibility hook for a future admin notification."""

    logger.info(
        "send_new_booking_email skipped (disabled) | booking_id=%s",
        getattr(booking, "id", "N/A"),
    )


def send_advocate_booking_email(advocate, booking) -> None:
    """Reserved compatibility hook for future advocate assignment."""

    logger.info(
        "send_advocate_booking_email skipped (disabled) | booking_id=%s",
        getattr(booking, "id", "N/A"),
    )
