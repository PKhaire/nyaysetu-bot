"""Bounded, idempotent scheduling for paid consultation reminders."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError

from config import (
    CONSULTATION_REMINDER_BATCH_SIZE,
    CONSULTATION_REMINDER_CATCHUP_MINUTES,
)
from db import SessionLocal
from models import (
    Booking,
    BookingFulfillment,
    BookingStatus,
    OutboxJob,
    User,
    utc_now,
)
from services.consultation_reminder_policy import (
    REMINDER_ELIGIBLE_FULFILLMENT_STATUSES,
    REMINDER_HORIZONS,
    as_naive_utc,
    configured_template,
    configured_variant_count,
)
from services.outbox_service import enqueue_job


DEFAULT_BATCH_SIZE = CONSULTATION_REMINDER_BATCH_SIZE
MAX_BATCH_SIZE = 500
MAX_SCAN_SIZE = 2_500
REMINDER_JOB_KIND = "consultation_reminder"


class ConsultationReminderError(RuntimeError):
    """Raised after a reminder scheduling transaction is rolled back."""


def _dedupe_key(
    fulfillment_id: int,
    scheduled_start_at: datetime,
    reminder_kind: str,
) -> str:
    scheduled = as_naive_utc(scheduled_start_at).isoformat(
        timespec="microseconds"
    )
    return (
        f"consultation-reminder:v1:{reminder_kind}:"
        f"{fulfillment_id}:{scheduled}"
    )


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds") + "Z"


def schedule_consultation_reminders(
    *,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    now: datetime | None = None,
    session_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Enqueue one bounded batch without exposing booking or user data."""

    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ValueError("batch_size must be an integer")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(
            f"batch_size must be between 1 and {MAX_BATCH_SIZE}"
        )

    current = as_naive_utc(now or utc_now())
    configured_variants = configured_variant_count()
    report: dict[str, Any] = {
        "ok": True,
        "dry_run": bool(dry_run),
        "enabled": configured_variants > 0,
        "configured_variants": configured_variants,
        "batch_size": batch_size,
        "scan_limit": min(MAX_SCAN_SIZE, batch_size * 5),
        "generated_at": _timestamp(current),
        "scanned": 0,
        "enqueued": 0,
        "would_enqueue": 0,
        "duplicates": 0,
        "skipped_unconfigured": 0,
        "more_remaining": False,
    }
    if configured_variants == 0:
        return report

    factory = session_factory or SessionLocal
    db = factory()
    try:
        remaining_jobs = batch_size
        remaining_scan = report["scan_limit"]
        # Imminent reminders take priority if a large backlog fills one batch.
        for reminder_kind in ("2h", "24h"):
            if remaining_jobs <= 0 or remaining_scan <= 0:
                report["more_remaining"] = True
                break

            scheduled_after = (
                current
                + REMINDER_HORIZONS[reminder_kind]
                - timedelta(
                    minutes=CONSULTATION_REMINDER_CATCHUP_MINUTES
                )
            )
            scheduled_through = current + REMINDER_HORIZONS[reminder_kind]

            rows = (
                db.query(BookingFulfillment, Booking, User)
                .join(
                    Booking,
                    Booking.id == BookingFulfillment.booking_id,
                )
                .outerjoin(User, User.whatsapp_id == Booking.whatsapp_id)
                .filter(
                    Booking.status == BookingStatus.PAID,
                    BookingFulfillment.status.in_(
                        REMINDER_ELIGIBLE_FULFILLMENT_STATUSES
                    ),
                    BookingFulfillment.scheduled_start_at
                    > scheduled_after,
                    BookingFulfillment.scheduled_start_at
                    <= scheduled_through,
                )
                .order_by(
                    BookingFulfillment.scheduled_start_at.asc(),
                    BookingFulfillment.id.asc(),
                )
                .limit(remaining_scan + 1)
                .all()
            )
            if len(rows) > remaining_scan:
                report["more_remaining"] = True
                rows = rows[:remaining_scan]

            for index, (fulfillment, booking, user) in enumerate(rows):
                report["scanned"] += 1
                remaining_scan -= 1
                if user is None:
                    report["skipped_unconfigured"] += 1
                    continue
                user_language = getattr(user, "language", None)
                if not configured_template(reminder_kind, user_language):
                    report["skipped_unconfigured"] += 1
                    continue

                scheduled_start = as_naive_utc(
                    fulfillment.scheduled_start_at
                )
                dedupe_key = _dedupe_key(
                    fulfillment.id,
                    scheduled_start,
                    reminder_kind,
                )
                existing = (
                    db.query(OutboxJob.id)
                    .filter(OutboxJob.dedupe_key == dedupe_key)
                    .first()
                )
                if existing:
                    report["duplicates"] += 1
                    continue

                if dry_run:
                    report["would_enqueue"] += 1
                    remaining_jobs -= 1
                    if remaining_jobs <= 0:
                        report["more_remaining"] = (
                            report["more_remaining"]
                            or index + 1 < len(rows)
                            or reminder_kind == "2h"
                        )
                        break
                    continue

                payload = {
                    "booking_id": booking.id,
                    "fulfillment_id": fulfillment.id,
                    "reminder_kind": reminder_kind,
                    "scheduled_start_at": scheduled_start.isoformat(
                        timespec="microseconds"
                    ),
                }
                try:
                    with db.begin_nested():
                        job = enqueue_job(
                            db,
                            REMINDER_JOB_KIND,
                            payload,
                            dedupe_key=dedupe_key,
                        )
                        job.available_at = current
                except IntegrityError:
                    # A concurrent scheduler won the unique-key race.
                    report["duplicates"] += 1
                    continue
                report["enqueued"] += 1
                remaining_jobs -= 1
                if remaining_jobs <= 0:
                    report["more_remaining"] = (
                        report["more_remaining"]
                        or index + 1 < len(rows)
                        or reminder_kind == "2h"
                    )
                    break

        if dry_run:
            db.rollback()
        else:
            db.commit()
        return report
    except Exception as exc:
        db.rollback()
        raise ConsultationReminderError(type(exc).__name__) from exc
    finally:
        db.close()
