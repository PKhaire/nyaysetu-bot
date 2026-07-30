"""Durable, retryable delivery jobs for webhook-triggered side effects.

The preferred payment flow uses one job per external system so a failed email
cannot cause an already-accepted WhatsApp message to be resent. The legacy
``payment_followup`` composite remains supported and records progress after
each accepted side effect.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from config import (
    AUTO_SEND_RECEIPTS,
    CONSULTATION_REMINDER_CATCHUP_MINUTES,
    OUTBOX_MAX_ATTEMPTS,
    OUTBOX_RETRY_BASE_SECONDS,
    OUTBOX_RETRY_MAX_SECONDS,
    OUTBOX_RUNNING_LEASE_SECONDS,
)
from db import SessionLocal
from models import (
    Booking,
    BookingFulfillment,
    BookingStatus,
    OutboxJob,
    PaymentReconciliation,
    SupportRequest,
    User,
    utc_now,
)
from services.consultation_reminder_policy import (
    REMINDER_ELIGIBLE_FULFILLMENT_STATUSES,
    REMINDER_HORIZONS,
    as_naive_utc,
    configured_template,
    reminder_due_window,
    template_components,
)
from services.email_service import (
    send_booking_notification_email,
    send_payment_reconciliation_email,
    send_support_request_email,
)
from services.receipt_service import generate_pdf_receipt
from services.whatsapp_service import (
    WhatsAppValidationError,
    is_ambiguous_delivery_failure,
    is_retryable_delivery_failure,
    send_approved_template,
    send_buttons,
    send_list_picker,
    send_payment_receipt_pdf,
    send_payment_success_message,
    send_text,
)


logger = logging.getLogger(__name__)

PENDING = "PENDING"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
DEAD = "DEAD"
CONVERSATION_DELIVERY_KIND = "whatsapp_conversation_delivery"
_CONVERSATION_DELIVERY_STEP = "whatsapp_conversation_delivery"

# A process can die after claiming a job. Reclaiming expired leases prevents
# those jobs from remaining RUNNING forever.
RUNNING_LEASE_SECONDS = OUTBOX_RUNNING_LEASE_SECONDS
_PERMANENT_ERROR_CODES = frozenset(
    {
        "unknown_job_kind",
        "invalid_job_payload",
        "invalid_booking_id",
        "booking_not_found",
        "invalid_support_request_id",
        "support_request_not_found",
        "invalid_payment_reconciliation_id",
        "payment_reconciliation_not_found",
        "invalid_consultation_reminder_payload",
        "consultation_reminder_booking_not_found",
        "consultation_reminder_fulfillment_not_found",
        "consultation_reminder_template_not_configured",
        "invalid_consultation_reminder_template_configuration",
        "consultation_reminder_delivery_ambiguous",
        "invalid_conversation_delivery_payload",
        "conversation_delivery_ambiguous",
        "conversation_delivery_rejected",
    }
)


class DeliveryFailure(RuntimeError):
    """An external delivery was not explicitly accepted."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _utc_now() -> datetime:
    return utc_now()


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _delivery_state(payload: dict[str, Any]) -> dict[str, bool]:
    state = payload.get("_delivery")
    if not isinstance(state, dict):
        state = {}
        payload["_delivery"] = state
    return state


def _step_completed(payload: dict[str, Any], step: str) -> bool:
    return _delivery_state(payload).get(step) is True


def _mark_step_completed(
    db,
    job: OutboxJob,
    payload: dict[str, Any],
    step: str,
) -> None:
    """Commit progress before moving to another external side effect."""

    _delivery_state(payload)[step] = True
    job.payload_json = _dump_payload(payload)
    job.updated_at = _utc_now()
    db.commit()


def _require_whatsapp_success(result: Any, code: str) -> dict[str, Any]:
    """Accept only the structured success contract from WhatsApp transport."""

    if not isinstance(result, dict) or result.get("ok") is not True:
        raise DeliveryFailure(code)
    return result


