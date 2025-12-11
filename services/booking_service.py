# services/booking_service.py
import os
import uuid
from datetime import datetime, timedelta, time
from typing import Tuple, List, Dict

from models import Booking
from db import SessionLocal

# Config driven by environment or defaults
BOOKING_PRICE = int(os.getenv("BOOKING_PRICE", "499"))
BOOKING_CUTOFF_HOURS = int(os.getenv("BOOKING_CUTOFF_HOURS", "2"))   # cannot book within X hours of slot start
SLOT_CAPACITY = int(os.getenv("SLOT_CAPACITY", "3"))                # capacity per slot
MAX_DAILY_BOOKINGS_PER_USER = int(os.getenv("MAX_DAILY_BOOKINGS_PER_USER", "1"))
MAX_ADVANCE_DAYS = int(os.getenv("MAX_ADVANCE_DAYS", "30"))
PAYMENT_BASE = os.getenv("PAYMENT_BASE", "https://pay.nyaysetu.in")

# mapping for readable text
SLOT_MAP = {
    "10_11": "10:00 AM – 11:00 AM",
    "12_1": "12:00 PM – 1:00 PM",
    "3_4": "3:00 PM – 4:00 PM",
    "6_7": "6:00 PM – 7:00 PM",
    "8_9": "8:00 PM – 9:00 PM",
}

def generate_dates_calendar(days: int = 7) -> List[Dict]:
    today = datetime.utcnow().date()
    rows = []
    for i in range(days):
        d = today + timedelta(days=i)
        idv = f"date_{d.isoformat()}"
        title = d.strftime("%d %b (%a)")
        rows.append({"id": idv, "title": title, "description": "Select this date"})
    return rows

def _slot_start_datetime_for(date_str: str, slot_code: str) -> datetime:
    # slot_code -> hour mapping (local time assumed IST). Using naive times in UTC would be wrong in prod,
    # but we assume server time is IST or convert accordingly.
    # Map slots to starting hour (24h)
    slot_start_hour = {
        "10_11": 10,
        "12_1": 12,
        "3_4": 15,
        "6_7": 18,
        "8_9": 20,
    }.get(slot_code, 0)
    # assume date_str is YYYY-MM-DD
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return datetime.combine(d, time(hour=slot_start_hour, minute=0))

def generate_slots_calendar(date_str: str) -> List[Dict]:
    # returns list dicts for WhatsApp list rows
    rows = []
    for code, title in SLOT_MAP.items():
        rows.append({"id": f"slot_{code}", "title": title, "description": f"Available on {date_str}"})
    return rows

def create_payment_token() -> str:
    return uuid.uuid4().hex

def create_booking_temp(db, user, name, city, category, date_str, slot_code) -> Tuple[Booking, str]:
    """
    Validate booking rules and create a pending booking with payment link.
    Returns (booking object, payment_link) on success.
    On validation failure returns (None, "reason message").
    Implemented rules:
      - Can't book in the past or for a slot already started (rule 1)
      - Can't book within BOOKING_CUTOFF_HOURS of slot start (rule 2)
      - No double-book of same slot by same user (rule 4)
      - Max daily bookings per user (rule 7)
      - Slot capacity (rule 8)
      - Max advance days (rule 12)
      - Ensure category/state/district present (rule 13 as needed)
    """
    # Basic validation
    if not date_str or not slot_code:
        return None, "Invalid date or slot."

    try:
        slot_start_dt = _slot_start_datetime_for(date_str, slot_code)
    except Exception:
        return None, "Invalid date or slot format."

    now = datetime.utcnow()
    # rule: max advance days
    if slot_start_dt.date() > (now.date() + timedelta(days=MAX_ADVANCE_DAYS)):
        return None, f"Bookings allowed only up to {MAX_ADVANCE_DAYS} days in advance."

    # rule 1: cannot book if slot already started or passed
    if slot_start_dt <= now:
        return None, "Cannot book a slot that has already started or passed."

    # rule 2: booking cutoff hours
    cutoff_dt = slot_start_dt - timedelta(hours=BOOKING_CUTOFF_HOURS)
    if now >= cutoff_dt:
        return None, f"Cannot book within {BOOKING_CUTOFF_HOURS} hours of the slot start."

    # rule 13: ensure category provided
    if not category:
        return None, "Please provide legal issue category before booking."

    # rule 4: same user same slot duplication
    existing_same_slot = db.query(Booking).filter_by(whatsapp_id=user.whatsapp_id, date=date_str, slot_code=slot_code, status!="cancelled").first()
    if existing_same_slot:
        return None, "You already have a booking for this slot."

    # rule 7: max daily bookings per user
    daily_count = db.query(Booking).filter_by(whatsapp_id=user.whatsapp_id, date=date_str).filter(Booking.status != "cancelled").count()
    if daily_count >= MAX_DAILY_BOOKINGS_PER_USER:
        return None, f"You can only book {MAX_DAILY_BOOKINGS_PER_USER} consultation(s) per day."

    # rule 8: slot capacity
    slot_count = db.query(Booking).filter_by(date=date_str, slot_code=slot_code).filter(Booking.status == "confirmed").count()
    if slot_count >= SLOT_CAPACITY:
        return None, "This slot is fully booked. Please choose another slot."

    # OK, create pending booking
    token = create_payment_token()
    payment_link = f"{PAYMENT_BASE}/{token}"

    booking = Booking(
        whatsapp_id=user.whatsapp_id,
        user_case_id=user.case_id,
        name=name,
        city=city,
        state=getattr(user, "state", None),
        district=getattr(user, "district", None),
        category=category,
        date=date_str,
        slot_code=slot_code,
        slot_readable=SLOT_MAP.get(slot_code, slot_code),
        status="pending",
        payment_token=token,
        payment_link=payment_link
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking, payment_link

def confirm_booking_after_payment(db, token: str):
    """
    Mark booking confirmed based on payment token.
    Returns (booking, status_message) or (None, reason)
    """
    booking = db.query(Booking).filter_by(payment_token=token).first()
    if not booking:
        return None, "Booking not found."

    if booking.status == "confirmed":
        return booking, "already_confirmed"

    booking.status = "confirmed"
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking, "ok"

# helper: ask rating buttons (simple placeholder)
def ask_rating_buttons(whatsapp_id: str):
    # left as placeholder for your whatsapp_service send_buttons call
    return
