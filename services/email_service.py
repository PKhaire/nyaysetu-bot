# ============================================================
# email_service.py
# ------------------------------------------------------------
# Centralized email handling for NyaySetu
#
# - Uses SendGrid (HTTPS, Render-safe)
# - All emails routed through a single helper
# - Admin / Advocate emails intentionally disabled
#   for future use
# ============================================================

import atexit
import logging

import httpx

from config import (
    BOOKING_NOTIFICATION_EMAILS,
    SENDGRID_API_KEY,
    SENDGRID_CONNECT_TIMEOUT_SECONDS,
    SENDGRID_FROM_EMAIL,
    SENDGRID_READ_TIMEOUT_SECONDS,
    SUPPORT_NOTIFICATION_EMAILS,
)
from db import SessionLocal
from models import PaymentReconciliation, SupportRequest, User

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# SendGrid configuration (from Render environment variables)
# ------------------------------------------------------------
SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"
_SENDGRID_TIMEOUT = httpx.Timeout(
    connect=SENDGRID_CONNECT_TIMEOUT_SECONDS,
    read=SENDGRID_READ_TIMEOUT_SECONDS,
    write=SENDGRID_READ_TIMEOUT_SECONDS,
    pool=SENDGRID_CONNECT_TIMEOUT_SECONDS,
)
_HTTP_CLIENT = httpx.Client(timeout=_SENDGRID_TIMEOUT)
atexit.register(_HTTP_CLIENT.close)

# ============================================================
# INTERNAL HELPER — DO NOT CALL DIRECTLY FROM OUTSIDE
# ============================================================
def _send_via_sendgrid(
    subject: str,
    body: str,
    recipients: list[str],
) -> bool:
    """
    Internal helper to send email via SendGrid.
    This function never raises exceptions and reports whether all sends worked.
    Safe for background tasks / webhooks.
    """

    if not SENDGRID_API_KEY or not SENDGRID_FROM_EMAIL:
        logger.warning("SendGrid environment variables are not configured")
        return False

    if not recipients:
        logger.warning("Email skipped because no recipients are configured")
        return False

    try:
        normalized_recipients = list(
            dict.fromkeys(
                str(recipient).strip()
                for recipient in recipients
                if str(recipient).strip()
            )
        )
        if not normalized_recipients:
            logger.warning(
                "Email skipped because no valid recipients are configured"
            )
            return False

        # A single request keeps latency bounded. Separate personalizations
        # prevent one recipient's address from being exposed to another.
        payload = {
            "personalizations": [
                {"to": [{"email": recipient}]}
                for recipient in normalized_recipients
            ],
            "from": {"email": SENDGRID_FROM_EMAIL},
            "subject": str(subject),
            "content": [{"type": "text/plain", "value": str(body)}],
        }
        response = _HTTP_CLIENT.post(
            SENDGRID_API_URL,
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_SENDGRID_TIMEOUT,
        )
        if not 200 <= response.status_code < 300:
            # Response bodies can echo provider/request details, so only the
            # status code is safe to record.
            logger.error(
                "SendGrid rejected email | status=%s",
                response.status_code,
            )
            return False

        logger.info(
            "Email sent via SendGrid | recipient_count=%s",
            len(normalized_recipients),
        )
        return True

    except httpx.TimeoutException as exc:
        # A timed-out submission is not retried here: SendGrid may have
        # accepted it, and an automatic retry could deliver a duplicate.
        logger.error(
            "SendGrid email timed out | reason=%s",
            type(exc).__name__,
        )
        return False

    except Exception as exc:
        # Provider exceptions can contain request details. Log only the class,
        # never recipient addresses, message bodies, API responses, or keys.
        logger.error(
            "SendGrid email send failed | reason=%s",
            type(exc).__name__,
        )
        return False


# ============================================================
# ACTIVE: Booking Notification Email (PRIMARY FLOW)
# ============================================================
def send_booking_notification_email(booking) -> bool:
    """
    Sends booking confirmation email to internal notification emails.
    """

    db = SessionLocal()
    try:
        # Fetch user safely to get case_id
        user = (
            db.query(User)
            .filter(User.whatsapp_id == booking.whatsapp_id)
            .first()
        )

        case_id = user.case_id if user else "N/A"

        subject = "🆕 New Consultation Booking Confirmed"

        body = f"""
New legal consultation booked.

Case ID     : {case_id}
Name        : {booking.name}
Phone       : {booking.phone}

Date        : {booking.date}
Time Slot   : {booking.slot_readable}

Category    : {booking.category}
Subcategory : {booking.subcategory or "N/A"}
State       : {booking.state_name}
District    : {booking.district_name}

Payment     : CONFIRMED

– NyaySetu System
"""

        return _send_via_sendgrid(
            subject=subject,
            body=body,
            recipients=BOOKING_NOTIFICATION_EMAILS,
        )

    except Exception as exc:
        logger.error(
            "Booking notification email failed | booking_id=%s | reason=%s",
            booking.id,
            type(exc).__name__,
        )
        return False

    finally:
        db.close()


