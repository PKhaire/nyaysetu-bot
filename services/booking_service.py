# services/booking_service.py

from datetime import datetime, date, time, timedelta
import uuid
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")
import razorpay
from config import BOOKING_PRICE, BOOKING_CUTOFF_HOURS, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
from models import Booking   # ✅ REQUIRED IMPORT
from db import SessionLocal

SLOT_BUFFER_HOURS = 2  # Same buffer as backend

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)

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
def generate_dates_calendar(skip_today=False):
    today = datetime.now(IST).date()
    rows = []

    # Skip today if required (late-evening buffer case)
    start_offset = 1 if skip_today else 0

    for i in range(start_offset, 7):
        d = today + timedelta(days=i)

        rows.append({
            "id": f"date_{d.isoformat()}",
            "title": d.strftime("%d %b (%a)"),
            "description": "Select this date",
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
        phone=user.whatsapp_id,              
        district_name=district,
        category=category,
        date=datetime.strptime(date, "%Y-%m-%d").date(),
        slot_code=slot_code,
        slot_readable=SLOT_MAP[slot_code],
        amount=BOOKING_PRICE,                
        status="PENDING",
        created_at=datetime.utcnow()
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    # 🔐 CREATE RAZORPAY PAYMENT LINK
    payment_link = razorpay_client.payment_link.create({
        "amount": BOOKING_PRICE * 100,  # paisa
        "currency": "INR",
        "accept_partial": False,
        "description": "NyaySetu Legal Consultation",
        "customer": {
            "name": name,
            "contact": user.whatsapp_id
        },
        "notify": {
            "sms": False,
            "email": False
        },
        "notes": {
            "booking_token": token
        }
    })

    # Save Razorpay reference
    booking.razorpay_payment_link_id = payment_link["id"]
    db.commit()

    return booking, payment_link["short_url"]

# --------------------
# Payment confirmation
# --------------------
def confirm_booking_after_payment(db, token):
    booking = db.query(Booking).filter_by(payment_token=token).first()
    # ⏳ Expire payment link after 15 minutes
    if booking.created_at < datetime.utcnow() - timedelta(minutes=15):
        return None, "Payment link expired"
        
    if not booking:
        return None, "Booking not found."

    if booking.status == "PAID":
        return booking, "Already confirmed"

    booking.status = "PAID"
    db.commit()

    return booking, "confirmed"

def is_payment_already_processed(payment_id):
    from db import SessionLocal
    from models import Booking

    db = SessionLocal()
    try:
        return (
            db.query(Booking)
            .filter(Booking.razorpay_payment_id == payment_id)
            .first()
            is not None
        )
    finally:
        db.close()


def confirm_booking_payment(payment_link_id, payment_id, payment_mode):
    from db import SessionLocal
    from models import Booking
    from datetime import datetime

    db = SessionLocal()
    try:
        booking = (
            db.query(Booking)
            .filter(
                Booking.razorpay_payment_link_id == payment_link_id,
                Booking.status == "PENDING"
            )
            .first()
        )

        if not booking:
            return False

        booking.status = "PAID"
        booking.razorpay_payment_id = payment_id
        booking.payment_mode = payment_mode
        booking.paid_at = datetime.utcnow()

        db.commit()
        return True

    finally:
        db.close()
        
# --------------------
# FINAL PAYMENT CONFIRMATION (USED BY WEBHOOK)
# --------------------
def mark_booking_as_paid(payment_link_id, payment_id, payment_mode):
    db = SessionLocal()
    try:
        booking = (
            db.query(Booking)
            .filter(Booking.razorpay_payment_link_id == payment_link_id)
            .first()
        )

        if not booking:
            return None

        # 🔐 FINAL IDEMPOTENCY LOCK
        if booking.payment_processed:
            return booking

        booking.status = "PAID"
        booking.razorpay_payment_id = payment_id
        booking.payment_mode = payment_mode
        booking.payment_processed = True
        booking.paid_at = datetime.utcnow()

        db.commit()
        db.refresh(booking)
        return booking

    finally:
        db.close()
