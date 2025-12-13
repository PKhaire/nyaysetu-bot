# models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String, unique=True, index=True)
    case_id = Column(String)

    # Personal information
    name = Column(String)
    state_name = Column(String)
    district_name = Column(String)
    category = Column(String)

    # Conversation state
    language = Column(String, default="English")
    query_count = Column(Integer, default=0)
    state = Column(String, default="NORMAL")

    # Booking temp storage
    temp_date = Column(String)
    temp_slot = Column(String)

    # Payment
    last_payment_link = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String, index=True)

    name = Column(String)
    state = Column(String)
    district = Column(String)
    category = Column(String)

    date = Column(String)
    slot_code = Column(String)
    slot_readable = Column(String)

    payment_token = Column(String, unique=True)
    paid = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String)
    rating = Column(Integer)
    feedback = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
