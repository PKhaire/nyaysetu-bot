# services/booking_service.py
from datetime import datetime, timedelta
import uuid
from config import BOOKING_PRICE, BOOKING_CUTOFF_HOURS

SLOT_MAP = {
    "10_11": "10:00 AM – 11:00 AM",
    "12_1": "12:00 PM – 1:00 PM",
    "3_4": "3:00 PM – 4:00 PM",
    "6_7": "6:00 PM – 7:00 PM",
    "8_9": "8:00 PM – 9:00 PM",
}

def create_token():
    return uuid.uuid4().hex

def generate_dates_calendar():
    today = datetime.now()
    rows = []
    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        label = d.strftime("%d %b (%a)")
        rows.append({
            "id": f"date_{date_str}",
            "title": label,
            "description": "Select this date"
        })
    return rows

def generate_slots_calendar(date_str: str):
    rows = []
    for code, readable in SLOT_MAP.items():
        rows.append({
            "id": f"slot_{code}",
            "title": readable,
            "description": f"Available on {date_str}"
        })
    return rows

def validate_slot(date_str, slot_code):
    today = datetime.now()

    slot_start_map = {
        "10_11": 10,
        "12_1": 12,
        "3_4": 15,
        "6_7": 18,
        "8_9": 20,
    }

    if slot_code not in slot_start_map:
        return False, "Invalid slot selected."

    slot_hour = slot_start_map[slot_code]
    slot_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=slot_hour, minute=0)

    if slot_dt <= today:
        return False, "Cannot book a slot that has already started or passed."

    cutoff_dt = today + timedelta(hours=BOOKING_CUTOFF_HOURS)
    if slot_dt <= cutoff_dt:
        return False, f"Slot must be booked at least {BOOKING_CUTOFF_HOURS} hours in advance."

    return True, None

def create_booking_temp(db, user, name, state, district, category, date, slot_code):
    ok, msg = validate_slot(date, slot_code)
    if not ok:
        return None, msg

    token = create_token()

    booking = Booking(
        whatsapp_id=user.whatsapp_id,
        name=name,
        state=state,
        district=district,
        category=category,
        date=date,
        slot_code=slot_code,
        slot_readable=SLOT_MAP.get(slot_code),
        payment_token=token
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return booking, f"https://pay.nyaysetu.in/{token}"

def confirm_booking_after_payment(db, token):
    booking = db.query(Booking).filter_by(payment_token=token).first()
    if not booking:
        return None, "Booking not found."

    booking.paid = True
    db.add(booking)
    db.commit()
    return booking, "confirmed"
