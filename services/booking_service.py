# services/booking_service.py
import random
import string
from datetime import datetime, timedelta
import json
import os
import logging
from db import SessionLocal
from models import Booking, User
from config import BOOKING_PRICE, BOOKING_CUTOFF_HOURS, BOOKING_MAX_AHEAD_DAYS, BOOKING_MAX_PER_DAY, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

logger = logging.getLogger("services.booking_service")

# slot mapping and times (24h start)
SLOT_MAP = {
    "10_11": "10:00 AM – 11:00 AM",
    "12_1": "12:00 PM – 1:00 PM",
    "3_4": "3:00 PM – 4:00 PM",
    "6_7": "6:00 PM – 7:00 PM",
    "8_9": "8:00 PM – 9:00 PM",
}
SLOT_START_HOUR = {
    "10_11": 10,
    "12_1": 12,
    "3_4": 15,
    "6_7": 18,
    "8_9": 20,
}

# small sample states/districts. Add full JSON in data/india_states_districts.json
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data")
if not os.path.exists(DATA_PATH):
    os.makedirs(DATA_PATH)

SAMPLE_INDIAN_LOCATIONS = {
    "Maharashtra": ["Pune", "Mumbai", "Nashik"],
    "Karnataka": ["Bengaluru", "Mysore"],
}
# Save sample if not present
SAMPLE_FILE = os.path.join(DATA_PATH, "india_states_districts.json")
if not os.path.exists(SAMPLE_FILE):
    with open(SAMPLE_FILE, "w") as f:
        json.dump(SAMPLE_INDIAN_LOCATIONS, f, indent=2)

# caching loader
_states_cache = None
def load_states():
    global _states_cache
    if _states_cache is not None:
        return _states_cache
    try:
        with open(SAMPLE_FILE, "r") as f:
            _states_cache = json.load(f)
    except Exception:
        _states_cache = SAMPLE_INDIAN_LOCATIONS
    return _states_cache

def generate_dates_calendar(days=7):
    """Return list of rows for next 'days' days (id,title,description)"""
    rows = []
    today = datetime.now().date()
    for i in range(days):
        d = today + timedelta(days=i)
        rows.append({
            "id": f"date_{d.isoformat()}",
            "title": d.strftime("%d %b (%a)"),
            "description": "Select this date"
        })
    return rows

def generate_slots_calendar(date_str):
    """
    Return rows list for Slack style list picker.
    Apply rule: if slot start time is already past or within cutoff, exclude (or will be validated on booking).
    """
    rows = []
    # parse date
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        date_obj = datetime.now().date()
    now = datetime.now()
    for code, readable in SLOT_MAP.items():
        start_hour = SLOT_START_HOUR.get(code, 0)
        slot_start_dt = datetime.combine(date_obj, datetime.min.time()) + timedelta(hours=start_hour)
        # Format title and description
        rows.append({"id": f"slot_{code}", "title": readable, "description": f"Available on {date_str}"})
    return rows

# helpers for validations
def _slot_start_datetime(date_str, slot_code):
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        date_obj = datetime.now().date()
    hour = SLOT_START_HOUR.get(slot_code, 0)
    return datetime.combine(date_obj, datetime.min.time()) + timedelta(hours=hour)

def _random_token(length=32):
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))

# create booking: returns (BookingObj, payment_link_or_message)
def create_booking_temp(db, user, name, city, category, date_str, slot_code):
    """
    Validations implemented (selected subset per request):
    - No booking within BOOKING_CUTOFF_HOURS of slot start.
    - No duplicate booking by same user for same date+slot.
    - Max ahead days limit.
    - Max bookings per day enforced.
    - Prevent booking if a confirmed booking already exists for same slot (global).
    Returns (None, "reason message") on validation failure.
    On success, creates a Booking row with status 'pending' and returns payment link.
    """
    # 1) date range check
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None, "Invalid date format."

    now = datetime.now()
    slot_dt = _slot_start_datetime(date_str, slot_code)

    # rule: max ahead days
    if (date_obj - now.date()).days < 0:
        return None, "Cannot book a past date."
    if (date_obj - now.date()).days > BOOKING_MAX_AHEAD_DAYS:
        return None, f"Cannot book more than {BOOKING_MAX_AHEAD_DAYS} days ahead."

    # rule: cutoff hours
    hours_before_start = (slot_dt - now).total_seconds() / 3600.0
    if hours_before_start < BOOKING_CUTOFF_HOURS:
        return None, "Cannot book a slot that has already started or is within cutoff time."

    # enforce daily capacity and duplicates
    # count bookings (confirmed or pending) for that date
    q_same_slot = db.query(Booking).filter(Booking.date == date_str, Booking.slot_code == slot_code, Booking.status == "confirmed")
    if q_same_slot.count() >= 1:
        # Option: if you allow multiple per slot, compute capacity differently. For now treat slot as single capacity.
        return None, "Slot already booked. Please pick another slot."

    # check user duplicate
    q_user = db.query(Booking).filter(Booking.whatsapp_id == user.whatsapp_id, Booking.date == date_str, Booking.slot_code == slot_code, Booking.status != "cancelled")
    if q_user.count() > 0:
        return None, "You already have a booking for this slot."

    # check total bookings that day
    q_day = db.query(Booking).filter(Booking.date == date_str, Booking.status == "confirmed")
    if q_day.count() >= BOOKING_MAX_PER_DAY:
        return None, "No more bookings available on this date."

    # create booking pending
    token = _random_token(20)
    booking = Booking(
        user_id=user.id,
        whatsapp_id=user.whatsapp_id,
        name=name,
        city=city,
        category=category,
        date=date_str,
        slot_code=slot_code,
        slot_readable=SLOT_MAP.get(slot_code, slot_code),
        price=float(BOOKING_PRICE),
        status="pending",
        payment_token=token
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # generate payment link
    payment_link = _make_payment_link(booking)
    return booking, payment_link

def _make_payment_link(booking: Booking):
    """
    If Razorpay keys present, create an order and return a small link (not full checkout). Otherwise return test URL with token.
    """
    if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
        try:
            import razorpay
            client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
            order = client.order.create(dict(amount=int(booking.price * 100), currency="INR", receipt=str(booking.id), payment_capture=1))
            # return a simple redirect to a de-facto checkout page you host (not implemented here).
            return f"https://pay.nyaysetu.in/{booking.payment_token}"  # placeholder, integrate client-side checkout
        except Exception as e:
            logger.exception("Razorpay order creation failed")
            return f"https://pay.nyaysetu.in/{booking.payment_token}"
    return f"https://pay.nyaysetu.in/{booking.payment_token}"

def confirm_booking_after_payment(db, token: str):
    """
    Confirm booking given a payment token (called from payment webhook).
    Returns (booking, "ok") or (None, "reason").
    """
    booking = db.query(Booking).filter(Booking.payment_token == token).first()
    if not booking:
        return None, "Booking not found."
    if booking.status == "confirmed":
        return booking, "already_confirmed"
    # Mark confirmed
    booking.status = "confirmed"
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking, "confirmed"
