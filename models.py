from sqlalchemy import Column, String, Integer, DateTime, Boolean
from datetime import datetime
from db import Base


class User(Base):
    __tablename__ = "users"

    whatsapp_id = Column(String, primary_key=True, index=True)
    case_id = Column(String, nullable=False)
    language = Column(String, nullable=True)
    query_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_whatsapp_id = Column(String, nullable=False)
    direction = Column(String, nullable=False)      # "user" or "bot"
    text = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_whatsapp_id = Column(String, nullable=False)
    preferred_time = Column(String, nullable=False)

    # pricing
    amount = Column(Integer, nullable=False)
    coupon = Column(String, nullable=True)

    # payment
    payment_link = Column(String, nullable=False)
    confirmed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
