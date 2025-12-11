# booking_service.py
from datetime import datetime, timedelta, time as dt_time
import random
import string
from typing import List, Tuple

# import models at runtime to avoid circular imports in some setups
from models import Booking, User  # ensure models.py defines these properly

# ---------- Helpers & Constants ----------
SLOTS = [
    ("10_11", "10:00 AM – 11:00 AM", 10),
    ("12_1",  "12:00 PM – 1:00 PM", 12),
    ("3_4",   "3:00 PM – 4:00 PM", 15),
    ("6_7",   "6:00 PM – 7:00 PM", 18),
    ("8_9",   "8:00 PM – 9:00 PM", 20),
]

def _today():
    return datetime.now().date()

def _now():
    return datetime.now()

# ---------- Date / Slot generation & validation ----------
def generate_dates_calendar() -> List[dict]:
    """
    Returns rows for next 7 days (as list of dicts for WhatsApp list picker).
    Excludes today if too late (for ex if current time > last slot start).
    """
    rows = []
    now = _now()
    for i in range(0, 7):
        d = now.date() + timedelta(days=i)
        # Decide whether to include today:
        include = True
        if i == 0:
            # If current time is after last slot start (20:00) exclude today
            last_slot_hour = max(s[2] for s in SLOTS)
            if now.hour >= last_slot_hour:
                include = False
        if not include:
            continue
        rows.append({
            "id": f"date_{d.isoformat()}",
            "title": d.strftime("%d %b (%a)"),
            "description": "Tap to select this date"
        })
    return rows

def generate_slots_calendar(date_str: str) -> List[dict]:
    """
    Given date_str in YYYY-MM-DD returns available slot rows.
    Hides slots whose start time is already past when date == today.
    """
    rows = []
    now = _now()
    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return rows

    for code, readable, hour in SLOTS:
        slot_dt = datetime.combine(selected_date, dt_time(hour=hour))
        # Rule 1: if selected_date==today and slot time < now -> skip
        if selected_date == now.date() and slot_dt <= now:
            continue
        rows.append({
            "id": f"slot_{code}",
            "title": readable,
            "description": f"Available on {date_str}"
        })

    return rows

def validate_date_str(date_str: str) -> bool:
    """Validate date within [today..today+7] and proper format."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return False
    today = _today()
    if d < today:
        return False
    if d > today + timedelta(days=7):
        return False
    return True

# ---------- Booking business logic ----------
def user_has_active_booking(db, user_id: int) -> bool:
    """Return True if user has PENDING or CONFIRMED booking."""
    q = db.query(Booking).filter(
        Booking.user_id == user_id,
        Booking.status.in_(["PENDING", "CONFIRMED"])
    ).first()
    return q is not None

def user_unpaid_count_last_24h(db, user_id: int) -> int:
    cutoff = _now() - timedelta(hours=24)
    return db.query(Booking).filter(
        Booking.user_id == user_id,
        Booking.status == "PENDING",
        Booking.created_at >= cutoff
    ).count()

def latest_user_booking(db, user_id: int):
    return db.query(Booking).filter(
        Booking.user_id == user_id
    ).order_by(Booking.created_at.desc()).first()

def parse_slot_to_datetime(date_str: str, slot_code: str) -> datetime:
    """
    Convert date_str and slot_code like '8_9' to a datetime representing slot start.
    If slot_code is already readable, best-effort parse.
    """
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None
    # expect slot_code like "8_9" or "12_1"
    if "_" in slot_code:
        hour = int(slot_code.split("_")[0])
    else:
        # fallback: try to extract leading hour integer
        try:
            hour = int(slot_code.split(":")[0])
        except Exception:
            hour = 10
    return datetime.combine(d, dt_time(hour=hour))

def auto_cancel_unpaid_bookings(db):
    """
    Cancel bookings in PENDING older than 15 minutes. Returns count.
    """
    threshold = _now() - timedelta(minutes=15)
    expired = db.query(Booking).filter(
        Booking.status == "PENDING",
        Booking.created_at < threshold
    ).all()
    count = 0
    for b in expired:
        b.status = "CANCELLED"
        count += 1
    if count:
        db.commit()
    return count

# ---------- Booking creation (temporary pending with payment link) ----------
def _generate_payment_token(length=32):
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))

def create_booking_temp(db, user, name: str, city: str, category: str, date: str, slot: str, price: int = 499) -> Tuple[Booking, str]:
    """
    Create a Booking row in PENDING status and return (booking, payment_link).
    Payment link is generated by a simple token + app URL (you should replace with Razorpay logic).
    """
    # For safety: ensure slot is valid for the date (double-check)
    if not validate_date_str(date):
        raise ValueError("Invalid date")

    # avoid double booking race: check again
    if user_has_active_booking(db, user.id):
        raise ValueError("User already has an active booking")

    # create booking
    token = _generate_payment_token()
    payment_link = f"https://pay.nyaysetu.in/{token}"  # replace with real provider link or Razorpay order id
    booking = Booking(
        user_id=user.id,
        date_str=date,
        slot_str=slot,
        status="PENDING",
        created_at=_now(),
        payment_id=None,
        price=price,
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    # store link on user (optional)
    try:
        user.last_payment_link = payment_link
        db.add(user)
        db.commit()
    except Exception:
        db.rollback()

    return booking, payment_link

def confirm_booking_after_payment(db, payment_id: str, booking_id: int, razorpay_payload=None) -> bool:
    """
    Mark booking as CONFIRMED when payment provider confirms. Returns True on success.
    """
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        return False
    b.status = "CONFIRMED"
    b.payment_id = payment_id
    db.add(b)
    db.commit()
    return True

def mark_booking_completed(db, booking_id: int):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        return False
    b.status = "COMPLETED"
    db.add(b)
    db.commit()
    return True

# ---------- Small utility to map slot code to readable ----------
def slot_code_to_readable(code: str) -> str:
    for c, readable, _ in SLOTS:
        if c == code:
            return readable
    return code
