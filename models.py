from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from db import Base


class User(Base):
    __tablename__ = "users"

    whatsapp_id = Column(String, primary_key=True)
    case_id = Column(String, nullable=False)
    language = Column(String, default="en")
    query_count = Column(Integer, default=0)
    state = Column(String, default="NORMAL_CHAT")
    created_at = Column(DateTime, default=datetime.utcnow)

    last_payment_link = Column(String, nullable=True)

    # relationships
    bookings = relationship("Booking", back_populates="user")
    ratings = relationship("Rating", back_populates="user")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    whatsapp_id = Column(String, ForeignKey("users.whatsapp_id"))
    date = Column(String, nullable=False)
    slot = Column(String, nullable=False)
    status = Column(String, default="PENDING")      # PENDING / PAID / COMPLETED

    payment_id = Column(String, nullable=True)

    user = relationship("User", back_populates="bookings")


class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    whatsapp_id = Column(String, ForeignKey("users.whatsapp_id"))
    booking_id = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="ratings")
