# services/booking_service.py

from datetime import datetime, date, time, timedelta
import uuid

from config import BOOKING_PRICE, BOOKING_CUTOFF_HOURS
from models import Booking   # ✅ REQUIRED IMPORT

SLOT_BUFFER_HOURS = 2  # Same buffer as backend


# --------------------
# Slot configuration
# --------------------
SLOT_MAP = {
    "10_11": "10:00 AM – 11:00 AM",
    "12_1":  "12:00 PM – 1:00 PM",
    "3_4":   "3:00 PM – 4:00 PM",
    "6_7":   "6:00 PM – 7:00 PM",
    "8_9":   "8:00 PM – 9:00 PM",
}

SLOT_START_HOUR = {
    "10_11": 10,
    "12_1": 12,
    "3_4": 15,
    "6_7": 18,
    "8_9": 20,
}

# --------------------
# Helpers
# --------------------
def create_token():
    return uuid.uuid4().hex


# --------------------
# Calendar generators
# --------------------
def generate_dates_calendar():
    today = datetime.now().date()
    rows = []

    for i in range(7):
        d = today + timedelta(days=i)
        rows.append({
            "id": f"date_{d.isoformat()}",
            "title": d.strftime("%d %b (%a)"),
            "description": "Select this date"
        })

    return rows

def generate_slots_calendar(date_str):
    today = date.today()
    now = datetime.now()

    booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    min_allowed_time = now + timedelta(hours=SLOT_BUFFER_HOURS)

    rows = []

    for code, label in SLOT_MAP.items():
        slot_start_hour = int(code.split("_")[0])
        slot_start_dt = datetime.combine(
            booking_date, time(slot_start_hour, 0)
        )

        # Hide slots violating buffer for today
        if booking_date == today and slot_start_dt < min_allowed_time:
            continue

        rows.append({
            "id": f"slot_{code}",
            "title": label,
            "description": f"Available on {date_str}",
        })

    return rows


# --------------------
# Time slot validation
# --------------------
from datetime import datetime, date, time, timedelta

SLOT_BUFFER_HOURS = 2  # Minimum buffer from current time

def validate_slot(date_str, slot_code):
    """
    Reject past slots and enforce minimum 2-hour buffer.
    """
    try:
        booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return False, "Invalid booking date."

    if slot_code not in SLOT_MAP:
        return False, "Invalid time slot."

    now = datetime.now()
    today = date.today()

    # Past date not allowed
    if booking_date < today:
        return False, "This date has already passed."

    # Today → enforce buffer
    if booking_date == today:
        slot_start_hour = int(slot_code.split("_")[0])
        slot_start_dt = datetime.combine(
            today, time(slot_start_hour, 0)
        )

        min_allowed_time = now + timedelta(hours=SLOT_BUFFER_HOURS)

        if slot_start_dt < min_allowed_time:
            return False, "Please select a time slot at least 2 hours from now."

    return True, None

# --------------------
# Booking creation
# --------------------
def create_booking_temp(db, user, name, state, district, category, date, slot_code):
    ok, error = validate_slot(date, slot_code)
    if not ok:
        return None, error

    token = create_token()

    booking = Booking(
        whatsapp_id=user.whatsapp_id,
        name=name,
        state_name=state,
        district_name=district,
        category=category,
        date=date,
        slot_code=slot_code,
        slot_readable=SLOT_MAP[slot_code],
        payment_token=token,
        status="PENDING",
        created_at=datetime.utcnow()
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return booking, f"https://pay.nyaysetu.in/{token}"


# --------------------
# Payment confirmation
# --------------------
def confirm_booking_after_payment(db, token):
    booking = db.query(Booking).filter_by(payment_token=token).first()
    if not booking:
        return None, "Booking not found."
        
    booking.status = "PAID"
    db.commit()

    return booking, "confirmed"
