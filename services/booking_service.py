import uuid
import razorpay
from datetime import datetime, timedelta

from models import Booking, Rating
from db import SessionLocal
from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ---------------------------------------------------------
# Generate next 7 calendar days for WhatsApp list selector
# ---------------------------------------------------------
def generate_dates_calendar():
    today = datetime.utcnow()
    rows = []

    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        title = d.strftime("%d %b (%a)")

        rows.append({
            "id": f"date_{date_str}",
            "title": title,
            "description": "Select this date"
        })

    return rows


# ---------------------------------------------------------
# Time-slots list for selected date
# ---------------------------------------------------------
def generate_slots_calendar(date_str):
    slots = [
        ("slot_10_11", "10:00 AM – 11:00 AM"),
        ("slot_12_1", "12:00 PM – 1:00 PM"),
        ("slot_3_4", "3:00 PM – 4:00 PM"),
        ("slot_6_7", "6:00 PM – 7:00 PM"),
        ("slot_8_9", "8:00 PM – 9:00 PM"),
    ]

    rows = []
    for slot_id, title in slots:
        rows.append({
            "id": slot_id,
            "title": title,
            "description": f"Available on {date_str}"
        })
    return rows


# ---------------------------------------------------------
# Create booking (PENDING) + dummy payment URL
# ---------------------------------------------------------
def create_booking_temp(db, user, date_str, slot_str):
    booking = Booking(
        user_id=user.id,
        name=user.name,
        city=user.city,
        category=user.category,
        date=date_str,
        slot=slot_str,
        status="pending",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Create Razorpay Payment Link
    payment = razorpay_client.payment_link.create({
        "amount": 49900,  # ₹499 × 100
        "currency": "INR",
        "description": "NyaySetu Legal Consultation",
        "reference_id": str(booking.id),
        "customer": {
            "name": user.name,
            "contact": user.wa_id  # WhatsApp number
        },
        "notify": {
            "sms": True,
            "email": False
        },
        "callback_url": "https://api.nyaysetu.in/payment/success",
        "callback_method": "get"
    })

    payment_link = payment["short_url"]
    booking.payment_link = payment_link
    db.add(booking)
    db.commit()

    return booking, payment_link


# ---------------------------------------------------------
# Mark payment completed (called from webhook later)
# ---------------------------------------------------------
def confirm_booking_after_payment(db, booking: Booking, payment_id: str):
    booking.status = "PAID"
    booking.payment_id = payment_id
    db.add(booking)
    db.commit()


# ---------------------------------------------------------
# After call completion
# ---------------------------------------------------------
def mark_booking_completed(db, booking: Booking):
    booking.status = "COMPLETED"
    db.add(booking)
    db.commit()


# ---------------------------------------------------------
# Ask rating buttons text
# ---------------------------------------------------------
def ask_rating_buttons():
    return (
        "⭐ How was your consultation experience?\n"
        "Please rate from 1–5 (just type a number):\n"
        "1️⃣ Very Bad\n"
        "2️⃣ Bad\n"
        "3️⃣ Average\n"
        "4️⃣ Good\n"
        "5️⃣ Excellent"
    )


# ---------------------------------------------------------
# Save rating
# ---------------------------------------------------------
def save_rating(db, user, booking: Booking, score: int):
    rating = Rating(
        whatsapp_id=user.whatsapp_id,
        booking_id=booking.id,
        score=score
    )
    db.add(rating)
    db.commit()
