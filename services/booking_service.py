from datetime import datetime, timedelta
from db import get_db
from models import User, Booking
from config import PAYMENT_BASE_URL
from whatsapp_service import send_buttons

# Generate dates (next 7 days)
def generate_dates_calendar():
    dates = []
    today = datetime.now()
    for i in range(7):
        d = today + timedelta(days=i)
        label = d.strftime("%b %d (%a)")
        dates.append({"id": f"date_{label}", "title": label})
    return [{"id": d["id"], "title": d["title"]} for d in dates]

# Generate slots: 10 AM – 8 PM
def generate_slots():
    slots = []
    for hour in range(10, 21):
        t = datetime.strptime(str(hour), "%H").strftime("%I:00 %p")
        slots.append({"id": f"slot_{t}", "title": t})
    return slots


def start_booking_flow(user, wa_id):
    from whatsapp_service import send_list_picker
    send_list_picker(wa_id, "Select Appointment Date", "Choose a date 👇", generate_dates_calendar())


def handle_date_selection(user, wa_id, date_title):
    from whatsapp_service import send_list_picker
    send_list_picker(wa_id, "Select Time Slot", f"Date: {date_title}\nChoose a time 👇", generate_slots())


def handle_slot_selection(user, wa_id, date_title, slot_title):
    db = next(get_db())
    booking = Booking(whatsapp_id=wa_id, date=date_title, slot=slot_title)
    db.add(booking)
    db.commit()

    payment_url = f"{PAYMENT_BASE_URL}?wa_id={wa_id}&booking_id={booking.id}"
    user.last_payment_link = payment_url
    db.commit()

    send_buttons(
        wa_id,
        f"To confirm your appointment on {date_title} at {slot_title}, please complete the payment 👇\nFee: ₹499",
        [("Pay ₹499", payment_url)]
    )


def confirm_booking_after_payment(user, payment_id):
    db = next(get_db())
    booking = db.query(Booking).filter_by(whatsapp_id=user.whatsapp_id, status="PENDING").first()
    if not booking:
        return None
    booking.status = "PAID"
    booking.payment_id = payment_id
    db.commit()
    return booking


def mark_booking_completed(booking_id):
    db = next(get_db())
    booking = db.query(Booking).filter_by(id=booking_id, status="PAID").first()
    if not booking:
        return None
    booking.status = "COMPLETED"
    db.commit()
    return booking
