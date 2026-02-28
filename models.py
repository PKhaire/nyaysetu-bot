from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Date,
    Index,
    Enum,
)
from datetime import datetime
import enum
from db import Base


# =========================================================
# BOOKING STATUS ENUM (Prevents Status Typos)
# =========================================================

class BookingStatus(enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


# =========================================================
# USER MODEL
# =========================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String, unique=True, index=True, nullable=False)

    # -------------------------
    # FLOW STATE
    # -------------------------
    flow_state = Column(String, default="NORMAL")

    # -------------------------
    # USER / CONTEXT
    # -------------------------
    case_id = Column(String, unique=True, index=True)
    language = Column(String, default="English")
    name = Column(String)

    # -------------------------
    # LOCATION
    # -------------------------
    state_name = Column(String)
    district_name = Column(String)
    temp_state = Column(String)
    temp_district = Column(String)

    # -------------------------
    # LEGAL CONTEXT
    # -------------------------
    category = Column(String)
    subcategory = Column(String)

    # -------------------------
    # AI / SESSION FLAGS
    # -------------------------
    ai_enabled = Column(Boolean, default=False)
    free_ai_count = Column(Integer, default=0)
    welcome_sent = Column(Boolean, default=False)
    session_started = Column(Boolean, default=False)
    query_count = Column(Integer, default=0)

    # -------------------------
    # TEMP BOOKING DATA
    # -------------------------
    temp_date = Column(String)
    temp_slot = Column(String)
    last_payment_link = Column(String)

    # -------------------------
    # AUDIT
    # -------------------------
    created_at = Column(DateTime, default=datetime.utcnow)


# =========================================================
# BOOKING MODEL (UPGRADED)
# =========================================================

class Booking(Base):
    __tablename__ = "bookings"

    __table_args__ = (
        Index("idx_booking_wa_status", "whatsapp_id", "status"),
        Index("idx_booking_token", "payment_token"),
    )

    # -------------------------
    # PRIMARY KEY
    # -------------------------
    id = Column(Integer, primary_key=True, index=True)

    # -------------------------
    # WHATSAPP CONTEXT
    # -------------------------
    whatsapp_id = Column(String, index=True, nullable=False)

    # -------------------------
    # USER DETAILS
    # -------------------------
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)

    # -------------------------
    # LOCATION
    # -------------------------
    state_name = Column(String, nullable=False)
    district_name = Column(String, nullable=False)

    # -------------------------
    # LEGAL CONTEXT
    # -------------------------
    category = Column(String, nullable=False)
    subcategory = Column(String, nullable=True)

    # -------------------------
    # APPOINTMENT
    # -------------------------
    date = Column(Date, nullable=False)
    slot_code = Column(String, nullable=True)
    slot_readable = Column(String, nullable=False)

    # -------------------------
    # PAYMENT
    # -------------------------
    amount = Column(Integer, nullable=False)

    status = Column(
        Enum(BookingStatus),
        default=BookingStatus.PENDING,
        nullable=False,
    )

    payment_token = Column(String, unique=True, nullable=True)

    razorpay_payment_link_id = Column(String, nullable=True, unique=True)
    razorpay_payment_id = Column(String, nullable=True, unique=True)

    payment_processed = Column(Boolean, default=False)

    payment_mode = Column(String, nullable=True)
    paid_at = Column(DateTime, nullable=True)

    receipt_generated = Column(Boolean, default=False)
    receipt_sent = Column(Boolean, default=False)

    # -------------------------
    # AUDIT
    # -------------------------
    created_at = Column(DateTime, default=datetime.utcnow)


# =========================================================
# CATEGORY ANALYTICS
# =========================================================

class CategoryAnalytics(Base):
    __tablename__ = "category_analytics"

    id = Column(Integer, primary_key=True)
    category = Column(String, index=True)
    subcategory = Column(String, index=True)
    count = Column(Integer, default=0)


# =========================================================
# CONVERSATION LOG
# =========================================================

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    user_whatsapp_id = Column(String, index=True)
    direction = Column(String)
    text = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


# =========================================================
# ADVOCATE MODEL
# =========================================================

class Advocate(Base):
    __tablename__ = "advocates"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    category = Column(String, nullable=False)
    district = Column(String, nullable=False)
    active = Column(Boolean, default=True)


# =========================================================
# PROCESSED MESSAGE (DEDUP PROTECTION)
# =========================================================

class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True)
    message_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
