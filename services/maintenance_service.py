"""Conservative, bounded database housekeeping and operational risk reporting.

Only terminal operational artifacts with an explicit expiry/retention rule are
deleted. Financial reconciliation, fulfilment, support, booking, user,
feedback, conversation, and legacy message evidence is never deleted here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func

from config import (
    ANALYTICS_EVENT_TTL_DAYS,
    OUTBOX_COMPLETED_TTL_DAYS,
    PAYMENT_LINK_TTL_MINUTES,
    PAYMENT_RECONCILIATION_LOOKBACK_DAYS,
    PROCESSED_MESSAGE_TTL_DAYS,
    SUPPORT_SLA_HOURS,
)
from db import SessionLocal
from models import (
    AnalyticsEvent,
    Booking,
    BookingFulfillment,
    BookingStatus,
    InboundMessageEvent,
    OutboxJob,
    PaymentReconciliation,
    ProcessedMessage,
    SupportRequest,
    WebhookEvent,
    utc_now,
)


DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 1_000

_TERMINAL_FULFILLMENT_STATUSES = ("COMPLETED", "REFUNDED", "CANCELLED")
_ACTIVE_SUPPORT_STATUSES = ("OPEN", "IN_PROGRESS", "WAITING_USER")


class MaintenanceError(RuntimeError):
    """Raised after a failed maintenance transaction has been rolled back."""


def _as_naive_utc(value: datetime | None) -> datetime:
    current = value or utc_now()
    if current.tzinfo is not None:
        current = current.astimezone(timezone.utc).replace(tzinfo=None)
    return current


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None


def _bounded_ids(query, column, batch_size: int) -> tuple[list[int], bool]:
    """Return at most one batch of IDs and whether another eligible row exists."""

    rows = query.with_entities(column).limit(batch_size + 1).all()
    ids = [int(row[0]) for row in rows[:batch_size]]
    return ids, len(rows) > batch_size


def _category_report(
    *,
    eligible_ids: list[int],
    more_remaining: bool,
    dry_run: bool,
    affected: int = 0,
    action: str,
    retention_source: str,
    skipped_reason: str | None = None,
) -> dict[str, Any]:
    skipped = skipped_reason is not None
    return {
        "action": action,
        "retention_source": retention_source,
        "eligible_in_batch": len(eligible_ids),
        "more_remaining": more_remaining,
        "affected": 0 if dry_run or skipped else int(affected),
        "would_affect": len(eligible_ids) if dry_run and not skipped else 0,
        "skipped": skipped,
        "skip_reason": skipped_reason,
    }


def _risk_metric(db, model, timestamp_column, *filters) -> dict[str, Any]:
    count, oldest = (
        db.query(
            func.count(model.id),
            func.min(timestamp_column),
        )
        .filter(*filters)
        .one()
    )
    return {
        "count": int(count or 0),
        "oldest_at": _timestamp(oldest),
    }


def _operational_risks(db, current: datetime) -> dict[str, Any]:
    active_fulfillment = BookingFulfillment.status.notin_(
        _TERMINAL_FULFILLMENT_STATUSES
    )
    fulfillment_overdue = _risk_metric(
        db,
        BookingFulfillment,
        BookingFulfillment.sla_due_at,
        active_fulfillment,
        BookingFulfillment.sla_due_at.is_not(None),
        BookingFulfillment.sla_due_at < current,
    )
    fulfillment_without_sla = _risk_metric(
        db,
        BookingFulfillment,
        BookingFulfillment.created_at,
        active_fulfillment,
        BookingFulfillment.sla_due_at.is_(None),
    )

    active_support = SupportRequest.status.in_(_ACTIVE_SUPPORT_STATUSES)
    support_overdue = _risk_metric(
        db,
        SupportRequest,
        SupportRequest.sla_due_at,
        active_support,
        SupportRequest.sla_due_at.is_not(None),
        SupportRequest.sla_due_at < current,
    )
    support_without_sla = _risk_metric(
        db,
        SupportRequest,
        SupportRequest.created_at,
        active_support,
        SupportRequest.sla_due_at.is_(None),
        SupportRequest.created_at
        < current - timedelta(hours=SUPPORT_SLA_HOURS),
    )

    reconciliation_open = _risk_metric(
        db,
        PaymentReconciliation,
        PaymentReconciliation.created_at,
        PaymentReconciliation.status == "OPEN",
    )
    reconciliation_stale = _risk_metric(
        db,
        PaymentReconciliation,
        PaymentReconciliation.created_at,
        PaymentReconciliation.status == "OPEN",
        PaymentReconciliation.created_at
        < current - timedelta(days=PAYMENT_RECONCILIATION_LOOKBACK_DAYS),
    )

    actionable = sum(
        metric["count"]
        for metric in (
            fulfillment_overdue,
            fulfillment_without_sla,
            support_overdue,
            support_without_sla,
            reconciliation_stale,
        )
    )
    return {
        "fulfillment": {
            "overdue": fulfillment_overdue,
            "active_without_sla": fulfillment_without_sla,
        },
        "support": {
            "overdue": support_overdue,
            "active_without_sla_beyond_configured_sla": support_without_sla,
            "sla_hours": SUPPORT_SLA_HOURS,
        },
        "payment_reconciliation": {
            "open": reconciliation_open,
            "open_older_than_lookback": reconciliation_stale,
            "lookback_days": PAYMENT_RECONCILIATION_LOOKBACK_DAYS,
        },
        "summary": {
            "actionable_signals": actionable,
            "alert_required": actionable > 0,
            "financial_evidence_mutated": False,
        },
    }


def run_maintenance(
    *,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    now: datetime | None = None,
    session_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run one bounded maintenance transaction and return a PII-free report."""

    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ValueError("batch_size must be an integer")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(
            f"batch_size must be between 1 and {MAX_BATCH_SIZE}"
        )

    current = _as_naive_utc(now)
    processed_cutoff = current - timedelta(days=PROCESSED_MESSAGE_TTL_DAYS)
    analytics_cutoff = current - timedelta(days=ANALYTICS_EVENT_TTL_DAYS)
    outbox_cutoff = current - timedelta(days=OUTBOX_COMPLETED_TTL_DAYS)
    booking_cutoff = current - timedelta(minutes=PAYMENT_LINK_TTL_MINUTES)

    factory = session_factory or SessionLocal
    db = factory()
    categories: dict[str, dict[str, Any]] = {}

    try:
        booking_query = (
            db.query(Booking)
            .filter(
                Booking.status == BookingStatus.PENDING,
                Booking.created_at < booking_cutoff,
            )
            .order_by(Booking.created_at.asc(), Booking.id.asc())
        )
        booking_ids, booking_more = _bounded_ids(
            booking_query,
            Booking.id,
            batch_size,
        )
        bookings_affected = 0
        if booking_ids and not dry_run:
            bookings_affected = (
                db.query(Booking)
                .filter(
                    Booking.id.in_(booking_ids),
                    Booking.status == BookingStatus.PENDING,
                    Booking.created_at < booking_cutoff,
                )
                .update(
                    {Booking.status: BookingStatus.EXPIRED},
                    synchronize_session=False,
                )
            )
        categories["pending_bookings"] = _category_report(
            eligible_ids=booking_ids,
            more_remaining=booking_more,
            dry_run=dry_run,
            affected=bookings_affected,
            action="expire",
            retention_source="PAYMENT_LINK_TTL_MINUTES",
        )

        webhook_query = (
            db.query(WebhookEvent)
            .filter(
                WebhookEvent.status == "DONE",
                WebhookEvent.expires_at.is_not(None),
                WebhookEvent.expires_at <= current,
            )
            .order_by(WebhookEvent.expires_at.asc(), WebhookEvent.id.asc())
        )
        webhook_ids, webhook_more = _bounded_ids(
            webhook_query,
            WebhookEvent.id,
            batch_size,
        )
        webhooks_affected = 0
        if webhook_ids and not dry_run:
            webhooks_affected = (
                db.query(WebhookEvent)
                .filter(
                    WebhookEvent.id.in_(webhook_ids),
                    WebhookEvent.status == "DONE",
                    WebhookEvent.expires_at.is_not(None),
                    WebhookEvent.expires_at <= current,
                )
                .delete(synchronize_session=False)
            )
        categories["webhook_events"] = _category_report(
            eligible_ids=webhook_ids,
            more_remaining=webhook_more,
            dry_run=dry_run,
            affected=webhooks_affected,
            action="delete",
            retention_source="WEBHOOK_EVENT_TTL_DAYS/expires_at",
        )

        inbound_query = (
            db.query(InboundMessageEvent)
            .filter(
                InboundMessageEvent.status == "DONE",
                InboundMessageEvent.expires_at.is_not(None),
                InboundMessageEvent.expires_at <= current,
            )
            .order_by(
                InboundMessageEvent.expires_at.asc(),
                InboundMessageEvent.id.asc(),
            )
        )
        inbound_ids, inbound_more = _bounded_ids(
            inbound_query,
            InboundMessageEvent.id,
            batch_size,
        )
        inbound_affected = 0
        if inbound_ids and not dry_run:
            inbound_affected = (
                db.query(InboundMessageEvent)
                .filter(
                    InboundMessageEvent.id.in_(inbound_ids),
                    InboundMessageEvent.status == "DONE",
                    InboundMessageEvent.expires_at.is_not(None),
                    InboundMessageEvent.expires_at <= current,
                )
                .delete(synchronize_session=False)
            )
        categories["inbound_message_events"] = _category_report(
            eligible_ids=inbound_ids,
            more_remaining=inbound_more,
            dry_run=dry_run,
            affected=inbound_affected,
            action="delete",
            retention_source="PROCESSED_MESSAGE_TTL_DAYS/expires_at",
        )

        legacy_query = (
            db.query(ProcessedMessage)
            .filter(ProcessedMessage.created_at <= processed_cutoff)
            .order_by(ProcessedMessage.created_at.asc(), ProcessedMessage.id.asc())
        )
        legacy_ids, legacy_more = _bounded_ids(
            legacy_query,
            ProcessedMessage.id,
            batch_size,
        )
        categories["legacy_processed_messages"] = _category_report(
            eligible_ids=legacy_ids,
            more_remaining=legacy_more,
            dry_run=dry_run,
            action="retain",
            retention_source="PROCESSED_MESSAGE_TTL_DAYS",
            skipped_reason="legacy_claims_are_never_pruned",
        )

        analytics_query = (
            db.query(AnalyticsEvent)
            .filter(AnalyticsEvent.created_at <= analytics_cutoff)
            .order_by(AnalyticsEvent.created_at.asc(), AnalyticsEvent.id.asc())
        )
        analytics_ids, analytics_more = _bounded_ids(
            analytics_query,
            AnalyticsEvent.id,
            batch_size,
        )
        analytics_affected = 0
        if analytics_ids and not dry_run:
            analytics_affected = (
                db.query(AnalyticsEvent)
                .filter(
                    AnalyticsEvent.id.in_(analytics_ids),
                    AnalyticsEvent.created_at <= analytics_cutoff,
                )
                .delete(synchronize_session=False)
            )
        categories["analytics_events"] = _category_report(
            eligible_ids=analytics_ids,
            more_remaining=analytics_more,
            dry_run=dry_run,
            affected=analytics_affected,
            action="delete",
            retention_source="ANALYTICS_EVENT_TTL_DAYS",
        )

        outbox_query = (
            db.query(OutboxJob)
            .filter(
                OutboxJob.status == "COMPLETED",
                OutboxJob.updated_at <= outbox_cutoff,
            )
            .order_by(OutboxJob.updated_at.asc(), OutboxJob.id.asc())
        )
        outbox_ids, outbox_more = _bounded_ids(
            outbox_query,
            OutboxJob.id,
            batch_size,
        )
        outbox_affected = 0
        if outbox_ids and not dry_run:
            outbox_affected = (
                db.query(OutboxJob)
                .filter(
                    OutboxJob.id.in_(outbox_ids),
                    OutboxJob.status == "COMPLETED",
                    OutboxJob.updated_at <= outbox_cutoff,
                )
                .delete(synchronize_session=False)
            )
        categories["completed_outbox_jobs"] = _category_report(
            eligible_ids=outbox_ids,
            more_remaining=outbox_more,
            dry_run=dry_run,
            affected=outbox_affected,
            action="delete",
            retention_source="OUTBOX_COMPLETED_TTL_DAYS",
        )

        risks = _operational_risks(db, current)
        if dry_run:
            db.rollback()
        else:
            db.commit()

        return {
            "ok": True,
            "dry_run": bool(dry_run),
            "batch_size": batch_size,
            "generated_at": _timestamp(current),
            "categories": categories,
            "operational_risks": risks,
            "preserved": [
                "legacy_processed_messages",
                "booking_records",
                "booking_fulfillments",
                "payment_reconciliations",
                "users",
                "support_requests",
                "feedback",
                "conversations",
                "dead_or_failed_outbox_jobs",
                "failed_or_unmatched_webhook_events",
                "nonterminal_inbound_message_events",
            ],
        }
    except Exception as exc:
        db.rollback()
        raise MaintenanceError(type(exc).__name__) from exc
    finally:
        db.close()
