# models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String, unique=True, index=True, nullable=False)
    case_id = Column(String, nullable=True)
    name = Column(String, nullable=True)
    city = Column(String, nullable=True)
    category = Column(String, nullable=True)
    language = Column(String, default="English")
    query_count = Column(Integer, default=0)
    state = Column(String, default="NORMAL")
    temp_date = Column(String, nullable=True)
    temp_slot = Column(String, nullable=True)  # code like "8_9"
    last_payment_link = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="user")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    whatsapp_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    city = Column(String, nullable=True)
    category = Column(String, nullable=True)
    date = Column(String, nullable=False)  # YYYY-MM-DD
    slot_code = Column(String, nullable=False)  # e.g., "8_9"
    slot_readable = Column(String, nullable=False)  # "8:00 PM – 9:00 PM"
    price = Column(Float, nullable=False)
    status = Column(String, default="pending")  # pending/confirmed/cancelled
    payment_token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookings")

class Rating(Base):
    __tablename__ = "ratings"
    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String, nullable=False)
    score = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