def send_support_request_email(support_request: SupportRequest) -> bool:
    """Notify the configured operations recipients about a support ticket."""

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.id == support_request.user_id)
            .first()
        )
        contact = user.whatsapp_id if user else "N/A"
    finally:
        db.close()

    subject = f"NyaySetu support request #{support_request.id}"
    body = (
        "A new user support request was recorded.\n\n"
        f"Ticket ID : NSH-{support_request.id:06d}\n"
        f"Case ID   : {support_request.case_id or 'N/A'}\n"
        f"Type      : {support_request.request_type}\n"
        f"Priority  : {support_request.priority}\n"
        f"WhatsApp  : {contact}\n"
        f"SLA Due   : {support_request.sla_due_at or 'N/A'} UTC\n\n"
        f"Message:\n{support_request.message}\n"
    )
    return _send_via_sendgrid(
        subject,
        body,
        SUPPORT_NOTIFICATION_EMAILS,
    )


def send_payment_reconciliation_email(
    reconciliation: PaymentReconciliation,
) -> bool:
    """Alert operations without including user contact or case narrative."""

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
    recipients = list(
        dict.fromkeys(
            [
                *BOOKING_NOTIFICATION_EMAILS,
                *SUPPORT_NOTIFICATION_EMAILS,
            ]
        )
    )
    subject = (
        "NyaySetu payment review required "
        f"#{reconciliation.id}"
    )
    body = (
        "A captured payment needs operational review.\n\n"
        f"Reconciliation ID : {reconciliation.id}\n"
        f"Booking ID        : {reconciliation.booking_id or 'UNMATCHED'}\n"
        f"Payment ID        : {reconciliation.payment_id}\n"
        f"Payment Link ID   : "
        f"{reconciliation.payment_link_id or 'N/A'}\n"
        f"Reason            : {reconciliation.reason}\n"
        f"Expected (paise)  : {expected_amount}\n"
        f"Received (paise)  : {received_amount}\n"
        f"Currency          : {reconciliation.currency or 'N/A'}\n\n"
        "Review this item through the authenticated NyaySetu operations API."
    )
    return _send_via_sendgrid(subject, body, recipients)


def send_email(
    subject: str,
    body: str,
    recipients: list[str] | None = None,
) -> bool:
    """Compatibility helper used by scheduled operational reports."""

    return _send_via_sendgrid(
        subject,
        body,
        recipients or BOOKING_NOTIFICATION_EMAILS,
    )


# ============================================================
# FUTURE USE: Admin booking notification
# ------------------------------------------------------------
# Intentionally disabled.
# Reason:
# - Admin notifications are currently centralized
#   via SendGrid booking notifications.
# - Can be re-enabled later for internal ops,
#   dashboards, or parallel alerting.
#
# def send_new_booking_email(booking):
#     pass
# ============================================================

def send_new_booking_email(booking) -> None:
    """
    FUTURE USE:
    Admin-level booking notification email.

    Currently disabled by design.
    This stub exists to prevent ImportError during app startup.
    """
    logger.info(
        "ℹ️ send_new_booking_email skipped (disabled) | booking_id=%s",
        getattr(booking, "id", "N/A"),
    )
    return


# ============================================================
# FUTURE USE: Advocate booking assignment email
# ------------------------------------------------------------
# Intentionally disabled.
# Reason:
# - Advocate-wise routing not finalized yet.
# - Prevents accidental crashes due to
#   wrong email routing/signatures.
#
# def send_advocate_booking_email(advocate, booking):
#     pass
# ============================================================
def send_advocate_booking_email(advocate, booking) -> None:
    """
    FUTURE USE:
    Advocate-specific booking assignment email.
    Currently disabled by design.
    """
    logger.info(
        "ℹ️ send_advocate_booking_email skipped (disabled) | booking_id=%s",
        getattr(booking, "id", "N/A"),
    )
    return
