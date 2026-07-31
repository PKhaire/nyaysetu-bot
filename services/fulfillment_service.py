"""Consultation-fulfilment lifecycle helpers.

Payment acceptance and provider reconciliation both use this module so every
captured payment creates the same operational work item.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from models import BookingFulfillment, utc_now
from services.booking_service import IST, SLOT_START_HOUR


_TERMINAL_STATUSES = frozenset({"COMPLETED", "REFUNDED", "CANCELLED"})


def _scheduled_start_utc(booking) -> datetime | None:
    if not booking or not booking.date or not booking.slot_code:
        return None

    start_hour = SLOT_START_HOUR.get(booking.slot_code)
    if start_hour is None:
        return None

    scheduled = datetime.combine(
        booking.date,
        datetime.min.time(),
        tzinfo=IST,
    ).replace(hour=start_hour)
    return scheduled.astimezone(timezone.utc).replace(tzinfo=None)


def ensure_booking_fulfillment(
    db,
    booking,
    *,
    capacity_conflict: str | None = None,
) -> BookingFulfillment:
    """Create or refresh the single operational record for a paid booking."""

    fulfillment = (
        db.query(BookingFulfillment)
        .filter(BookingFulfillment.booking_id == booking.id)
        .with_for_update()
        .first()
    )
    created = fulfillment is None
    if not fulfillment:
        fulfillment = BookingFulfillment(booking_id=booking.id)
        db.add(fulfillment)

    now = utc_now()
    scheduled_start = _scheduled_start_utc(booking)
    schedule_changed = fulfillment.scheduled_start_at != scheduled_start
    fulfillment.scheduled_start_at = scheduled_start

    if fulfillment.status in {None, "", "UNASSIGNED"}:
        fulfillment.status = (
            "RESCHEDULE_REQUIRED"
            if capacity_conflict
            else "UNASSIGNED"
        )
    if capacity_conflict:
        fulfillment.operator_notes = capacity_conflict[:2_000]

    # Reconciliation and webhook retries must not keep moving an existing SLA
    # forward and hiding overdue operational work. Recalculate only for new
    # work, a genuine reschedule, or legacy active rows without an SLA.
    should_set_sla = (
        fulfillment.status not in _TERMINAL_STATUSES
        and (
            created
            or schedule_changed
            or fulfillment.sla_due_at is None
        )
    )
    if should_set_sla:
        target_sla = (
            scheduled_start - timedelta(hours=2)
            if scheduled_start
            else now + timedelta(hours=4)
        )
        fulfillment.sla_due_at = max(
            now + timedelta(minutes=30),
            min(target_sla, now + timedelta(hours=4)),
        )
    db.flush()
    return fulfillment
