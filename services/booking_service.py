"""Booking, availability, and payment-link lifecycle services.

The database stores naive UTC timestamps for compatibility with the existing
schema. All user-facing calendar and slot calculations are performed with
timezone-aware Asia/Kolkata datetimes.
"""

from __future__ import annotations

import atexit
import logging
import re
import uuid
from datetime import date as date_type
from datetime import datetime, time as time_type, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import and_, or_, text

from config import (
    BOOKING_CUTOFF_HOURS,
    BOOKING_DATE_CHOICES,
    BOOKING_MAX_AHEAD_DAYS,
    BOOKING_MAX_PER_DAY,
    BOOKING_MAX_PER_SLOT,
    BOOKING_PRICE,
    BOOKING_WORKING_WEEKDAYS,
    PAYMENT_LINK_TTL_MINUTES,
    RAZORPAY_API_TIMEOUT_SECONDS,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
)
from db import SessionLocal
from models import (
    Booking,
    BookingBlackout,
    BookingCapacityOverride,
    BookingStatus,
)

logger = logging.getLogger("booking_service")

try:
    IST = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    # Windows does not ship the IANA database. India has no daylight-saving
    # transition in the booking horizon, so this remains correct if `tzdata`
    # is not installed in a local development environment.
    IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")


# --------------------
# Slot configuration
# --------------------
SLOT_MAP = {
    "10_11": "10:00 AM – 11:00 AM",
    "12_1": "12:00 PM – 1:00 PM",
    "3_4": "3:00 PM – 4:00 PM",
    "6_7": "6:00 PM – 7:00 PM",
    "8_9": "8:00 PM – 9:00 PM",
}

SLOT_START_HOUR = {
    "10_11": 10,
    "12_1": 12,
    "3_4": 15,
    "6_7": 18,
    "8_9": 20,
}

SLOT_BUFFER_HOURS = float(BOOKING_CUTOFF_HOURS)
_razorpay_client = None
_RAZORPAY_PAYMENT_LINK_ID = re.compile(r"plink_[A-Za-z0-9]+")


