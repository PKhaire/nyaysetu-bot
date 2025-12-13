# models.py
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String, unique=True, index=True, nullable=False)

    # Profile
    name = Column(String)
    state_name = Column(String)
    district_name = Column(String)
    category = Column(String)
    language = Column(String, default="English")

    # Flow state
    state = Column(String, default="NORMAL")

    # Booking temp data
    temp_date = Column(String)
    temp_slot = Column(String)
    last_payment_link = Column(String)

    # Meta
    query_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="user")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    whatsapp_id = Column(String, index=True)

    name = Column(String)
    state_name = Column(String)
    district_name = Column(String)
    category = Column(String)

    date = Column(String)
    slot_code = Column(String)
    slot_readable = Column(String)

    amount = Column(Integer)
    payment_token = Column(String, unique=True)
    is_paid = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookings")


class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"))
    rating = Column(Integer)
    comment = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
