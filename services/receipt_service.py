# services/receipt_service.py

import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from db import SessionLocal
from models import Booking
from utils.date_utils import format_date_readable 
RECEIPT_DIR = "receipts"


def generate_pdf_receipt(booking):
    """
    Generates payment receipt PDF.
    Idempotent and safe for retries.
    """
    os.makedirs(RECEIPT_DIR, exist_ok=True)

    file_path = os.path.join(
        RECEIPT_DIR,
        f"receipt_{booking.id}.pdf"
    )

    # -------------------------------------------------
    # Create PDF ONLY if it doesn't already exist
    # -------------------------------------------------
    if not os.path.exists(file_path):
        c = canvas.Canvas(file_path, pagesize=A4)

        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, "NyaySetu – Payment Receipt")

        c.setFont("Helvetica", 11)
        y = 760

        lines = [
            f"Booking ID: {booking.id}",
            f"Name: {booking.name}",
            f"Phone: {booking.phone}",
            f"Category: {booking.category}",
            f"Date: {format_date_readable(booking.date)}",
            f"Time: {booking.slot_readable}",
            f"Amount Paid: ₹{booking.amount}",
            f"Payment ID: {booking.razorpay_payment_id}",
            "Status: PAID",
        ]

        for line in lines:
            c.drawString(50, y, line)
            y -= 20

        c.showPage()
        c.save()

    # -------------------------------------------------
    # Mark receipt as generated (DB update)
    # -------------------------------------------------
    db = SessionLocal()
    try:
        booking = db.merge(booking)
        booking.receipt_generated = True
        db.commit()
    finally:
        db.close()

    return file_path