class _PaymentLinkAPI:
    """Small compatibility surface backed by bounded Razorpay HTTPS calls."""

    def __init__(self, http_client: httpx.Client):
        self._http_client = http_client

    def create(self, payload: dict) -> dict:
        response = self._http_client.post("/v1/payment_links", json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Razorpay returned an invalid JSON response")
        return data

    def cancel(self, payment_link_id: str) -> dict:
        if not _RAZORPAY_PAYMENT_LINK_ID.fullmatch(
            str(payment_link_id or "")
        ):
            raise ValueError("Invalid Razorpay payment-link ID")
        response = self._http_client.post(
            f"/v1/payment_links/{payment_link_id}/cancel"
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Razorpay returned an invalid JSON response")
        return data


class _RazorpayHTTPClient:
    def __init__(self):
        timeout = httpx.Timeout(
            RAZORPAY_API_TIMEOUT_SECONDS,
            connect=min(RAZORPAY_API_TIMEOUT_SECONDS, 5.0),
        )
        self._http_client = httpx.Client(
            base_url="https://api.razorpay.com",
            auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "NyaySetu-Payment-Link/1.0",
            },
            follow_redirects=False,
            timeout=timeout,
        )
        self.payment_link = _PaymentLinkAPI(self._http_client)

    def close(self) -> None:
        self._http_client.close()


# --------------------
# Time and provider helpers
# --------------------
def _now_ist() -> datetime:
    return datetime.now(IST)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_booking_date(value: str) -> date_type | None:
    try:
        return date_type.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _slot_start_at(booking_date: date_type, slot_code: str) -> datetime:
    return datetime.combine(
        booking_date,
        time_type(SLOT_START_HOUR[slot_code], tzinfo=IST),
    )


def _payment_expiry_cutoff(now_utc: datetime | None = None) -> datetime:
    now_utc = _as_utc_naive(now_utc or _utc_now_naive())
    return now_utc - timedelta(minutes=PAYMENT_LINK_TTL_MINUTES)


def _payment_expire_by(created_at: datetime) -> int:
    created_at_utc = _as_utc_naive(created_at).replace(tzinfo=timezone.utc)
    return int(
        (
            created_at_utc
            + timedelta(minutes=PAYMENT_LINK_TTL_MINUTES)
        ).timestamp()
    )


def _get_razorpay_client():
    """Lazily build a bounded HTTP client with no import-time network work."""
    global _razorpay_client

    if _razorpay_client is not None:
        return _razorpay_client

    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise RuntimeError("Razorpay credentials are not configured")

    _razorpay_client = _RazorpayHTTPClient()
    atexit.register(_razorpay_client.close)
    return _razorpay_client


def _cancel_payment_link_safely(client, payment_link_id: str | None) -> None:
    if not client or not payment_link_id:
        return

    try:
        cancel = getattr(client.payment_link, "cancel", None)
        if callable(cancel):
            cancel(payment_link_id)
    except Exception:
        logger.exception(
            "Failed to cancel orphaned Razorpay link | payment_link_id=%s",
            payment_link_id,
        )


def create_token():
    return uuid.uuid4().hex


# --------------------
# Availability helpers
# --------------------
def _is_working_day(booking_date: date_type) -> bool:
    return booking_date.weekday() in BOOKING_WORKING_WEEKDAYS


def _load_availability_rules(
    db,
    booking_dates: list[date_type],
) -> tuple[
    dict[date_type, set[str | None]],
    dict[tuple[date_type, str | None], int],
]:
    blackouts: dict[date_type, set[str | None]] = {
        booking_date: set() for booking_date in booking_dates
    }
    overrides: dict[tuple[date_type, str | None], int] = {}
    if not booking_dates:
        return blackouts, overrides

    for blackout in (
        db.query(BookingBlackout)
        .filter(
            BookingBlackout.date.in_(booking_dates),
            BookingBlackout.active.is_(True),
        )
        .all()
    ):
        blackouts.setdefault(blackout.date, set()).add(blackout.slot_code)

    for override in (
        db.query(BookingCapacityOverride)
        .filter(
            BookingCapacityOverride.date.in_(booking_dates),
            BookingCapacityOverride.active.is_(True),
        )
        .order_by(BookingCapacityOverride.id.asc())
        .all()
    ):
        overrides[(override.date, override.slot_code)] = max(
            0,
            int(override.capacity),
        )
    return blackouts, overrides


def _effective_capacity(
    booking_date: date_type,
    slot_code: str,
    overrides: dict[tuple[date_type, str | None], int],
) -> tuple[int, int]:
    day_capacity = overrides.get(
        (booking_date, None),
        int(BOOKING_MAX_PER_DAY),
    )
    slot_capacity = overrides.get(
        (booking_date, slot_code),
        int(BOOKING_MAX_PER_SLOT),
    )
    return day_capacity, slot_capacity


def _is_blacked_out(
    booking_date: date_type,
    slot_code: str,
    blackouts: dict[date_type, set[str | None]],
) -> bool:
    date_blackouts = blackouts.get(booking_date, set())
    return None in date_blackouts or slot_code in date_blackouts


def _active_capacity_filter(now_utc: datetime | None = None):
    return or_(
        Booking.status == BookingStatus.PAID,
        and_(
            Booking.status == BookingStatus.PENDING,
            Booking.created_at >= _payment_expiry_cutoff(now_utc),
        ),
    )


def _active_bookings_for_date(
    db,
    booking_date: date_type,
    *,
    lock: bool = False,
    exclude_booking_id: int | None = None,
) -> list[Booking]:
    query = db.query(Booking).filter(
        Booking.date == booking_date,
        _active_capacity_filter(),
    )
    if exclude_booking_id is not None:
        query = query.filter(Booking.id != exclude_booking_id)
    if lock:
        query = query.with_for_update()
    return query.all()


def _acquire_capacity_lock(db, booking_date: date_type) -> None:
    """Serialize capacity decisions for a date across worker processes.

    PostgreSQL gets a transaction-scoped advisory lock. SQLite has no row or
    advisory locks, so a harmless UPDATE is used to acquire its database write
    lock before capacity is read. Other dialects still receive row locking
    from `_active_bookings_for_date`.
    """
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        namespace = 0x4E53  # "NS"
        lock_key = (namespace << 32) | booking_date.toordinal()
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )
    elif dialect_name == "sqlite":
        db.execute(
            text(
                "UPDATE bookings "
                "SET id = id "
                "WHERE date = :booking_date"
            ),
            {"booking_date": booking_date},
        )