def _get_paid_booking(db, payload: dict[str, Any]) -> Booking:
    try:
        booking_id = int(payload["booking_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DeliveryFailure("invalid_booking_id") from exc

    booking = db.get(Booking, booking_id)
    if not booking:
        raise DeliveryFailure("booking_not_found")
    if booking.status not in (BookingStatus.PAID, BookingStatus.COMPLETED):
        raise DeliveryFailure("booking_not_paid")
    return booking


def enqueue_job(
    db,
    kind: str,
    payload: dict[str, Any],
    *,
    dedupe_key: str | None = None,
) -> OutboxJob:
    """Add a job to the caller's transaction and flush its generated ID."""

    normalized_dedupe_key = (
        str(dedupe_key).strip()[:255] if dedupe_key else None
    )
    if normalized_dedupe_key:
        existing = (
            db.query(OutboxJob)
            .filter(OutboxJob.dedupe_key == normalized_dedupe_key)
            .first()
        )
        if existing:
            return existing

    job = OutboxJob(
        kind=kind[:80],
        dedupe_key=normalized_dedupe_key,
        payload_json=_dump_payload(payload),
        status=PENDING,
        available_at=_utc_now(),
    )
    db.add(job)
    db.flush()
    return job


def _handle_payment_success_message(
    db,
    payload: dict[str, Any],
    job: OutboxJob,
) -> None:
    if _step_completed(payload, "payment_success_message"):
        return

    booking = _get_paid_booking(db, payload)
    result = send_payment_success_message(booking)
    _require_whatsapp_success(result, "payment_success_message_not_sent")
    _mark_step_completed(db, job, payload, "payment_success_message")


def _handle_booking_notification(
    db,
    payload: dict[str, Any],
    job: OutboxJob,
) -> None:
    if _step_completed(payload, "booking_notification"):
        return

    booking = _get_paid_booking(db, payload)
    if send_booking_notification_email(booking) is not True:
        raise DeliveryFailure("booking_notification_not_sent")
    _mark_step_completed(db, job, payload, "booking_notification")


def _remove_receipt(file_path: str | None, booking_id: int) -> None:
    if not file_path:
        return
    try:
        os.remove(file_path)
    except FileNotFoundError:
        return
    except OSError as exc:
        # Never log the temporary path; a caller-provided filename can contain
        # private data.
        logger.error(
            "Temporary receipt cleanup failed | booking_id=%s | reason=%s",
            booking_id,
            type(exc).__name__,
        )


def _handle_payment_receipt(
    db,
    payload: dict[str, Any],
    job: OutboxJob,
) -> None:
    if not AUTO_SEND_RECEIPTS or _step_completed(payload, "payment_receipt"):
        return

    booking = _get_paid_booking(db, payload)
    if booking.receipt_sent:
        _mark_step_completed(db, job, payload, "payment_receipt")
        return

    pdf_path = None
    try:
        pdf_path = generate_pdf_receipt(booking)
        result = send_payment_receipt_pdf(
            booking.whatsapp_id,
            pdf_path,
            booking_id=booking.id,
        )
        _require_whatsapp_success(result, "payment_receipt_not_sent")

        # send_payment_receipt_pdf preserves its legacy tracking behavior, but
        # this assignment records the exact booking handled by this job.
        booking.receipt_sent = True
        _mark_step_completed(db, job, payload, "payment_receipt")
    finally:
        # Receipts contain PII. Keep the durable payment record, never a local
        # PDF, regardless of transport success, exceptions, or retries.
        _remove_receipt(pdf_path, booking.id)


def _handle_payment_followup(
    db,
    payload: dict[str, Any],
    job: OutboxJob,
) -> None:
    """Backward-compatible composite with durable per-step progress."""

    _handle_payment_success_message(db, payload, job)
    _handle_booking_notification(db, payload, job)
    _handle_payment_receipt(db, payload, job)


def _handle_support_notification(
    db,
    payload: dict[str, Any],
    job: OutboxJob,
) -> None:
    if _step_completed(payload, "support_notification"):
        return

    try:
        support_request_id = int(payload["support_request_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DeliveryFailure("invalid_support_request_id") from exc

    support_request = db.get(SupportRequest, support_request_id)
    if not support_request:
        raise DeliveryFailure("support_request_not_found")
    if send_support_request_email(support_request) is not True:
        raise DeliveryFailure("support_notification_not_sent")
    _mark_step_completed(db, job, payload, "support_notification")


def _handle_payment_reconciliation_alert(
    db,
    payload: dict[str, Any],
    job: OutboxJob,
) -> None:
    if _step_completed(payload, "payment_reconciliation_alert"):
        return

    try:
        reconciliation_id = int(payload["payment_reconciliation_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DeliveryFailure(
            "invalid_payment_reconciliation_id"
        ) from exc

    reconciliation = db.get(PaymentReconciliation, reconciliation_id)
    if not reconciliation:
        raise DeliveryFailure("payment_reconciliation_not_found")
    if reconciliation.status != "OPEN":
        _mark_step_completed(
            db,
            job,
            payload,
            "payment_reconciliation_alert",
        )
        return
    if send_payment_reconciliation_email(reconciliation) is not True:
        raise DeliveryFailure("payment_reconciliation_alert_not_sent")
    _mark_step_completed(
        db,
        job,
        payload,
        "payment_reconciliation_alert",
    )


def _handle_consultation_reminder(
    db,
    payload: dict[str, Any],
    job: OutboxJob,
) -> None:
    """Send one time-bounded approved template, never free-form text."""

    step = "consultation_reminder"
    if _step_completed(payload, step):
        return

    try:
        booking_id = int(payload["booking_id"])
        fulfillment_id = int(payload["fulfillment_id"])
        reminder_kind = str(payload["reminder_kind"])
        scheduled_start = as_naive_utc(
            datetime.fromisoformat(str(payload["scheduled_start_at"]))
        )
        if reminder_kind not in REMINDER_HORIZONS:
            raise ValueError("unsupported reminder kind")
    except (KeyError, TypeError, ValueError) as exc:
        raise DeliveryFailure(
            "invalid_consultation_reminder_payload"
        ) from exc

    booking = db.get(Booking, booking_id)
    if not booking:
        raise DeliveryFailure("consultation_reminder_booking_not_found")
    fulfillment = db.get(BookingFulfillment, fulfillment_id)
    if not fulfillment or fulfillment.booking_id != booking.id:
        raise DeliveryFailure(
            "consultation_reminder_fulfillment_not_found"
        )

    # Cancellation, completion, rescheduling, and exception/review states make
    # the queued reminder obsolete. These are successful no-send decisions,
    # not delivery failures that should retry.
    current_start = fulfillment.scheduled_start_at
    if (
        booking.status != BookingStatus.PAID
        or fulfillment.status
        not in REMINDER_ELIGIBLE_FULFILLMENT_STATUSES
        or current_start is None
        or as_naive_utc(current_start) != scheduled_start
    ):
        _mark_step_completed(db, job, payload, step)
        return

    now = _utc_now()
    due_at, stale_at = reminder_due_window(
        scheduled_start,
        reminder_kind,
        CONSULTATION_REMINDER_CATCHUP_MINUTES,
    )
    if now < due_at or now >= stale_at or scheduled_start <= now:
        _mark_step_completed(db, job, payload, step)
        return

    user = (
        db.query(User)
        .filter(User.whatsapp_id == booking.whatsapp_id)
        .first()
    )
    if not user:
        _mark_step_completed(db, job, payload, step)
        return
    template = configured_template(
        reminder_kind,
        user.language,
    )
    if not template:
        raise DeliveryFailure(
            "consultation_reminder_template_not_configured"
        )

    template_name, language_code = template
    try:
        result = send_approved_template(
            booking.whatsapp_id,
            template_name,
            language_code,
            components=template_components(booking),
        )
    except WhatsAppValidationError as exc:
        raise DeliveryFailure(
            "invalid_consultation_reminder_template_configuration"
        ) from exc
    if (
        isinstance(result, dict)
        and result.get("error") == "whatsapp_transport_error"
        and result.get("reason")
        not in {"ConnectError", "ConnectTimeout", "PoolTimeout"}
    ):
        # A read/write/protocol failure may occur after Meta accepted the
        # message. Do not automatically retry an ambiguous user-visible send.
        raise DeliveryFailure(
            "consultation_reminder_delivery_ambiguous"
        )
    _require_whatsapp_success(
        result,
        "consultation_reminder_not_sent",
    )
    _mark_step_completed(db, job, payload, step)


def _handle_whatsapp_conversation_delivery(
    db,
    payload: dict[str, Any],
    job: OutboxJob,
) -> None:
    """Retry one failed inbound reply without replaying its business logic."""

    if _step_completed(payload, _CONVERSATION_DELIVERY_STEP):
        return

    try:
        operation = str(payload["operation"])
        recipient = str(payload["to"])
        if operation == "text":
            result = send_text(recipient, str(payload["body"]))
        elif operation == "buttons":
            buttons = payload["buttons"]
            if not isinstance(buttons, list):
                raise ValueError("buttons must be a list")
            result = send_buttons(
                recipient,
                str(payload["body"]),
                buttons,
            )
        elif operation == "list":
            rows = payload["rows"]
            if not isinstance(rows, list):
                raise ValueError("rows must be a list")
            result = send_list_picker(
                recipient,
                header=str(payload["header"]),
                body=str(payload["body"]),
                rows=rows,
                section_title=str(payload["section_title"]),
            )
        else:
            raise ValueError("unsupported conversation delivery operation")
    except (KeyError, TypeError, ValueError) as exc:
        raise DeliveryFailure("invalid_conversation_delivery_payload") from exc

    if is_ambiguous_delivery_failure(result):
        raise DeliveryFailure("conversation_delivery_ambiguous")
    if not isinstance(result, dict) or result.get("ok") is not True:
        if is_retryable_delivery_failure(result):
            raise DeliveryFailure("conversation_delivery_not_sent")
        raise DeliveryFailure("conversation_delivery_rejected")

    # The response body and recipient are needed only until Meta accepts the
    # send. Scrub both before the job becomes terminal so retained operational
    # history does not preserve private conversation content.
    job.payload_json = _dump_payload(
        {"_delivery": {_CONVERSATION_DELIVERY_STEP: True}}
    )
    job.updated_at = _utc_now()
    db.commit()


_HANDLERS = {
    "payment_success_message": _handle_payment_success_message,
    "booking_notification": _handle_booking_notification,
    "payment_receipt": _handle_payment_receipt,
    "payment_followup": _handle_payment_followup,
    "support_notification": _handle_support_notification,
    "payment_reconciliation_alert": _handle_payment_reconciliation_alert,
    "consultation_reminder": _handle_consultation_reminder,
    CONVERSATION_DELIVERY_KIND: _handle_whatsapp_conversation_delivery,
}


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, DeliveryFailure):
        return exc.code[:500]
    return type(exc).__name__[:500]


def process_job(job_id: int) -> bool:
    """Claim and process one job. Return True only after explicit success."""

    db = SessionLocal()
    try:
        now = _utc_now()
        claimed = (
            db.query(OutboxJob)
            .filter(
                OutboxJob.id == job_id,
                OutboxJob.status == PENDING,
                OutboxJob.available_at <= now,
            )
            .update(
                {
                    OutboxJob.status: RUNNING,
                    OutboxJob.attempts: OutboxJob.attempts + 1,
                    OutboxJob.updated_at: now,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if claimed != 1:
            return False

        job = db.get(OutboxJob, job_id)
        if not job:
            return False

        try:
            handler = _HANDLERS.get(job.kind)
            if not handler:
                raise DeliveryFailure("unknown_job_kind")
            payload = json.loads(job.payload_json)
            if not isinstance(payload, dict):
                raise DeliveryFailure("invalid_job_payload")
            handler(db, payload, job)
        except Exception as exc:
            db.rollback()
            job = db.get(OutboxJob, job_id)
            if not job:
                return False

            error_code = _safe_error_code(exc)
            job.last_error = error_code
            if (
                error_code in _PERMANENT_ERROR_CODES
                or job.attempts >= OUTBOX_MAX_ATTEMPTS
            ):
                job.status = DEAD
                if job.kind == CONVERSATION_DELIVERY_KIND:
                    # A dead conversational reply cannot be delivered
                    # automatically. Retain only its operational result.
                    job.payload_json = _dump_payload(
                        {
                            "_delivery": {
                                _CONVERSATION_DELIVERY_STEP: False,
                            },
                            "redacted": True,
                        }
                    )
            else:
                delay = min(
                    OUTBOX_RETRY_BASE_SECONDS * (2 ** max(job.attempts - 1, 0)),
                    OUTBOX_RETRY_MAX_SECONDS,
                )
                job.status = PENDING
                job.available_at = _utc_now() + timedelta(seconds=delay)
            db.commit()
            logger.warning(
                "Outbox job failed | job_id=%s | kind=%s | attempt=%s | error=%s",
                job.id,
                job.kind if job.kind in _HANDLERS else "unknown",
                job.attempts,
                error_code,
            )
            return False

        job.status = COMPLETED
        job.last_error = None
        job.updated_at = _utc_now()
        db.commit()
        return True
    finally:
        db.close()


def _recover_expired_leases(db, now: datetime) -> None:
    cutoff = now - timedelta(seconds=RUNNING_LEASE_SECONDS)
    (
        db.query(OutboxJob)
        .filter(
            OutboxJob.status == RUNNING,
            OutboxJob.updated_at < cutoff,
            OutboxJob.attempts < OUTBOX_MAX_ATTEMPTS,
        )
        .update(
            {
                OutboxJob.status: PENDING,
                OutboxJob.available_at: now,
                OutboxJob.last_error: "worker_lease_expired",
                OutboxJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    (
        db.query(OutboxJob)
        .filter(
            OutboxJob.status == RUNNING,
            OutboxJob.updated_at < cutoff,
            OutboxJob.attempts >= OUTBOX_MAX_ATTEMPTS,
        )
        .update(
            {
                OutboxJob.status: DEAD,
                OutboxJob.last_error: "worker_lease_expired",
                OutboxJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()


def process_pending_jobs(limit: int = 25) -> tuple[int, int]:
    """Recover abandoned claims and process a bounded batch."""

    db = SessionLocal()
    try:
        now = _utc_now()
        _recover_expired_leases(db, now)
        job_ids = [
            row[0]
            for row in (
                db.query(OutboxJob.id)
                .filter(
                    OutboxJob.status == PENDING,
                    OutboxJob.available_at <= now,
                )
                .order_by(OutboxJob.available_at.asc(), OutboxJob.id.asc())
                .limit(max(1, min(limit, 100)))
                .all()
            )
        ]
    finally:
        db.close()

    completed = sum(1 for job_id in job_ids if process_job(job_id))
    return completed, len(job_ids) - completed


def get_outbox_health() -> dict[str, int]:
    """Return a small post-drain snapshot without exposing job payloads.

    ``ready_count`` is work that should have been eligible for the current
    bounded drain. ``deferred_count`` includes retries intentionally scheduled
    for the future and therefore is not, by itself, a worker failure.
    """

    db = SessionLocal()
    try:
        now = _utc_now()
        pending_query = db.query(OutboxJob).filter(OutboxJob.status == PENDING)
        ready_count = pending_query.filter(OutboxJob.available_at <= now).count()
        deferred_count = pending_query.filter(OutboxJob.available_at > now).count()
        running_count = (
            db.query(OutboxJob)
            .filter(OutboxJob.status == RUNNING)
            .count()
        )
        dead_count = (
            db.query(OutboxJob)
            .filter(OutboxJob.status == DEAD)
            .count()
        )
        oldest_created_at = (
            db.query(OutboxJob.created_at)
            .filter(OutboxJob.status.in_((PENDING, RUNNING, DEAD)))
            .order_by(OutboxJob.created_at.asc())
            .limit(1)
            .scalar()
        )

        oldest_age_seconds = 0
        if oldest_created_at is not None:
            if oldest_created_at.tzinfo is not None:
                oldest_created_at = oldest_created_at.replace(tzinfo=None)
            oldest_age_seconds = max(
                0,
                int((now - oldest_created_at).total_seconds()),
            )

        return {
            "backlog_count": (
                ready_count + deferred_count + running_count + dead_count
            ),
            "ready_count": ready_count,
            "deferred_count": deferred_count,
            "running_count": running_count,
            "dead_count": dead_count,
            "oldest_age_seconds": oldest_age_seconds,
        }
    finally:
        db.close()
