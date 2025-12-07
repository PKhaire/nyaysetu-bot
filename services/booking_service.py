import logging
from datetime import datetime, timedelta
import razorpay
from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
from db import get_db
from sqlalchemy.orm import Session
from models import Booking

PRICE = 499  # Fixed consultation price


def generate_dates_calendar():
    dates = []
    today = datetime.now()
    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%b %d (%a)")
        dates.append({"id": f"date_{date_str}", "title": date_str})
    return dates


def generate_slots():
    slots = []
    for hour in range(10, 21):
        time_label = datetime.strptime(str(hour), "%H").strftime("%I:00 %p")
        slots.append({"id": f"slot_{time_label}", "title": time_label})
    return slots


def generate_slots_calendar():
    return generate_slots()


# ---------------------------------------------------
# Create booking temporarily and generate payment
# ---------------------------------------------------
def create_booking_and_payment(user, date_choice, slot_choice):
    db: Session = next(get_db())

    # Save temporary booking
    booking = Booking(
        user_id=user.whatsapp_id,
        date=date_choice,
        slot=slot_choice,
        status="pending"
    )
    db.add(booking)
    db.commit()

    # Razorpay order
    try:
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

        order = client.order.create({
            "amount": PRICE * 100,
            "currency": "INR",
            "receipt": f"NS-{user.whatsapp_id}",
            "payment_capture": 1
        })

        payment_url = f"https://rzp.io/i/{order['id']}"
        logging.info(f"Razorpay Order created: {order['id']}")

        return {
            "success": True,
            "payment_url": payment_url,
            "amount": PRICE
        }

    except Exception as e:
        logging.error(f"Payment error: {e}")
        return {"success": False, "error": str(e)}
