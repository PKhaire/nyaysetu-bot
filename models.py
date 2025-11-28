# models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from datetime import datetime
from db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String, unique=True, index=True, nullable=False)
    case_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=True)
    language = Column(String, default="English")
    created_at = Column(DateTime, default=datetime.utcnow)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    user_whatsapp_id = Column(String, index=True)
    direction = Column(String)  # 'user' or 'bot'
    text = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    user_whatsapp_id = Column(String, index=True)
    preferred_time = Column(String)
    confirmed = Column(Boolean, default=False)
    otp = Column(String, nullable=True)
    otp_valid_until = Column(DateTime, nullable=True)
    payment_link = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Lawyer(Base):
    __tablename__ = "lawyers"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    verified = Column(Boolean, default=False)
    languages = Column(String)  # comma-separated
    specialty = Column(String)
