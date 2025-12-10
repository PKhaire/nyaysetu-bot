# models.py
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Float
)
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String(32), unique=True, index=True, nullable=False)
    case_id = Column(String(32), nullable=False)
    language = Column(String(32), default="English")
    query_count = Column(Integer, default=0)
    state = Column(String(64), default="NORMAL")
    created_at = Column(DateTime, default=datetime.utcnow)

    # temp booking fields
    temp_name = Column(String(128), nullable=True)
    temp_city = Column(String(128), nullable=True)
    temp_category = Column(String(128), nullable=True)
    temp_date = Column(String(32), nullable=True)
    temp_slot = Column(String(32), nullable=True)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    booking_ref = Column(String(64), unique=True, index=True, nullable=False)
    whatsapp_id = Column(String(32), nullable=False)
    case_id = Column(String(32), nullable=True)

    name = Column(String(128), nullable=True)
    city = Column(String(128), nullable=True)
    category = Column(String(128), nullable=True)
    date = Column(String(32), nullable=True)
    slot = Column(String(64), nullable=True)

    price = Column(Float, default=0.0)
    status = Column(String(32), default="PENDING")
    payment_link = Column(Text, nullable=True)
    payment_reference = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
