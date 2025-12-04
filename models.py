from sqlalchemy import Column, String, Integer, DateTime, Boolean
from datetime import datetime
from db import Base

class User(Base):
    __tablename__ = "users"

    phone = Column(String, primary_key=True, index=True)
    case_id = Column(String, nullable=False)
    language = Column(String, nullable=True)
    query_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # flags for booking flow
    is_booking = Column(Boolean, default=False)
    selected_date = Column(String, nullable=True)
    selected_time = Column(String, nullable=True)
    payment_done = Column(Boolean, default=False)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    phone = Column(String, nullable=False)
    date = Column(String, nullable=False)
    time = Column(String, nullable=False)
    payment_status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_whatsapp_id = Column(String, nullable=False)   # WA number
    direction = Column(String, nullable=False)          # "user" or "bot"
    text = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
