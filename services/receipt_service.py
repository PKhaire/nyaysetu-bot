# services/receipt_service.py

import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

RECEIPT_DIR = "receipts"

def generate_pdf_receipt(booking):
    os.makedirs(RECEIPT_DIR, exist_ok=True)

    file_path = f"{RECEIPT_DIR}/receipt_{booking.id}.pdf"
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
        f"Date: {booking.date}",
        f"Time: {booking.slot_readable}",
        f"Amount Paid: ₹{booking.amount}",
        f"Payment ID: {booking.razorpay_payment_id}",
        f"Status: PAID",
    ]

    for line in lines:
        c.drawString(50, y, line)
        y -= 20

    c.showPage()
    c.save()

    return file_path

def generate_pdf_receipt(booking):
    try:
        # existing PDF logic
        pdf_path = create_pdf_somehow(booking)

        db = SessionLocal()
        booking = db.merge(booking)
        booking.receipt_generated = True
        db.commit()
        db.close()

        return pdf_path

    except Exception:
        raise

