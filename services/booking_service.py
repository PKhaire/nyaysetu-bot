# services/booking_service.py
import os
import uuid
from datetime import datetime, timedelta

from models import Booking
from sqlalchemy.orm import Session

# Payment base url used to generate a link. Replace with live integration later.
PAY_BASE_URL = os.getenv("PAY_BASE_URL", "https://pay.nyaysetu.in")

def _make_booking_ref() -> str:
    return "BK-" + uuid.uuid4().hex[:12].upper()

def generate_dates_calendar(days=7):
    """
    Returns a list of rows for WhatsApp list picker for the next `days`.
    Each row is dict: {'id': 'date_YYYY-MM-DD', 'title': 'DD Mon (Day)', 'description': 'Tap to select this date'}
    """
    rows = []
    today = datetime.utcnow().date()
    for i in range(days):
        d = today + timedelta(days=i)
        id_ = f"date_{d.isoformat()}"
        title = d.strftime("%d %b (%a)")
        rows.append({
            "id": id_,
            "title": title,
            "description": "Tap to select this date"
        })
    return rows

def generate_slots_calendar(date_str: str):
    """
    Given date string (YYYY-MM-DD) returns time-slot rows for that date.
    Each row is dict: {'id': 'slot_8_9', 'title': '8:00 PM – 9:00 PM', 'description': 'Available on YYYY-MM-DD'}
    """
    # Basic fixed slots - update as needed
    slots = [
        ("10_11", "10:00 AM – 11:00 AM"),
        ("12_1", "12:00 PM – 1:00 PM"),
        ("3_4", "3:00 PM – 4:00 PM"),
        ("6_7", "6:00 PM – 7:00 PM"),
        ("8_9", "8:00 PM – 9:00 PM"),
    ]
    rows = []
    for code, title in slots:
        rows.append({
            "id": f"slot_{code}",
            "title": title,
            "description": f"Available on {date_str}"
        })
    return rows

def create_booking_temp(db: Session, user, name: str, city: str, category: str, date: str, slot: str, price: float = 499.0):
    """
    Creates a booking row with status PENDING and returns (booking_obj, payment_link)
    This function accepts SQLAlchemy session `db` and a `user` object (SQLAlchemy User).
    """
    # create booking DB object
    booking_ref = _make_booking_ref()
    # human readable slot (store code in slot)
    slot_code = slot.replace("slot_", "") if slot else slot
    booking = Booking(
        booking_ref=booking_ref,
        whatsapp_id=user.whatsapp_id,
        case_id=user.case_id,
        name=name,
        city=city,
        category=category,
        date=date,
        slot=slot_code,
        price=float(price),
        status="PENDING",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # generate a simple payment link (placeholder) - replace with Razorpay / real provider
    payment_link = f"{PAY_BASE_URL}/{booking_ref}"
    # save link
    booking.payment_link = payment_link
    db.add(booking)
    db.commit()
    db.refresh(booking)

    return booking, payment_link

def confirm_booking_after_payment(db: Session, booking_ref: str, external_payment_id: str = None):
    """
    Mark booking as PAID/CONFIRMED. Returns booking or None.
    This method should be invoked by payment webhook.
    """
    booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
    if not booking:
        return None
    booking.status = "PAID"
    if external_payment_id:
        booking.payment_reference = external_payment_id
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking

def mark_booking_completed(db: Session, booking_ref: str):
    booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
    if not booking:
        return None
    booking.status = "CONFIRMED"
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking

def ask_rating_buttons():
    # Return sample buttons structure for whatsapp_service.send_buttons
    return [
        {"id": "rating_1", "title": "1"},
        {"id": "rating_2", "title": "2"},
        {"id": "rating_3", "title": "3"},
        {"id": "rating_4", "title": "4"},
        {"id": "rating_5", "title": "5"},
    ]
