# models.py
from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.sql import func
from db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String(50), unique=True, index=True)
    case_id = Column(String(50), index=True)
    name = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    language = Column(String(50), default="English")
    query_count = Column(Integer, default=0)
    state = Column(String(50), default="NORMAL")
    # temporary fields persisted for durability across requests:
    temp_date = Column(String(50), nullable=True)
    temp_slot = Column(String(50), nullable=True)
    last_payment_link = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String(50), index=True)
    case_id = Column(String(50), index=True)
    name = Column(String(200))
    city = Column(String(100))
    category = Column(String(100))
    date = Column(String(50))  # YYYY-MM-DD
    slot_code = Column(String(50))  # e.g. 8_9
    slot_readable = Column(String(100))  # human text
    price = Column(Integer)
    status = Column(String(50), default="pending")  # pending / confirmed / cancelled
    payment_link = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class Rating(Base):
    __tablename__ = "ratings"
    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String(50), index=True)
    score = Column(Integer)
    feedback = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())