def _capacity_error(
    db,
    booking_date: date_type,
    slot_code: str,
    *,
    lock: bool = False,
    exclude_booking_id: int | None = None,
) -> str | None:
    if not _is_working_day(booking_date):
        return "Consultations are not available on this day."

    blackouts, overrides = _load_availability_rules(db, [booking_date])
    if _is_blacked_out(booking_date, slot_code, blackouts):
        return "This date or time slot is unavailable. Please select another."

    active_bookings = _active_bookings_for_date(
        db,
        booking_date,
        lock=lock,
        exclude_booking_id=exclude_booking_id,
    )
    day_capacity, slot_capacity = _effective_capacity(
        booking_date,
        slot_code,
        overrides,
    )

    if day_capacity <= 0 or len(active_bookings) >= day_capacity:
        return "All consultation slots for this date are full."

    slot_count = sum(
        booking.slot_code == slot_code for booking in active_bookings
    )
    if slot_capacity <= 0 or slot_count >= slot_capacity:
        return "This time slot is no longer available. Please select another."

    return None


def payment_capacity_conflict(db, booking: Booking) -> str | None:
    """Serialize and re-check capacity before accepting a delayed payment."""

    if not booking or not booking.date or not booking.slot_code:
        return "The paid booking is missing schedule information."

    _acquire_capacity_lock(db, booking.date)
    return _capacity_error(
        db,
        booking.date,
        booking.slot_code,
        lock=True,
        exclude_booking_id=booking.id,
    )


def reschedule_paid_booking(
    db,
    booking: Booking,
    new_date: str,
    new_slot_code: str,
) -> str | None:
    """Move a paid booking under the same serialized capacity rules."""

    if booking.status not in (BookingStatus.PAID, BookingStatus.COMPLETED):
        return "Only paid consultations can be rescheduled."

    booking_date = _parse_booking_date(new_date)
    if booking_date is None:
        return "Invalid booking date."
    valid, error = validate_slot(new_date, new_slot_code, db=db)
    if not valid:
        return error

    lock_dates = sorted({booking.date, booking_date})
    for lock_date in lock_dates:
        _acquire_capacity_lock(db, lock_date)

    capacity_error = _capacity_error(
        db,
        booking_date,
        new_slot_code,
        lock=True,
        exclude_booking_id=booking.id,
    )
    if capacity_error:
        return capacity_error

    booking.date = booking_date
    booking.slot_code = new_slot_code
    booking.slot_readable = SLOT_MAP[new_slot_code]
    db.flush()
    return None


def _load_capacity_by_date(
    db,
    booking_dates: list[date_type],
) -> dict[date_type, dict[str, int]]:
    capacity: dict[date_type, dict[str, int]] = {
        booking_date: {} for booking_date in booking_dates
    }
    if not booking_dates:
        return capacity

    bookings = (
        db.query(Booking)
        .filter(
            Booking.date.in_(booking_dates),
            _active_capacity_filter(),
        )
        .all()
    )
    for booking in bookings:
        slot_counts = capacity.setdefault(booking.date, {})
        slot_counts[booking.slot_code] = (
            slot_counts.get(booking.slot_code, 0) + 1
        )
    return capacity


def _calendar_capacity(
    booking_dates: list[date_type],
    db=None,
) -> dict[date_type, dict[str, int]]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        return _load_capacity_by_date(session, booking_dates)
    except Exception:
        if not owns_session:
            raise
        session.rollback()
        logger.exception("Unable to load booking capacity for calendar")
        return {booking_date: {} for booking_date in booking_dates}
    finally:
        if owns_session:
            session.close()


