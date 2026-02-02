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

import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from db import SessionLocal
from models import User

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# SendGrid configuration (from Render environment variables)
# ------------------------------------------------------------
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")

# ------------------------------------------------------------
# TEMP: Centralized booking notification recipients
# (Can be changed to advocate-wise routing later)
# ------------------------------------------------------------
BOOKING_NOTIFICATION_EMAILS = [
    "outsidethecourt@gmail.com",
    "nyaysetu@gmail.com",
]


# ============================================================
# INTERNAL HELPER — DO NOT CALL DIRECTLY FROM OUTSIDE
# ============================================================
def _send_via_sendgrid(subject: str, body: str, recipients: list[str]) -> None:
    """
    Internal helper to send email via SendGrid.
    This function NEVER raises exceptions.
    Safe for background tasks / webhooks.
    """

    if not SENDGRID_API_KEY or not SENDGRID_FROM_EMAIL:
        logger.error("❌ SendGrid environment variables not configured")
        return

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)

        for recipient in recipients:
            message = Mail(
                from_email=SENDGRID_FROM_EMAIL,
                to_emails=recipient,
                subject=subject,
                plain_text_content=body,
            )
            sg.send(message)

        logger.info("📧 Email sent via SendGrid | subject=%s", subject)

    except Exception:
        logger.exception("❌ SendGrid email send failed")


# ============================================================
# ACTIVE: Booking Notification Email (PRIMARY FLOW)
# ============================================================
def send_booking_notification_email(booking) -> None:
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

        _send_via_sendgrid(
            subject=subject,
            body=body,
            recipients=BOOKING_NOTIFICATION_EMAILS,
        )

    except Exception:
        logger.exception(
            "⚠️ Booking notification email failed | booking_id=%s",
            booking.id,
        )

    finally:
        db.close()


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
