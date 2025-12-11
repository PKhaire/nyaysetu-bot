# services/booking_service.py
import uuid
from datetime import datetime, timedelta
from models import Booking, User
from config import BOOKING_PRICE, BOOKING_CUTOFF_HOURS
from db import SessionLocal
from sqlalchemy import and_

# Define available slots (slot_code -> readable)
SLOT_MAP = {
    "10_11": "10:00 AM – 11:00 AM",
    "12_1": "12:00 PM – 1:00 PM",
    "3_4": "3:00 PM – 4:00 PM",
    "6_7": "6:00 PM – 7:00 PM",
    "8_9": "8:00 PM – 9:00 PM",
}

def generate_dates_calendar(days=7):
    today = datetime.utcnow().date()
    rows = []
    for i in range(days):
        d = today + timedelta(days=i)
        rows.append({
            "id": f"date_{d.isoformat()}",
            "title": d.strftime("%d %b (%a)"),
            "description": "Select this date"
        })
    return rows

def generate_slots_calendar(date_str):
    # date_str expected YYYY-MM-DD
    # return list of rows with ids like slot_10_11
    rows = []
    for code, readable in SLOT_MAP.items():
        rows.append({
            "id": f"slot_{code}",
            "title": readable,
            "description": f"Available on {date_str}"
        })
    return rows

def _slot_datetime_from(date_str, slot_code):
    # Attempt to build a datetime for the slot start in UTC (assume local IST offset +5:30)
    # For server-side cutoff comparisons we use naive UTC approximations.
    # slot_code like "12_1" -> start hour 12:00 local.
    # NOTE: For production, store timezone-aware datetimes.
    parts = slot_code.split("_")
    try:
        start_hour = int(parts[0])
    except Exception:
        start_hour = 9
    # date_str is YYYY-MM-DD
    dt = datetime.fromisoformat(date_str)
    # treat the start as local hour; convert to UTC by subtracting 5h30m
    # (This is a simple fix for India; replace with pytz for production)
    local_start = datetime(dt.year, dt.month, dt.day, start_hour, 0, 0)
    utc_start = local_start - timedelta(hours=5, minutes=30)
    return utc_start

def create_booking_temp(db_session, user_obj, name, city, category, date, slot_code, price=BOOKING_PRICE):
    """
    Create a tentative booking and return (booking, payment_link)
    Returns (None, reason_message) if validation fails.
    """
    # validations:
    # 1) date in future and slot start > now + cutoff
    try:
        slot_start_utc = _slot_datetime_from(date, slot_code)
    except Exception as e:
        return None, "Invalid date/slot."

    now = datetime.utcnow()
    cutoff = now + timedelta(hours=BOOKING_CUTOFF_HOURS)
    if slot_start_utc <= now:
        return None, "Cannot book a slot that has already started or passed."
    if slot_start_utc <= cutoff:
        return None, f"Bookings require at least {BOOKING_CUTOFF_HOURS} hours' notice for the selected slot."

    # 2) No duplicate booking for that slot/date
    existing = db_session.query(Booking).filter(
        Booking.date == date,
        Booking.slot_code == slot_code,
        Booking.status.in_(["pending", "confirmed"])
    ).first()
    if existing:
        return None, "Sorry — that slot is already taken. Please choose another slot."

    # 3) Single active booking per user
    active = db_session.query(Booking).filter(
        Booking.whatsapp_id == user_obj.whatsapp_id,
        Booking.status.in_(["pending", "confirmed"])
    ).first()
    if active:
        return None, "You already have an active booking. Only one active session allowed at a time."

    # Create booking row
    booking = Booking(
        whatsapp_id=user_obj.whatsapp_id,
        case_id=user_obj.case_id,
        name=name,
        city=city,
        category=category,
        date=date,
        slot_code=slot_code,
        slot_readable=SLOT_MAP.get(slot_code, slot_code),
        price=price,
        status="pending"
    )
    # make a test payment link (use real gateway to create real links)
    token = uuid.uuid4().hex
    payment_link = f"https://pay.nyaysetu.in/{token}"
    booking.payment_link = payment_link

    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)
    return booking, payment_link

def confirm_booking_after_payment(db_session, payment_token):
    # payment_token corresponds to token part in payment_link above
    # Simple approach: search booking.payment_link endswith token
    booking = db_session.query(Booking).filter(Booking.payment_link.like(f"%{payment_token}")).first()
    if not booking:
        return None, "Booking not found"
    booking.status = "confirmed"
    db_session.add(booking)
    db_session.commit()
    return booking, "confirmed"

def mark_booking_completed(db_session, booking_id):
    booking = db_session.query(Booking).get(booking_id)
    if not booking:
        return False
    booking.status = "completed"
    db_session.add(booking)
    db_session.commit()
    return True

def ask_rating_buttons():
    return [
        {"id": "rate_5", "title": "⭐️⭐️⭐️⭐️⭐️ Excellent"},
        {"id": "rate_4", "title": "⭐️⭐️⭐️⭐️ Good"},
        {"id": "rate_3", "title": "⭐️⭐️⭐ Average"},
        {"id": "rate_2", "title": "⭐️⭐ Poor"},
        {"id": "rate_1", "title": "⭐ Very Bad"},
    ]
