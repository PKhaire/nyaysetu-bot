# services/booking_service.py
import random
from datetime import datetime, timedelta
from models import Booking
from db import SessionLocal
from config import PAYMENT_BASE_URL

def create_booking_for_user(whatsapp_id, preferred_time):
    db = SessionLocal()
    try:
        otp = f"{random.randint(100000, 999999)}"
        otp_valid_until = datetime.utcnow() + timedelta(minutes=10)
        payment_link = f"{PAYMENT_BASE_URL}?case={whatsapp_id}&amount=199"
        booking = Booking(user_whatsapp_id=whatsapp_id, preferred_time=preferred_time,
                          otp=otp, otp_valid_until=otp_valid_until, payment_link=payment_link)
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()

def verify_booking_otp(whatsapp_id, otp_candidate):
    db = SessionLocal()
    try:
        booking = db.query(Booking).filter_by(user_whatsapp_id=whatsapp_id).order_by(Booking.created_at.desc()).first()
        if not booking:
            return False, "No booking found."
        if booking.otp != otp_candidate:
            return False, "Incorrect OTP."
        if datetime.utcnow() > (booking.otp_valid_until or datetime.utcnow()):
            return False, "OTP expired."
        booking.confirmed = True
        db.commit()
        return True, booking
    finally:
        db.close()
