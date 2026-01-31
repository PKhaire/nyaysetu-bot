import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import BOOKING_NOTIFICATION_EMAILS
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

def send_email(subject, body):
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    server.starttls()
    server.login(SMTP_USERNAME, SMTP_PASSWORD)

    for recipient in BOOKING_NOTIFICATION_EMAILS:
        message = f"Subject: {subject}\n\n{body}"
        server.sendmail(
            SMTP_FROM_EMAIL,
            recipient,
            message
        )

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

def send_advocate_booking_email(advocate, booking):
    subject = f"🆕 New Legal Consultation Assigned"

    body = f"""
Hello {advocate.name},

A new consultation has been assigned to you.

Client Name: {booking.name}
Category: {booking.category.replace('_', ' ').title()}
District: {booking.district.title()}
Date: {booking.date}
Time Slot: {booking.slot_code.replace('_', ':00 - ')}

Please review and prepare accordingly.

– NyaySetu
"""

    send_email(
        to=advocate.email,
        subject=subject,
        body=body
    )

def send_booking_notification_email(booking):
    subject = "🆕 New Consultation Booking Confirmed"

    body = f"""
A new consultation booking has been confirmed.

Client Name: {booking.name}
Category: {booking.category.replace('_', ' ').title()}
State: {booking.state_name}
District: {booking.district_name}
Date: {booking.date}
Time Slot: {booking.slot_readable}

Please take necessary action.

– NyaySetu System
"""

    # send_email already knows recipients internally
    send_email(subject, body)
