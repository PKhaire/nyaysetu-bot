from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Enum,
    UniqueConstraint,
)
from datetime import datetime, timezone
import enum
from db import Base


def utc_now():
    """Return naive UTC for compatibility with the existing DateTime columns."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    created_at = Column(DateTime, default=utc_now)


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
    created_at = Column(DateTime, default=utc_now)


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
    created_at = Column(DateTime, default=utc_now)


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
    """Legacy deduplication table retained for migration compatibility."""

    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True)
    message_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=utc_now)


# =========================================================
# DURABLE INBOUND WHATSAPP INBOX
# =========================================================

class InboundMessageEvent(Base):
    """Lease-aware message claim that cannot be stranded by a process crash."""

    __tablename__ = "inbound_message_events"

    __table_args__ = (
        Index("idx_inbound_status_lease", "status", "lease_expires_at"),
        Index("idx_inbound_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True)
    message_id = Column(String(255), unique=True, index=True, nullable=False)
    status = Column(String(32), nullable=False, default="RECEIVED")
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(500), nullable=True)
    received_at = Column(DateTime, nullable=False, default=utc_now)
    lease_expires_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)


# =========================================================
# USER FEEDBACK (ADDITIVE / STANDALONE)
# =========================================================

class Feedback(Base):
    __tablename__ = "feedback"

    __table_args__ = (
        Index("idx_feedback_status_created", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)
    rating = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    source = Column(String(40), nullable=False, default="whatsapp")
    context_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="NEW")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


# =========================================================
# SUPPORT REQUESTS (ADDITIVE / STANDALONE)
# =========================================================

class SupportRequest(Base):
    __tablename__ = "support_requests"

    __table_args__ = (
        Index("idx_support_status_created", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)
    case_id = Column(String(32), nullable=True, index=True)
    request_type = Column(String(64), nullable=False, default="GENERAL")
    subject = Column(String(160), nullable=True)
    message = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="OPEN")
    priority = Column(String(16), nullable=False, default="NORMAL")
    assigned_to = Column(String(120), nullable=True)
    resolution_note = Column(Text, nullable=True)
    sla_due_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    resolved_at = Column(DateTime, nullable=True)


# =========================================================
# VERSIONED USER CONSENT
# =========================================================

class UserConsent(Base):
    __tablename__ = "user_consents"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "purpose",
            "policy_version",
            name="uq_user_consent_purpose_version",
        ),
        Index("idx_consent_user_purpose", "user_id", "purpose"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    purpose = Column(String(64), nullable=False)
    policy_version = Column(String(64), nullable=False)
    granted = Column(Boolean, nullable=False, default=True)
    source = Column(String(32), nullable=False, default="whatsapp")
    consented_at = Column(DateTime, nullable=False, default=utc_now)
    revoked_at = Column(DateTime, nullable=True)


# =========================================================
# PRODUCT ANALYTICS (ADDITIVE / STANDALONE)
# =========================================================

class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    __table_args__ = (
        Index("idx_analytics_event_created", "event_name", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    event_name = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    session_id = Column(String(128), nullable=True, index=True)
    properties_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)


# =========================================================
# DURABLE WEBHOOK INBOX (ADDITIVE / STANDALONE)
# =========================================================

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "event_id",
            name="uq_webhook_event_provider_id",
        ),
        Index("idx_webhook_status_received", "status", "received_at"),
        Index("idx_webhook_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True)
    provider = Column(String(32), nullable=False)
    event_id = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=True)
    payload_hash = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="RECEIVED")
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(500), nullable=True)
    received_at = Column(DateTime, nullable=False, default=utc_now)
    processed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)


# =========================================================
# DURABLE SIDE-EFFECT OUTBOX (ADDITIVE / STANDALONE)
# =========================================================

class OutboxJob(Base):
    __tablename__ = "outbox_jobs"

    __table_args__ = (
        Index(
            "idx_outbox_status_available",
            "status",
            "available_at",
        ),
    )

    id = Column(Integer, primary_key=True)
    kind = Column(String(80), nullable=False, index=True)
    dedupe_key = Column(String(255), nullable=True, unique=True, index=True)
    payload_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="PENDING")
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=False, default=utc_now)
    last_error = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


# =========================================================
# CONSULTATION FULFILMENT AND PAYMENT RECONCILIATION
# =========================================================

class BookingFulfillment(Base):
    """Operational truth for delivering a paid consultation."""

    __tablename__ = "booking_fulfillments"

    __table_args__ = (
        Index("idx_fulfillment_status_due", "status", "sla_due_at"),
    )

    id = Column(Integer, primary_key=True)
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id"),
        unique=True,
        index=True,
        nullable=False,
    )
    status = Column(String(40), nullable=False, default="UNASSIGNED")
    advocate_id = Column(Integer, ForeignKey("advocates.id"), nullable=True)
    assigned_to = Column(String(160), nullable=True)
    operator_notes = Column(Text, nullable=True)
    scheduled_start_at = Column(DateTime, nullable=True)
    sla_due_at = Column(DateTime, nullable=True, index=True)
    assigned_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    feedback_requested_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class PaymentReconciliation(Base):
    """Privacy-minimised queue for captured payments requiring human review."""

    __tablename__ = "payment_reconciliations"

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "payment_id",
            name="uq_payment_reconciliation_provider_payment",
        ),
        Index("idx_payment_reconciliation_status", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    provider = Column(String(32), nullable=False, default="razorpay")
    payment_id = Column(String(255), nullable=False)
    payment_link_id = Column(String(255), nullable=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)
    reason = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="OPEN")
    expected_amount = Column(Integer, nullable=True)
    received_amount = Column(Integer, nullable=True)
    currency = Column(String(8), nullable=True)
    details_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(120), nullable=True)
    resolution_note = Column(Text, nullable=True)


# =========================================================
# OPERATOR-MANAGED AVAILABILITY
# =========================================================

class BookingBlackout(Base):
    __tablename__ = "booking_blackouts"

    __table_args__ = (
        Index("idx_blackout_date_active", "date", "active"),
    )

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    slot_code = Column(String(32), nullable=True)
    reason = Column(String(255), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(120), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class BookingCapacityOverride(Base):
    __tablename__ = "booking_capacity_overrides"

    __table_args__ = (
        Index("idx_capacity_override_date_active", "date", "active"),
    )

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    slot_code = Column(String(32), nullable=True)
    capacity = Column(Integer, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(120), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


# =========================================================
# ADMIN MUTATION AUDIT TRAIL
# =========================================================

class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"

    __table_args__ = (
        Index("idx_admin_audit_created", "created_at"),
        Index("idx_admin_audit_target", "target_type", "target_id"),
    )

    id = Column(Integer, primary_key=True)
    operator_id = Column(String(120), nullable=False)
    action = Column(String(100), nullable=False)
    target_type = Column(String(80), nullable=False)
    target_id = Column(String(120), nullable=False)
    before_json = Column(Text, nullable=False, default="{}")
    after_json = Column(Text, nullable=False, default="{}")
    request_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
