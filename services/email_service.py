import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from db import SessionLocal
from models import User

# ===============================
# EMAIL CONFIG
# ===============================
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")


# ===============================
# CORE EMAIL SENDER
# ===============================
def send_email(subject: str, body: str):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, ADMIN_EMAIL]):
        raise RuntimeError("Email configuration missing")

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = ADMIN_EMAIL
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    server.starttls()
    server.login(SMTP_USER, SMTP_PASSWORD)
    server.sendmail(SMTP_USER, ADMIN_EMAIL, msg.as_string())
    server.quit()


# ===============================
# ADMIN BOOKING EMAIL (FIXED)
# ===============================
def send_new_booking_email(booking):
    """
    Sends admin email on successful booking payment.
    SAFE:
    - Fetches case_id from User (not Booking)
    - No DB writes
    - No crashes if user missing
    """

    db = SessionLocal()
    try:
        # Fetch User to get case_id
        user = (
            db.query(User)
            .filter(User.whatsapp_id == booking.whatsapp_id)
            .first()
        )

        case_id = user.case_id if user else "N/A"

        subject = "🆕 New Consultation Booked – NyaySetu"

        body = f"""
New legal consultation booked.

Case ID     : {case_id}
Name        : {booking.name}
Phone       : {booking.phone}
WhatsApp ID : {booking.whatsapp_id}

Date        : {booking.date}
Time Slot   : {booking.slot_readable}

Category    : {booking.category}
Subcategory : {booking.subcategory or "N/A"}
State       : {booking.state_name}
District    : {booking.district_name}

Payment     : CONFIRMED

— NyaySetu System
"""

        send_email(subject, body)

    finally:
        db.close()