def _day_has_capacity(
    booking_date: date_type,
    slot_counts: dict[str, int],
    blackouts: dict[date_type, set[str | None]],
    overrides: dict[tuple[date_type, str | None], int],
) -> bool:
    if not _is_working_day(booking_date):
        return False
    if None in blackouts.get(booking_date, set()):
        return False

    total = sum(slot_counts.values())
    day_capacity = overrides.get(
        (booking_date, None),
        int(BOOKING_MAX_PER_DAY),
    )
    if day_capacity <= 0 or total >= day_capacity:
        return False

    for slot_code in SLOT_MAP:
        valid, _ = validate_slot(booking_date.isoformat(), slot_code)
        if not valid:
            continue
        if _is_blacked_out(booking_date, slot_code, blackouts):
            continue
        _, slot_capacity = _effective_capacity(
            booking_date,
            slot_code,
            overrides,
        )
        if (
            slot_capacity > 0
            and slot_counts.get(slot_code, 0) < slot_capacity
        ):
            return True
    return False


# --------------------
# Calendar generators
# --------------------
def generate_dates_calendar(skip_today=False, db=None):
    today = _now_ist().date()
    start_offset = 1 if skip_today else 0
    max_ahead = max(0, int(BOOKING_MAX_AHEAD_DAYS))
    final_offset = max_ahead

    if start_offset > final_offset:
        return []

    candidate_dates = [
        today + timedelta(days=offset)
        for offset in range(start_offset, final_offset + 1)
    ]
    owns_session = db is None
    session = db or SessionLocal()
    try:
        capacity = _load_capacity_by_date(session, candidate_dates)
        blackouts, overrides = _load_availability_rules(
            session,
            candidate_dates,
        )

        rows = []
        for booking_date in candidate_dates:
            if not _day_has_capacity(
                booking_date,
                capacity.get(booking_date, {}),
                blackouts,
                overrides,
            ):
                continue
            rows.append(
                {
                    "id": f"date_{booking_date.isoformat()}",
                    "title": booking_date.strftime("%d %b (%a)"),
                    "description": "Select this date",
                }
            )
            if len(rows) >= BOOKING_DATE_CHOICES:
                break
        return rows
    finally:
        if owns_session:
            session.close()


def generate_slots_calendar(date_str, db=None):
    booking_date = _parse_booking_date(date_str)
    if booking_date is None:
        return []

    owns_session = db is None
    session = db or SessionLocal()
    try:
        capacity = _load_capacity_by_date(session, [booking_date]).get(
            booking_date,
            {},
        )
        blackouts, overrides = _load_availability_rules(
            session,
            [booking_date],
        )
        day_capacity = overrides.get(
            (booking_date, None),
            int(BOOKING_MAX_PER_DAY),
        )
        if (
            not _is_working_day(booking_date)
            or None in blackouts.get(booking_date, set())
            or day_capacity <= 0
            or sum(capacity.values()) >= day_capacity
        ):
            return []

        rows = []
        for slot_code, label in SLOT_MAP.items():
            valid, _ = validate_slot(date_str, slot_code)
            if not valid:
                continue
            if _is_blacked_out(booking_date, slot_code, blackouts):
                continue
            _, slot_capacity = _effective_capacity(
                booking_date,
                slot_code,
                overrides,
            )
            if (
                slot_capacity <= 0
                or capacity.get(slot_code, 0) >= slot_capacity
            ):
                continue
            rows.append(
                {
                    "id": f"slot_{slot_code}",
                    "title": label,
                    "description": f"Available on {date_str}",
                }
            )
        return rows
    finally:
        if owns_session:
            session.close()


# --------------------
# Time slot validation
# --------------------
def validate_slot(date_str, slot_code, db=None):
    """Validate booking horizon and the configured IST cutoff."""
    booking_date = _parse_booking_date(date_str)
    if booking_date is None:
        return False, "Invalid booking date."

    if slot_code not in SLOT_MAP:
        return False, "Invalid time slot."

    now = _now_ist()
    today = now.date()
    if booking_date < today:
        return False, "This date has already passed."

    max_date = today + timedelta(days=max(0, int(BOOKING_MAX_AHEAD_DAYS)))
    if booking_date > max_date:
        return False, "Please select a date within the booking window."
    if not _is_working_day(booking_date):
        return False, "Consultations are not available on this day."
    if db is not None:
        blackouts, _ = _load_availability_rules(db, [booking_date])
        if _is_blacked_out(booking_date, slot_code, blackouts):
            return (
                False,
                "This date or time slot is unavailable. Please select another.",
            )

    slot_start = _slot_start_at(booking_date, slot_code)
    minimum_start = now + timedelta(hours=SLOT_BUFFER_HOURS)
    if slot_start < minimum_start:
        return (
            False,
            (
                "Please select a time slot at least "
                f"{BOOKING_CUTOFF_HOURS:g} hours from now."
            ),
        )

    return True, None


