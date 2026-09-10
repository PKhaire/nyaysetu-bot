"""Global, auditable daily capacity for Draft Studio.

Capacity is shared by every eligible user. PostgreSQL advisory transaction
locks serialize the count-and-reserve operation for one India business date,
so concurrent requests cannot allocate the same final slot.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, text

from config import APP_TIMEZONE, DOCUMENT_STUDIO_DAILY_CAPACITY
from models import DocumentCapacityReservation, DocumentOrder, utc_now


COUNTED_CAPACITY_STATUSES = ("RESERVED", "CONSUMED")


class DocumentStudioCapacityExhausted(RuntimeError):
    """Raised before a new draft is created when no daily slot remains."""

    def __init__(self, business_date: date, capacity_limit: int):
        super().__init__("document_studio_daily_capacity_reached")
        self.business_date = business_date
        self.capacity_limit = capacity_limit


def business_date_for(value: datetime | None = None) -> date:
    """Return the configured local business date for a UTC instant."""

    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(ZoneInfo(APP_TIMEZONE)).date()


def _capacity_lock_key(business_date: date) -> int:
    digest = hashlib.sha256(
        f"nyaysetu:document-studio-capacity:{business_date.isoformat()}".encode(
            "ascii"
        )
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _lock_business_date(db, business_date: date) -> None:
    """Serialize reservation changes on PostgreSQL until transaction end."""

    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _capacity_lock_key(business_date)},
        )


def _reservation_for_order(
    db,
    document_order_id: int,
) -> DocumentCapacityReservation | None:
    return (
        db.query(DocumentCapacityReservation)
        .filter(
            DocumentCapacityReservation.document_order_id
            == document_order_id
        )
        .one_or_none()
    )


def capacity_snapshot(
    db,
    *,
    value: datetime | None = None,
) -> dict[str, object]:
    """Return privacy-safe capacity metrics for one local business date."""

    db.flush()
    business_date = business_date_for(value)
    counts = {
        str(status): int(count)
        for status, count in (
            db.query(
                DocumentCapacityReservation.status,
                func.count(DocumentCapacityReservation.id),
            )
            .filter(
                DocumentCapacityReservation.business_date == business_date
            )
            .group_by(DocumentCapacityReservation.status)
            .all()
        )
    }
    reserved = counts.get("RESERVED", 0)
    consumed = counts.get("CONSUMED", 0)
    released = counts.get("RELEASED", 0)
    used = reserved + consumed
    return {
        "business_date": business_date.isoformat(),
        "timezone": APP_TIMEZONE,
        "limit": DOCUMENT_STUDIO_DAILY_CAPACITY,
        "reserved": reserved,
        "consumed": consumed,
        "released": released,
        "used": used,
        "remaining": max(0, DOCUMENT_STUDIO_DAILY_CAPACITY - used),
        "exhausted": used >= DOCUMENT_STUDIO_DAILY_CAPACITY,
    }


def reserve_capacity(
    db,
    order: DocumentOrder,
    *,
    value: datetime | None = None,
) -> DocumentCapacityReservation:
    """Idempotently reserve one global daily slot for a new/resumed draft."""

    if order.id is None:
        db.flush()
    existing = _reservation_for_order(db, order.id)
    if existing is not None:
        return existing

    business_date = business_date_for(value)
    _lock_business_date(db, business_date)

    # Recheck after acquiring the PostgreSQL lock because another transaction
    # may have committed while this transaction was waiting.
    existing = _reservation_for_order(db, order.id)
    if existing is not None:
        return existing

    used = (
        db.query(func.count(DocumentCapacityReservation.id))
        .filter(
            DocumentCapacityReservation.business_date == business_date,
            DocumentCapacityReservation.status.in_(
                COUNTED_CAPACITY_STATUSES
            ),
        )
        .scalar()
        or 0
    )
    if used >= DOCUMENT_STUDIO_DAILY_CAPACITY:
        raise DocumentStudioCapacityExhausted(
            business_date,
            DOCUMENT_STUDIO_DAILY_CAPACITY,
        )

    reservation = DocumentCapacityReservation(
        document_order_id=order.id,
        business_date=business_date,
        capacity_limit=DOCUMENT_STUDIO_DAILY_CAPACITY,
        status="RESERVED",
    )
    db.add(reservation)
    db.flush()
    return reservation


def consume_capacity(
    db,
    order: DocumentOrder,
) -> DocumentCapacityReservation:
    """Mark a reservation consumed once the user confirms the full draft."""

    reservation = _reservation_for_order(db, order.id)
    if reservation is None:
        reservation = reserve_capacity(db, order)
    if reservation.status == "RELEASED":
        raise RuntimeError("document_capacity_reservation_already_released")
    if reservation.status == "RESERVED":
        reservation.status = "CONSUMED"
        reservation.consumed_at = utc_now()
        reservation.updated_at = utc_now()
    return reservation


def release_capacity(
    db,
    order: DocumentOrder,
    *,
    reason: str,
) -> bool:
    """Release an unconsumed slot; consumed drafting work stays counted."""

    reservation = _reservation_for_order(db, order.id)
    if reservation is None or reservation.status != "RESERVED":
        return False

    _lock_business_date(db, reservation.business_date)
    reservation = _reservation_for_order(db, order.id)
    if reservation is None or reservation.status != "RESERVED":
        return False

    reservation.status = "RELEASED"
    reservation.release_reason = str(reason or "UNSPECIFIED")[:64]
    reservation.released_at = utc_now()
    reservation.updated_at = utc_now()
    return True
