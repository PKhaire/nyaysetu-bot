# models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String, unique=True, index=True, nullable=False)
    free_ai_count = Column(Integer, default=0)
    case_id = Column(String, unique=True, index=True)
    ai_enabled = Column(Boolean, default=False)
    name = Column(String)
    state_name = Column(String)
    district_name = Column(String)
    category = Column(String)
    subcategory = Column(String)
    
    language = Column(String, default="English")

    state = Column(String, default="NORMAL")
    temp_date = Column(String)
    temp_slot = Column(String)
    last_payment_link = Column(String)
    session_started = Column(Boolean, default=False)
    query_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "booking"

    id = Column(Integer, primary_key=True, index=True)

    # -------------------------
    # EXISTING FIELDS
    # -------------------------
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    state = Column(String, nullable=False)
    district = Column(String, nullable=False)
    category = Column(String, nullable=False)
    subcategory = Column(String, nullable=True)
    appointment_date = Column(String, nullable=False)
    time_slot = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String, default="PENDING")

    # Payment link reference
    razorpay_payment_link_id = Column(String, nullable=False, unique=True)

    # -------------------------
    # PAYMENT CONFIRMATION
    # -------------------------
    razorpay_payment_id = Column(String, nullable=True, unique=True)
    payment_mode = Column(String, nullable=True)  # test / live
    paid_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

class CategoryAnalytics(Base):
    __tablename__ = "category_analytics"

    id = Column(Integer, primary_key=True)
    category = Column(String, index=True)
    subcategory = Column(String, index=True)
    count = Column(Integer, default=0)

