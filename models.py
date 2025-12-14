# models.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    whatsapp_id = Column(String, unique=True, index=True, nullable=False)

    case_id = Column(String, unique=True, index=True)

    name = Column(String)
    state_name = Column(String)
    district_name = Column(String)
    category = Column(String)

    language = Column(String, default="English")

    state = Column(String, default="NORMAL")
    temp_date = Column(String)
    temp_slot = Column(String)
    last_payment_link = Column(String)

    query_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String, index=True)

    name = Column(String)
    state_name = Column(String)
    district_name = Column(String)
    category = Column(String)

    date = Column(String)
    slot_code = Column(String)
    slot_readable = Column(String)

    payment_token = Column(String, unique=True)
    status = Column(String, default="PENDING")

    created_at = Column(DateTime, default=datetime.utcnow)