# --------------------
# Booking creation
# --------------------
def create_booking_temp(
    db,
    user,
    name,
    state,
    district,
    category,
    subcategory,
    date,
    slot_code,
):
    if not state:
        logger.error(
            "Booking blocked: state missing | user_id=%s",
            getattr(user, "id", None),
        )
        return None, "State information missing. Please restart booking."

    if not name or not district or not category or not getattr(
        user,
        "whatsapp_id",
        None,
    ):
        return None, "Booking details are incomplete. Please restart booking."

    valid, error = validate_slot(date, slot_code, db=db)
    if not valid:
        return None, error

    booking_date = _parse_booking_date(date)
    if booking_date is None:
        return None, "Invalid booking date."

    payment_link_id = None
    razorpay_client = None
    try:
        _acquire_capacity_lock(db, booking_date)
        capacity_error = _capacity_error(
            db,
            booking_date,
            slot_code,
            lock=True,
        )
        if capacity_error:
            # Release any row locks acquired by the capacity check before the
            # caller performs network I/O to notify the user.
            db.rollback()
            return None, capacity_error

        token = create_token()
        created_at = _utc_now_naive()
        booking = Booking(
            whatsapp_id=user.whatsapp_id,
            name=name,
            phone=user.whatsapp_id,
            state_name=state,
            district_name=district,
            category=category,
            subcategory=subcategory,
            date=booking_date,
            slot_code=slot_code,
            slot_readable=SLOT_MAP[slot_code],
            amount=int(BOOKING_PRICE),
            payment_token=token,
            status=BookingStatus.PENDING,
            created_at=created_at,
        )

        db.add(booking)
        db.flush()

        razorpay_client = _get_razorpay_client()
        payment_link = razorpay_client.payment_link.create(
            {
                "amount": int(booking.amount * 100),
                "currency": "INR",
                "accept_partial": False,
                "expire_by": _payment_expire_by(created_at),
                "reference_id": token,
                "description": "NyaySetu Legal Consultation",
                "customer": {
                    "name": booking.name,
                    "contact": booking.phone,
                },
                "notify": {
                    "sms": False,
                    "email": False,
                },
                "notes": {
                    "booking_token": token,
                    "booking_id": str(booking.id),
                },
            }
        )

        if not isinstance(payment_link, dict):
            raise RuntimeError("Razorpay returned an invalid payment-link response")

        payment_link_id = payment_link.get("id")
        short_url = payment_link.get("short_url")
        if not payment_link_id or not short_url:
            raise RuntimeError("Razorpay response is missing id or short_url")

        booking.razorpay_payment_link_id = payment_link_id
        db.commit()
        db.refresh(booking)
        return booking, short_url

    except Exception:
        db.rollback()
        _cancel_payment_link_safely(razorpay_client, payment_link_id)
        logger.exception(
            "Booking/payment-link creation failed | user_id=%s",
            getattr(user, "id", None),
        )
        return (
            None,
            "Unable to create the payment link right now. Please try again.",
        )


# --------------------
# Payment confirmation
# --------------------
def confirm_booking_after_payment(db, token):
    booking = (
        db.query(Booking)
        .filter(Booking.payment_token == token)
        .with_for_update()
        .first()
    )
    if not booking:
        return None, "Booking not found."

    if booking.status == BookingStatus.PAID:
        return booking, "Already confirmed"

    created_at = _as_utc_naive(booking.created_at)
    if created_at < _payment_expiry_cutoff():
        booking.status = BookingStatus.EXPIRED
        db.commit()
        return None, "Payment link expired"

    booking.status = BookingStatus.PAID
    booking.payment_processed = True
    booking.paid_at = _utc_now_naive()
    db.commit()
    db.refresh(booking)
    return booking, "confirmed"


