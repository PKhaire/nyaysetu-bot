# services/booking_service.py

from datetime import datetime, timedelta
import uuid

from config import BOOKING_PRICE, BOOKING_CUTOFF_HOURS
from models import Booking   # ✅ REQUIRED IMPORT

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


def generate_slots_calendar(date_str: str):
    return [
        {
            "id": f"slot_{code}",
            "title": readable,
            "description": f"Available on {date_str}"
        }
        for code, readable in SLOT_MAP.items()
    ]


# --------------------
# Slot validation (FIXED)
# --------------------
def validate_slot(date_str: str, slot_code: str):
    if slot_code not in SLOT_START_HOUR:
        return False, "Invalid slot selected."

    now = datetime.now()
    booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    slot_hour = SLOT_START_HOUR[slot_code]

    slot_dt = datetime.combine(
        booking_date,
        datetime.min.time()
    ).replace(hour=slot_hour)

    # ❌ Slot already started
    if booking_date == now.date() and slot_dt <= now:
        return False, "Cannot book a slot that has already started or passed."

    # ⏳ Cutoff applies ONLY for same day
    if booking_date == now.date():
        cutoff_time = now + timedelta(hours=BOOKING_CUTOFF_HOURS)
        if slot_dt <= cutoff_time:
            return False, (
                f"Slot must be booked at least "
                f"{BOOKING_CUTOFF_HOURS} hours in advance."
            )

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
        paid=False,
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

    booking.paid = True
    db.commit()

    return booking, "confirmed"
