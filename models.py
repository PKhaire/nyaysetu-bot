from sqlalchemy import Column, String, Integer, DateTime, Boolean
from datetime import datetime
from db import Base


class User(Base):
    __tablename__ = "users"

    # WhatsApp phone number (e.g., "918975985808")
    whatsapp_id = Column(String, primary_key=True, index=True)

    case_id = Column(String, nullable=False)
    language = Column(String, nullable=True)
    query_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # optional flags for booking flow
    is_booking = Column(Boolean, default=False)
    selected_date = Column(String, nullable=True)
    selected_time = Column(String, nullable=True)
    payment_done = Column(Boolean, default=False)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_whatsapp_id = Column(String, nullable=False)  # WA phone number
    direction = Column(String, nullable=False)         # "user" or "bot"
    text = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_whatsapp_id = Column(String, nullable=False)  # foreign key to User
    preferred_time = Column(String, nullable=False)    # "2025-12-04 — Afternoon (1 PM – 4 PM)"
    otp = Column(String, nullable=False)
    otp_valid_until = Column(DateTime, nullable=False)
    payment_link = Column(String, nullable=False)

    confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