def is_payment_already_processed(payment_id):
    db = SessionLocal()
    try:
        return (
            db.query(Booking)
            .filter(Booking.razorpay_payment_id == payment_id)
            .first()
            is not None
        )
    finally:
        db.close()


def confirm_booking_payment(payment_link_id, payment_id, payment_mode):
    db = SessionLocal()
    try:
        return (
            mark_booking_as_paid(
                payment_link_id=payment_link_id,
                payment_id=payment_id,
                payment_mode=payment_mode,
                db=db,
            )
            is not None
        )
    finally:
        db.close()


def mark_booking_as_paid(
    payment_link_id,
    payment_id,
    payment_mode,
    db=None,
    *,
    commit=True,
):
    """Atomically mark a booking paid using the caller-owned session.

    `db` is deliberately required in active code. The function never creates
    or closes a session. Set ``commit=False`` when the caller needs the payment
    update, webhook inbox record, user state, and outbox jobs to commit as one
    transaction.
    """
    if db is None:
        raise ValueError("mark_booking_as_paid requires a caller-owned db session")

    paid_at = _utc_now_naive()
    try:
        duplicate_payment = (
            db.query(Booking)
            .filter(
                Booking.razorpay_payment_id == payment_id,
                Booking.razorpay_payment_link_id != payment_link_id,
            )
            .first()
        )
        if duplicate_payment:
            logger.error(
                "Payment id already belongs to another booking | payment_id=%s",
                payment_id,
            )
            return None

        updated = (
            db.query(Booking)
            .filter(
                Booking.razorpay_payment_link_id == payment_link_id,
                or_(
                    Booking.payment_processed.is_(False),
                    Booking.payment_processed.is_(None),
                ),
                Booking.status != BookingStatus.CANCELLED,
            )
            .update(
                {
                    Booking.status: BookingStatus.PAID,
                    Booking.razorpay_payment_id: payment_id,
                    Booking.payment_mode: payment_mode,
                    Booking.payment_processed: True,
                    Booking.paid_at: paid_at,
                },
                synchronize_session=False,
            )
        )

        if updated:
            if commit:
                db.commit()
            else:
                db.flush()
            booking = (
                db.query(Booking)
                .filter(
                    Booking.razorpay_payment_link_id == payment_link_id
                )
                .first()
            )
            if booking:
                db.refresh(booking)
            return booking

        booking = (
            db.query(Booking)
            .filter(Booking.razorpay_payment_link_id == payment_link_id)
            .first()
        )
        if (
            booking
            and booking.payment_processed
            and booking.razorpay_payment_id == payment_id
            and booking.status in (
                BookingStatus.PAID,
                BookingStatus.COMPLETED,
            )
        ):
            return booking

        if booking and booking.payment_processed:
            logger.error(
                "Payment link already processed with another payment id "
                "| booking_id=%s",
                booking.id,
            )
        return None

    except Exception:
        db.rollback()
        logger.exception(
            "Atomic payment update failed | payment_link_id=%s",
            payment_link_id,
        )
        raise


# =========================================================
# AUTO EXPIRE OLD PENDING BOOKINGS
# =========================================================
def expire_old_pending_bookings(db):
    """Expire stale pending bookings using, but never closing, `db`."""
    try:
        expired_count = (
            db.query(Booking)
            .filter(
                Booking.status == BookingStatus.PENDING,
                Booking.created_at < _payment_expiry_cutoff(),
            )
            .update(
                {"status": BookingStatus.EXPIRED},
                synchronize_session=False,
            )
        )
        db.commit()
        # Bulk updates bypass the identity map; callers may already hold one of
        # these Booking objects and must not continue seeing PENDING.
        db.expire_all()
        if expired_count:
            logger.info("Auto-expired %s pending bookings", expired_count)
        return expired_count
    except Exception:
        db.rollback()
        logger.exception("Failed to auto-expire bookings")
        return 0
