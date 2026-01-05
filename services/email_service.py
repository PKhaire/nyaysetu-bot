import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")


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


def send_new_booking_email(booking):
    subject = "🆕 New Consultation Booked – NyaySetu"

    body = f"""
New legal consultation booked.

Case ID   : {booking.case_id}
Name      : {booking.name}
WhatsApp  : {booking.whatsapp_id}

Date      : {booking.date}
Time Slot : {booking.slot_code}

Category  : {booking.category}
State     : {booking.state}
District  : {booking.district}

Payment   : CONFIRMED

— NyaySetu System
"""

    send_email(subject, body)
