# models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy import Date, Enum
from sqlalchemy.orm import relationship
from db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String(64), unique=True, index=True, nullable=False)
    case_id = Column(String(32), unique=True, nullable=False)
    name = Column(String(200), nullable=True)
    city = Column(String(200), nullable=True)
    state = Column(String(200), nullable=True)
    district = Column(String(200), nullable=True)
    category = Column(String(200), nullable=True)
    language = Column(String(50), default="English")
    query_count = Column(Integer, default=0)
    state = Column(String(50), default="NORMAL")  # conversation state
    temp_date = Column(String(32), nullable=True)
    temp_slot = Column(String(32), nullable=True)
    last_payment_link = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String(64), index=True, nullable=False)
    user_case_id = Column(String(32), nullable=False)
    name = Column(String(200), nullable=False)
    city = Column(String(200), nullable=True)
    state = Column(String(200), nullable=True)
    district = Column(String(200), nullable=True)
    category = Column(String(200), nullable=True)
    date = Column(String(32), nullable=False)           # YYYY-MM-DD
    slot_code = Column(String(32), nullable=False)      # e.g. 8_9
    slot_readable = Column(String(64), nullable=False)  # e.g. 8:00 PM – 9:00 PM
    status = Column(String(32), default="pending")      # pending/confirmed/cancelled
    payment_token = Column(String(128), unique=True, nullable=True)
    payment_link = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Rating(Base):
    __tablename__ = "ratings"
    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String(64), index=True, nullable=False)
    score = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
