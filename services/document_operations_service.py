"""Bounded, auditable operations for paid Document Studio orders.

The module owns recovery and refund-review decisions. Razorpay and WhatsApp
remain external adapters, and presigned artifact URLs are never persisted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from config import PAYMENT_RECONCILIATION_LOOKBACK_DAYS
from models import DocumentAuditEvent, DocumentOrder, OutboxJob, utc_now
from services.document_payment_service import (
    DocumentPaymentEvidence,
    build_document_payment_client,
    fetch_current_document_payment_evidence,
    is_full_document_refund,
    validate_current_document_capture,
)
from services.document_workflow import recover_verified_payment
from services.outbox_service import DOCUMENT_FINAL_DELIVERY_KIND, enqueue_job


logger = logging.getLogger(__name__)

_RECONCILABLE_STATES = frozenset(
    {"PAYMENT_PENDING", "NEEDS_ATTENTION", "REFUND_REVIEW"}
)
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,80}$")


@dataclass(frozen=True)
class DocumentOperationResult:
    ok: bool
    outcome: str
    reason_code: str
    order_ref: str | None = None
    job_id: int | None = None


def _canonical(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _audit(
    db,
    order: DocumentOrder,
    event_type: str,
    *,
    actor_type: str,
    actor_ref: str,
    from_state: str | None = None,
    to_state: str | None = None,
    details: dict | None = None,
) -> None:
    safe_details = {"actor_ref": str(actor_ref or "system")[:120]}
    safe_details.update(details or {})
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type=actor_type[:24],
            event_type=event_type[:64],
            from_state=from_state,
            to_state=to_state,
            details_json=_canonical(safe_details),
        )
    )


def _contains_payment_evidence(evidence: DocumentPaymentEvidence) -> bool:
    link = evidence.payment_link
    status = str(link.get("status") or "").strip().lower()
    amount_paid = link.get("amount_paid")
    payments = link.get("payments")
    return bool(
        status in {"paid", "partially_paid"}
        or (
            isinstance(amount_paid, int)
            and not isinstance(amount_paid, bool)
            and amount_paid > 0
        )
        or (isinstance(payments, list) and payments)
    )


def _payment_hash(payment_id: str | None) -> str | None:
    if not payment_id:
        return None
    return hashlib.sha256(payment_id.encode("utf-8")).hexdigest()


def enqueue_final_delivery(
    db,
    order: DocumentOrder,
    *,
    dedupe_key: str,
) -> OutboxJob:
    """Queue delivery by order identity; create short-lived URLs only later."""

    if (
        order.state != "FINAL_AVAILABLE"
        or not order.payment_processed
        or not order.final_available_until
        or order.final_available_until <= utc_now()
    ):
        raise ValueError("document_final_not_available")
    return enqueue_job(
        db,
        DOCUMENT_FINAL_DELIVERY_KIND,
        {"document_order_id": order.id},
        dedupe_key=dedupe_key,
    )


def queue_final_redelivery(
    db,
    order: DocumentOrder,
    *,
    actor_ref: str,
    reason: str,
    idempotency_key: str,
) -> DocumentOperationResult:
    """Queue one intentional operator redelivery with retry-safe deduplication."""

    normalized_reason = str(reason or "").strip()
    normalized_key = str(idempotency_key or "").strip()
    if not 10 <= len(normalized_reason) <= 300:
        return DocumentOperationResult(
            False,
            "rejected",
            "DOCUMENT_REDELIVERY_REASON_REQUIRED",
            order.public_ref,
        )
    if not _IDEMPOTENCY_KEY.fullmatch(normalized_key):
        return DocumentOperationResult(
            False,
            "rejected",
            "DOCUMENT_REDELIVERY_IDEMPOTENCY_KEY_INVALID",
            order.public_ref,
        )
    try:
        job = enqueue_final_delivery(
            db,
            order,
            dedupe_key=f"document-redelivery:{order.id}:{normalized_key}"[:255],
        )
    except ValueError as exc:
        return DocumentOperationResult(
            False,
            "rejected",
            str(exc).upper(),
            order.public_ref,
        )
    _audit(
        db,
        order,
        "DOCUMENT_FINAL_REDELIVERY_QUEUED",
        actor_type="OPERATOR",
        actor_ref=actor_ref,
        from_state=order.state,
        to_state=order.state,
        details={"job_id": job.id, "reason": normalized_reason},
    )
    return DocumentOperationResult(
        True,
        "queued",
        "DOCUMENT_FINAL_REDELIVERY_QUEUED",
        order.public_ref,
        job.id,
    )


def request_refund_review(
    db,
    order: DocumentOrder,
    *,
    actor_ref: str,
    reason: str,
) -> DocumentOperationResult:
    """Record the explicit decision to stop release and verify a manual refund."""

    normalized_reason = str(reason or "").strip()
    if not 10 <= len(normalized_reason) <= 500:
        return DocumentOperationResult(
            False,
            "rejected",
            "DOCUMENT_REFUND_REASON_REQUIRED",
            order.public_ref,
        )
    if not order.razorpay_payment_link_id or order.state not in {
        "NEEDS_ATTENTION",
        "FINAL_AVAILABLE",
        "REFUND_REVIEW",
    }:
        return DocumentOperationResult(
            False,
            "rejected",
            "DOCUMENT_REFUND_STATE_INVALID",
            order.public_ref,
        )
    if order.state == "REFUND_REVIEW":
        return DocumentOperationResult(
            True,
            "already_pending",
            "DOCUMENT_REFUND_REVIEW_ALREADY_PENDING",
            order.public_ref,
        )
    previous = order.state
    order.state = "REFUND_REVIEW"
    order.exception_code = "DOCUMENT_REFUND_PENDING"
    _audit(
        db,
        order,
        "DOCUMENT_REFUND_REVIEW_REQUESTED",
        actor_type="OPERATOR",
        actor_ref=actor_ref,
        from_state=previous,
        to_state=order.state,
        details={"reason": normalized_reason},
    )
    return DocumentOperationResult(
        True,
        "refund_review",
        "DOCUMENT_REFUND_REVIEW_REQUESTED",
        order.public_ref,
    )


def _record_review(
    db,
    order: DocumentOrder,
    reason_code: str,
    *,
    actor_type: str,
    actor_ref: str,
    payment_id: str | None,
) -> DocumentOperationResult:
    previous_state = order.state
    previous_reason = order.exception_code
    if order.state != "REFUND_REVIEW":
        order.state = "NEEDS_ATTENTION"
    order.exception_code = reason_code[:64]
    if order.state != previous_state or previous_reason != order.exception_code:
        _audit(
            db,
            order,
            "DOCUMENT_PAYMENT_REVIEW_REQUIRED",
            actor_type=actor_type,
            actor_ref=actor_ref,
            from_state=previous_state,
            to_state=order.state,
            details={
                "reason_code": order.exception_code,
                "payment_id_hash": _payment_hash(payment_id),
            },
        )
    db.commit()
    return DocumentOperationResult(
        False,
        "review_required",
        order.exception_code,
        order.public_ref,
    )


def reconcile_document_order(
    db,
    order_id: int,
    *,
    client=None,
    vault=None,
    actor_type: str = "SYSTEM",
    actor_ref: str = "system:document-payment-reconciliation",
) -> DocumentOperationResult:
    """Reconcile one order from current provider evidence and commit its result."""

    snapshot = (
        db.query(
            DocumentOrder.razorpay_payment_link_id,
            DocumentOrder.public_ref,
            DocumentOrder.state,
            DocumentOrder.payment_processed,
        )
        .filter(DocumentOrder.id == order_id)
        .first()
    )
    db.rollback()
    if not snapshot:
        return DocumentOperationResult(
            False, "not_found", "DOCUMENT_ORDER_NOT_FOUND"
        )
    payment_link_id, order_ref, snapshot_state, snapshot_processed = snapshot
    if snapshot_processed and snapshot_state == "FINAL_AVAILABLE":
        return DocumentOperationResult(
            True,
            "already_processed",
            "DOCUMENT_PAYMENT_ALREADY_PROCESSED",
            order_ref,
        )
    if not payment_link_id:
        return DocumentOperationResult(
            False,
            "skipped",
            "DOCUMENT_PAYMENT_LINK_MISSING",
            order_ref,
        )

    try:
        evidence = fetch_current_document_payment_evidence(
            str(payment_link_id),
            client=client,
        )
    except Exception as exc:
        db.rollback()
        logger.warning(
            "Document payment provider lookup failed | order_ref=%s | error=%s",
            order_ref,
            type(exc).__name__,
        )
        return DocumentOperationResult(
            False,
            "provider_error",
            "DOCUMENT_PAYMENT_PROVIDER_UNAVAILABLE",
            order_ref,
        )

    order = (
        db.query(DocumentOrder)
        .filter(DocumentOrder.id == order_id)
        .with_for_update()
        .one_or_none()
    )
    if not order:
        db.rollback()
        return DocumentOperationResult(
            False, "not_found", "DOCUMENT_ORDER_NOT_FOUND"
        )
    if order.razorpay_payment_link_id != payment_link_id:
        db.rollback()
        return DocumentOperationResult(
            False,
            "skipped",
            "DOCUMENT_PAYMENT_LINK_CHANGED",
            order.public_ref,
        )
    if order.payment_processed and order.state == "FINAL_AVAILABLE":
        db.rollback()
        return DocumentOperationResult(
            True,
            "already_processed",
            "DOCUMENT_PAYMENT_ALREADY_PROCESSED",
            order.public_ref,
        )
    if order.state not in _RECONCILABLE_STATES:
        db.rollback()
        return DocumentOperationResult(
            False,
            "skipped",
            "DOCUMENT_PAYMENT_STATE_NOT_RECONCILABLE",
            order.public_ref,
        )

    if not evidence.payment_id or not evidence.payment:
        if not _contains_payment_evidence(evidence):
            db.rollback()
            return DocumentOperationResult(
                True,
                "not_paid",
                "DOCUMENT_PAYMENT_NOT_PAID",
                order.public_ref,
            )
        return _record_review(
            db,
            order,
            "DOCUMENT_CAPTURE_COUNT_MISMATCH",
            actor_type=actor_type,
            actor_ref=actor_ref,
            payment_id=None,
        )

    payment_id = evidence.payment_id
    if is_full_document_refund(
        order,
        payment_id,
        evidence.payment_link,
        evidence.payment,
    ):
        previous = order.state
        order.state = "REFUNDED"
        order.exception_code = None
        _audit(
            db,
            order,
            "DOCUMENT_PAYMENT_REFUND_CONFIRMED",
            actor_type=actor_type,
            actor_ref=actor_ref,
            from_state=previous,
            to_state=order.state,
            details={"payment_id_hash": _payment_hash(payment_id)},
        )
        db.commit()
        return DocumentOperationResult(
            True,
            "refund_confirmed",
            "DOCUMENT_PAYMENT_REFUND_CONFIRMED",
            order.public_ref,
        )

    validation_error = validate_current_document_capture(
        order,
        payment_id,
        evidence.payment_link,
        evidence.payment,
    )
    if validation_error:
        return _record_review(
            db,
            order,
            validation_error,
            actor_type=actor_type,
            actor_ref=actor_ref,
            payment_id=payment_id,
        )
    if order.state == "REFUND_REVIEW":
        return _record_review(
            db,
            order,
            "DOCUMENT_REFUND_PENDING",
            actor_type=actor_type,
            actor_ref=actor_ref,
            payment_id=payment_id,
        )

    try:
        result = recover_verified_payment(
            db,
            order,
            payment_id=payment_id,
            payment_amount=int(evidence.payment["amount"]),
            payment_currency=str(evidence.payment["currency"]).upper(),
            actor_type=actor_type,
            vault=vault,
        )
        if not result.ok:
            return _record_review(
                db,
                order,
                result.reason_code,
                actor_type=actor_type,
                actor_ref=actor_ref,
                payment_id=payment_id,
            )
        job = enqueue_final_delivery(
            db,
            order,
            dedupe_key=f"document-payment:{payment_id}:final-delivery",
        )
        _audit(
            db,
            order,
            "DOCUMENT_PAYMENT_RECONCILED",
            actor_type=actor_type,
            actor_ref=actor_ref,
            from_state=order.state,
            to_state=order.state,
            details={
                "payment_id_hash": _payment_hash(payment_id),
                "delivery_job_id": job.id,
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        order = (
            db.query(DocumentOrder)
            .filter(DocumentOrder.id == order_id)
            .with_for_update()
            .one_or_none()
        )
        if order and not order.payment_processed:
            previous = order.state
            order.state = "NEEDS_ATTENTION"
            order.exception_code = "DOCUMENT_FINAL_RELEASE_FAILED"
            _audit(
                db,
                order,
                "DOCUMENT_FINAL_RELEASE_FAILED",
                actor_type=actor_type,
                actor_ref=actor_ref,
                from_state=previous,
                to_state=order.state,
                details={"error_type": type(exc).__name__},
            )
            db.commit()
        logger.error(
            "Document final recovery failed | order_ref=%s | error=%s",
            order_ref,
            type(exc).__name__,
        )
        return DocumentOperationResult(
            False,
            "release_failed",
            "DOCUMENT_FINAL_RELEASE_FAILED",
            order_ref,
        )

    return DocumentOperationResult(
        True,
        "recovered",
        "DOCUMENT_FINAL_RECOVERED",
        order.public_ref,
        job.id,
    )


def _new_stats() -> dict[str, int]:
    return {
        "checked": 0,
        "recovered": 0,
        "already_processed": 0,
        "not_paid": 0,
        "refund_confirmed": 0,
        "review_required": 0,
        "release_failed": 0,
        "provider_errors": 0,
        "skipped": 0,
        "not_found": 0,
    }


def reconcile_recent_document_payments(
    db,
    *,
    client=None,
    vault=None,
    limit: int = 100,
    now: datetime | None = None,
) -> dict[str, int]:
    """Reconcile a bounded recent set; isolate and commit each order."""

    stats = _new_stats()
    current = now or utc_now()
    cutoff = current - timedelta(days=PAYMENT_RECONCILIATION_LOOKBACK_DAYS)
    bounded_limit = min(max(int(limit), 1), 200)
    candidate_ids = [
        row[0]
        for row in (
            db.query(DocumentOrder.id)
            .filter(
                DocumentOrder.state.in_(_RECONCILABLE_STATES),
                DocumentOrder.razorpay_payment_link_id.isnot(None),
                DocumentOrder.updated_at >= cutoff,
            )
            .order_by(DocumentOrder.updated_at.desc(), DocumentOrder.id.desc())
            .limit(bounded_limit)
            .all()
        )
    ]
    db.rollback()

    owns_client = client is None
    active_client = client or build_document_payment_client()
    try:
        for order_id in candidate_ids:
            stats["checked"] += 1
            result = reconcile_document_order(
                db,
                order_id,
                client=active_client,
                vault=vault,
            )
            stats[result.outcome] = stats.get(result.outcome, 0) + 1
    finally:
        if owns_client:
            active_client.close()
    return stats
