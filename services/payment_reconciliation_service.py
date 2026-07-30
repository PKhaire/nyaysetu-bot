"""Recover captured Razorpay payments whose webhook was missed.

The reconciler uses Razorpay's authenticated payment-link lookup as an
independent safety net. It automatically accepts a payment only when every
identity, amount, currency, partial-payment, and capture check is exact.
Anything ambiguous is retained for an operator instead of changing a booking.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import or_

from config import (
    AUTO_SEND_RECEIPTS,
    BOOKING_NOTIFICATION_EMAILS,
    PAYMENT_RECONCILIATION_LOOKBACK_DAYS,
    RAZORPAY_API_TIMEOUT_SECONDS,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_MODE,
    SUPPORT_NOTIFICATION_EMAILS,
)
from models import (
    AdminAuditEvent,
    Booking,
    BookingStatus,
    PaymentReconciliation,
    User,
    utc_now,
)
from services.booking_service import (
    mark_booking_as_paid,
    payment_capacity_conflict,
)
from services.fulfillment_service import ensure_booking_fulfillment
from services.outbox_service import enqueue_job


logger = logging.getLogger(__name__)
RAZORPAY_API_BASE_URL = "https://api.razorpay.com"
_PAYMENT_LINK_ID_PATTERN = re.compile(r"plink_[A-Za-z0-9]{1,249}")
_PAYMENT_ID_PATTERN = re.compile(r"pay_[A-Za-z0-9]{1,251}")
_MANUAL_RECONCILIATION_STATUSES = frozenset(
    {"RESOLVED", "REFUND_INITIATED", "REFUNDED", "IGNORED"}
)
_CLOSED_RECONCILIATION_STATUSES = (
    _MANUAL_RECONCILIATION_STATUSES | {"AUTO_RESOLVED"}
)


def _new_stats() -> dict[str, int]:
    return {
        "checked": 0,
        "recovered": 0,
        "already_processed": 0,
        "not_paid": 0,
        "review_required": 0,
        "provider_errors": 0,
    }


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _expected_amount(booking: Booking) -> int | None:
    booking_amount = _safe_int(booking.amount)
    if booking_amount is None or booking_amount <= 0:
        return None
    return booking_amount * 100


def _captured_payment_id(entity: dict[str, Any]) -> str | None:
    payments = entity.get("payments")
    if not isinstance(payments, list) or len(payments) != 1:
        return None
    payment = payments[0]
    if not isinstance(payment, dict):
        return None
    value = payment.get("payment_id")
    if not isinstance(value, str):
        return None
    payment_id = value.strip()
    if not _PAYMENT_ID_PATTERN.fullmatch(payment_id):
        return None
    return payment_id


def _payment_id(entity: dict[str, Any], payment_link_id: str) -> str:
    captured_payment_id = _captured_payment_id(entity)
    if captured_payment_id:
        return captured_payment_id
    return f"link:{payment_link_id}"[:255]


def _validation_error(
    booking: Booking,
    entity: dict[str, Any],
) -> str | None:
    """Return a stable review reason unless this is one exact full capture."""

    link_id = str(entity.get("id") or "").strip()
    if link_id != booking.razorpay_payment_link_id:
        return "PROVIDER_LINK_ID_MISMATCH"

    if str(entity.get("status") or "").lower() != "paid":
        return "PAYMENT_LINK_NOT_PAID"

    expected_amount = _expected_amount(booking)
    if expected_amount is None:
        return "INVALID_BOOKING_AMOUNT"
    if (
        _safe_int(entity.get("amount")) != expected_amount
        or _safe_int(entity.get("amount_paid")) != expected_amount
    ):
        return "PROVIDER_AMOUNT_MISMATCH"

    # Razorpay documents INR as the default and may return an explicit empty
    # string for that default. A missing, null, or non-string field is instead
    # malformed evidence and must never be treated as INR.
    raw_currency = entity.get("currency")
    if not isinstance(raw_currency, str):
        return "PROVIDER_CURRENCY_MISMATCH"
    if raw_currency == "":
        currency = "INR"
    else:
        currency = raw_currency.strip().upper()
    if currency != "INR":
        return "PROVIDER_CURRENCY_MISMATCH"

    if entity.get("accept_partial") is not False:
        return "PARTIAL_PAYMENT_CONFIGURATION"

    raw_reference_id = entity.get("reference_id")
    reference_id = (
        raw_reference_id.strip()
        if isinstance(raw_reference_id, str)
        else ""
    )
    if not booking.payment_token or reference_id != booking.payment_token:
        return "PROVIDER_REFERENCE_MISMATCH"

    notes = entity.get("notes")
    if not isinstance(notes, dict):
        return "PROVIDER_NOTES_MISSING"
    raw_note_booking_id = notes.get("booking_id")
    note_booking_id = (
        raw_note_booking_id.strip()
        if isinstance(raw_note_booking_id, str)
        else ""
    )
    raw_note_token = notes.get("booking_token")
    note_token = (
        raw_note_token.strip() if isinstance(raw_note_token, str) else ""
    )
    if note_booking_id != str(booking.id):
        return "PROVIDER_NOTE_BOOKING_MISMATCH"
    if note_token != booking.payment_token:
        return "PROVIDER_NOTE_TOKEN_MISMATCH"

    payments = entity.get("payments")
    if not isinstance(payments, list) or len(payments) != 1:
        return "CAPTURE_COUNT_MISMATCH"

    payment = payments[0]
    if not isinstance(payment, dict):
        return "INVALID_CAPTURE_DETAILS"
    if str(payment.get("status") or "").lower() != "captured":
        return "PAYMENT_NOT_CAPTURED"
    if _safe_int(payment.get("amount")) != expected_amount:
        return "CAPTURE_AMOUNT_MISMATCH"
    raw_payment_id = payment.get("payment_id")
    if not isinstance(raw_payment_id, str) or not raw_payment_id.strip():
        return "PAYMENT_ID_MISSING"
    if not _PAYMENT_ID_PATTERN.fullmatch(raw_payment_id.strip()):
        return "PAYMENT_ID_INVALID"
    return None


def _payment_detail_validation_error(
    booking: Booking,
    payment_id: str,
    entity: dict[str, Any] | None,
) -> str | None:
    """Require current, non-refunded payment evidence before auto-recovery."""

    if not isinstance(entity, dict):
        return "INVALID_PAYMENT_DETAILS"
    raw_id = entity.get("id")
    if not isinstance(raw_id, str) or raw_id.strip() != payment_id:
        return "PAYMENT_DETAIL_ID_MISMATCH"
    if entity.get("entity") != "payment":
        return "PAYMENT_DETAIL_ENTITY_MISMATCH"
    if str(entity.get("status") or "").lower() != "captured":
        return "PAYMENT_DETAIL_NOT_CAPTURED"
    if entity.get("captured") is not True:
        return "PAYMENT_DETAIL_NOT_CAPTURED"

    expected_amount = _expected_amount(booking)
    if (
        expected_amount is None
        or _safe_int(entity.get("amount")) != expected_amount
    ):
        return "PAYMENT_DETAIL_AMOUNT_MISMATCH"

    raw_currency = entity.get("currency")
    if (
        not isinstance(raw_currency, str)
        or raw_currency.strip().upper() != "INR"
    ):
        return "PAYMENT_DETAIL_CURRENCY_MISMATCH"

    if (
        _safe_int(entity.get("amount_refunded")) != 0
        or entity.get("refund_status") is not None
    ):
        return "PAYMENT_ALREADY_REFUNDED"
    return None


def _contains_payment_evidence(entity: dict[str, Any]) -> bool:
    status = str(entity.get("status") or "").strip().lower()
    amount_paid = _safe_int(entity.get("amount_paid"))
    payments = entity.get("payments")
    return (
        status in {"paid", "partially_paid"}
        or (amount_paid is not None and amount_paid > 0)
        or (isinstance(payments, list) and bool(payments))
    )


def _find_reconciliation(
    db,
    payment_id: str,
) -> PaymentReconciliation | None:
    return (
        db.query(PaymentReconciliation)
        .filter(
            PaymentReconciliation.provider == "razorpay",
            PaymentReconciliation.payment_id == payment_id,
        )
        .with_for_update()
        .first()
    )


def lock_matching_payment_reconciliations(
    db,
    *,
    payment_id: str | None,
    payment_link_id: str | None,
) -> list[PaymentReconciliation]:
    """Lock all known reviews for one provider payment/link identity.

    Locking OPEN rows as well as terminal rows prevents an operator terminal
    disposition from racing with automatic payment acceptance.
    """

    identity_filters = []
    if payment_id:
        identity_filters.append(
            PaymentReconciliation.payment_id == payment_id
        )
    if payment_link_id:
        identity_filters.append(
            PaymentReconciliation.payment_link_id == payment_link_id
        )
    if not identity_filters:
        return []

    query = db.query(PaymentReconciliation).filter(
        PaymentReconciliation.provider == "razorpay",
        or_(*identity_filters),
    )
    if payment_id:
        query = query.order_by(
            (
                PaymentReconciliation.payment_id == payment_id
            ).desc(),
            PaymentReconciliation.id.desc(),
        )
    else:
        query = query.order_by(PaymentReconciliation.id.desc())
    return query.with_for_update().all()


def _identity_conflicts(
    item: PaymentReconciliation,
    booking: Booking,
) -> bool:
    payment_link_id = str(booking.razorpay_payment_link_id or "")
    return (
        item.booking_id is not None
        and item.booking_id != booking.id
    ) or (
        bool(item.payment_link_id)
        and item.payment_link_id != payment_link_id
    )


def _has_manual_disposition(
    db,
    booking: Booking,
    payment_id: str,
) -> bool:
    payment_link_id = str(booking.razorpay_payment_link_id or "")
    return any(
        item.status in _MANUAL_RECONCILIATION_STATUSES
        for item in lock_matching_payment_reconciliations(
            db,
            payment_id=payment_id,
            payment_link_id=payment_link_id,
        )
    )


def _upsert_review(
    db,
    *,
    booking: Booking,
    entity: dict[str, Any],
    reason: str,
    status: str = "OPEN",
) -> PaymentReconciliation:
    payment_link_id = str(booking.razorpay_payment_link_id or "")
    payment_id = _payment_id(entity, payment_link_id)
    item = _find_reconciliation(db, payment_id)

    # A provider payment id must never be silently moved between bookings.
    # Preserve the original evidence and create/link a stable link-scoped
    # review for the conflicting observation.
    if item and _identity_conflicts(item, booking):
        payment_id = f"link:{payment_link_id}"[:255]
        item = _find_reconciliation(db, payment_id)

    # Scheduled runs may revisit the same provider evidence. They must not
    # reopen or rewrite a system/operator disposition that is already final.
    if item and item.status in _CLOSED_RECONCILIATION_STATUSES:
        return item

    if not item:
        item = PaymentReconciliation(
            provider="razorpay",
            payment_id=payment_id,
        )
        db.add(item)

    item.payment_link_id = payment_link_id
    item.booking_id = booking.id
    item.reason = reason[:64]
    item.status = status
    item.expected_amount = _expected_amount(booking)
    item.received_amount = _safe_int(entity.get("amount_paid"))
    raw_currency = entity.get("currency")
    normalized_currency = ""
    if isinstance(raw_currency, str):
        normalized_currency = (
            "INR" if raw_currency == "" else raw_currency.strip().upper()
        )
    item.currency = (
        (normalized_currency or None)
        if isinstance(raw_currency, str)
        else None
    )
    payments = entity.get("payments")
    item.details_json = json.dumps(
        {
            "accept_partial": entity.get("accept_partial"),
            "payment_count": len(payments) if isinstance(payments, list) else 0,
            "provider_status": str(entity.get("status") or "")[:32],
            "source": "scheduled_provider_reconciliation",
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    if status == "AUTO_RESOLVED":
        item.resolved_at = utc_now()
        item.resolved_by = "system:payment-reconciliation"
        item.resolution_note = (
            "Recovered from Razorpay's authenticated payment-link lookup."
        )
    else:
        item.resolved_at = None
        item.resolved_by = None
        item.resolution_note = None
    db.flush()
    if status == "OPEN" and (
        BOOKING_NOTIFICATION_EMAILS or SUPPORT_NOTIFICATION_EMAILS
    ):
        enqueue_job(
            db,
            "payment_reconciliation_alert",
            {"payment_reconciliation_id": item.id},
            dedupe_key=(
                f"payment-review:{item.id}:"
                f"{item.reason[:64]}"
            ),
        )
    return item


def _enqueue_payment_followups(db, booking: Booking, payment_id: str) -> None:
    enqueue_job(
        db,
        "payment_success_message",
        {"booking_id": booking.id},
        dedupe_key=f"payment:{payment_id}:success-message",
    )
    if BOOKING_NOTIFICATION_EMAILS:
        enqueue_job(
            db,
            "booking_notification",
            {"booking_id": booking.id},
            dedupe_key=f"payment:{payment_id}:booking-notification",
        )
    if AUTO_SEND_RECEIPTS:
        enqueue_job(
            db,
            "payment_receipt",
            {"booking_id": booking.id},
            dedupe_key=f"payment:{payment_id}:receipt",
        )


def _recover_exact_capture(
    db,
    booking: Booking,
    entity: dict[str, Any],
) -> str:
    payment_id = _payment_id(
        entity,
        str(booking.razorpay_payment_link_id or ""),
    )

    if booking.payment_processed:
        if (
            booking.razorpay_payment_id == payment_id
            and booking.status in (BookingStatus.PAID, BookingStatus.COMPLETED)
        ):
            ensure_booking_fulfillment(db, booking)
            _enqueue_payment_followups(db, booking, payment_id)
            _upsert_review(
                db,
                booking=booking,
                entity=entity,
                reason="PROVIDER_CAPTURE_ALREADY_PROCESSED",
                status="AUTO_RESOLVED",
            )
            db.commit()
            return "already_processed"

        _upsert_review(
            db,
            booking=booking,
            entity=entity,
            reason="BOOKING_ALREADY_PAID_WITH_DIFFERENT_PAYMENT",
        )
        db.commit()
        return "review_required"

    capacity_conflict = payment_capacity_conflict(db, booking)
    paid_booking = mark_booking_as_paid(
        db=db,
        payment_link_id=str(booking.razorpay_payment_link_id),
        payment_id=payment_id,
        payment_mode=RAZORPAY_MODE,
        commit=False,
    )
    if not paid_booking:
        _upsert_review(
            db,
            booking=booking,
            entity=entity,
            reason="ATOMIC_PAYMENT_UPDATE_CONFLICT",
        )
        db.commit()
        return "review_required"

    ensure_booking_fulfillment(
        db,
        paid_booking,
        capacity_conflict=capacity_conflict,
    )
    user = (
        db.query(User)
        .filter(User.whatsapp_id == paid_booking.whatsapp_id)
        .first()
    )
    if user:
        user.flow_state = "PAYMENT_CONFIRMED"
        user.last_payment_link = None

    _upsert_review(
        db,
        booking=paid_booking,
        entity=entity,
        reason="PROVIDER_CAPTURE_RECOVERED",
        status="AUTO_RESOLVED",
    )
    _enqueue_payment_followups(db, paid_booking, payment_id)
    db.add(
        AdminAuditEvent(
            operator_id="system:payment-reconciliation",
            action="payment.capture_recovered",
            target_type="booking",
            target_id=str(paid_booking.id),
            before_json=json.dumps(
                {"payment_processed": False},
                separators=(",", ":"),
            ),
            after_json=json.dumps(
                {
                    "capacity_conflict": bool(capacity_conflict),
                    "payment_processed": True,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    )
    db.commit()
    return "recovered"


def _fetch_payment_link(client, payment_link_id: str) -> dict[str, Any]:
    if not _PAYMENT_LINK_ID_PATTERN.fullmatch(payment_link_id):
        raise ValueError("invalid_payment_link_id")

    response = client.get(f"/v1/payment_links/{payment_link_id}")
    response.raise_for_status()
    entity = response.json()
    if not isinstance(entity, dict):
        raise ValueError("invalid_provider_response")
    return entity


def _fetch_payment(client, payment_id: str) -> dict[str, Any]:
    if not _PAYMENT_ID_PATTERN.fullmatch(payment_id):
        raise ValueError("invalid_payment_id")

    response = client.get(f"/v1/payments/{payment_id}")
    response.raise_for_status()
    entity = response.json()
    if not isinstance(entity, dict):
        raise ValueError("invalid_payment_response")
    return entity


def _build_razorpay_client() -> httpx.Client:
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise RuntimeError("Razorpay credentials are not configured")
    timeout = httpx.Timeout(
        RAZORPAY_API_TIMEOUT_SECONDS,
        connect=min(RAZORPAY_API_TIMEOUT_SECONDS, 5.0),
    )
    return httpx.Client(
        base_url=RAZORPAY_API_BASE_URL,
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
        headers={
            "Accept": "application/json",
            "User-Agent": "NyaySetu-Payment-Verification/1.0",
        },
        follow_redirects=False,
        timeout=timeout,
    )


def fetch_current_razorpay_capture(
    payment_link_id: str,
    payment_id: str,
    *,
    client=None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch independent current link and payment evidence from Razorpay."""

    owned_client = client is None
    active_client = client or _build_razorpay_client()
    try:
        return (
            _fetch_payment_link(active_client, payment_link_id),
            _fetch_payment(active_client, payment_id),
        )
    finally:
        if owned_client:
            active_client.close()


def validate_current_razorpay_capture(
    booking: Booking,
    payment_id: str,
    payment_link_entity: dict[str, Any],
    payment_entity: dict[str, Any],
) -> str | None:
    """Validate ownership, exact full capture, and current refund state."""

    validation_error = _validation_error(booking, payment_link_entity)
    if validation_error:
        return validation_error
    if _captured_payment_id(payment_link_entity) != payment_id:
        return "CAPTURE_PAYMENT_ID_MISMATCH"
    return _payment_detail_validation_error(
        booking,
        payment_id,
        payment_entity,
    )


def reconcile_recent_payment_links(
    db,
    *,
    client=None,
    limit: int = 100,
    now: datetime | None = None,
) -> dict[str, int]:
    """Check a bounded set of unresolved links and recover exact captures."""

    stats = _new_stats()
    now = now or utc_now()
    cutoff = now - timedelta(days=PAYMENT_RECONCILIATION_LOOKBACK_DAYS)
    bounded_limit = min(max(int(limit), 1), 200)
    candidates = (
        db.query(Booking.id, Booking.razorpay_payment_link_id)
        .filter(
            Booking.status.in_(
                (BookingStatus.PENDING, BookingStatus.EXPIRED)
            ),
            Booking.payment_processed.isnot(True),
            Booking.razorpay_payment_link_id.isnot(None),
            Booking.created_at >= cutoff,
        )
        # Check recent links first so a backlog of old unpaid links cannot
        # starve newly captured payments in this deliberately bounded scan.
        .order_by(Booking.created_at.desc(), Booking.id.desc())
        .limit(bounded_limit)
        .all()
    )
    # Release the candidate snapshot before any provider network call.
    db.rollback()

    owned_client = client is None
    if owned_client:
        client = _build_razorpay_client()

    try:
        for booking_id, payment_link_id in candidates:
            stats["checked"] += 1
            try:
                entity = _fetch_payment_link(client, str(payment_link_id))
                captured_payment_id = _captured_payment_id(entity)
                payment_entity = (
                    _fetch_payment(client, captured_payment_id)
                    if captured_payment_id
                    else None
                )
                booking = (
                    db.query(Booking)
                    .filter(Booking.id == booking_id)
                    .with_for_update()
                    .first()
                )
                if not booking:
                    db.rollback()
                    continue
                if booking.payment_processed:
                    # The provider lookup happened before this row lock. If a
                    # concurrent handler paid the booking in that window,
                    # compare the exact capture so a second payment cannot be
                    # silently mistaken for an idempotent replay.
                    validation_error = _validation_error(booking, entity)
                    if (
                        validation_error is None
                        and captured_payment_id
                    ):
                        validation_error = _payment_detail_validation_error(
                            booking,
                            captured_payment_id,
                            payment_entity,
                        )
                    if validation_error is None:
                        outcome = _recover_exact_capture(
                            db,
                            booking,
                            entity,
                        )
                        stats[outcome] += 1
                    elif _contains_payment_evidence(entity):
                        # A concurrent success can make the candidate snapshot
                        # stale, but captured/malformed financial evidence is
                        # never silently classified as an idempotent replay.
                        _upsert_review(
                            db,
                            booking=booking,
                            entity=entity,
                            reason=validation_error,
                        )
                        db.commit()
                        stats["review_required"] += 1
                    else:
                        db.rollback()
                        stats["already_processed"] += 1
                    continue

                validation_error = _validation_error(booking, entity)
                if validation_error is None and captured_payment_id:
                    validation_error = _payment_detail_validation_error(
                        booking,
                        captured_payment_id,
                        payment_entity,
                    )
                if validation_error == "PAYMENT_LINK_NOT_PAID":
                    provider_payments = entity.get("payments")
                    amount_paid = _safe_int(entity.get("amount_paid")) or 0
                    if amount_paid > 0 or (
                        isinstance(provider_payments, list)
                        and bool(provider_payments)
                    ):
                        _upsert_review(
                            db,
                            booking=booking,
                            entity=entity,
                            reason="PARTIAL_OR_UNEXPECTED_PAYMENT",
                        )
                        db.commit()
                        stats["review_required"] += 1
                    else:
                        db.rollback()
                        stats["not_paid"] += 1
                    continue
                if validation_error:
                    _upsert_review(
                        db,
                        booking=booking,
                        entity=entity,
                        reason=validation_error,
                    )
                    db.commit()
                    stats["review_required"] += 1
                    continue

                if booking.status not in (
                    BookingStatus.PENDING,
                    BookingStatus.EXPIRED,
                ):
                    _upsert_review(
                        db,
                        booking=booking,
                        entity=entity,
                        reason="BOOKING_STATE_CHANGED",
                    )
                    db.commit()
                    stats["review_required"] += 1
                    continue

                payment_id = captured_payment_id
                prior_review = (
                    _find_reconciliation(db, payment_id)
                    if payment_id
                    else None
                )
                if prior_review and _identity_conflicts(
                    prior_review,
                    booking,
                ):
                    _upsert_review(
                        db,
                        booking=booking,
                        entity=entity,
                        reason="PAYMENT_IDENTITY_COLLISION",
                    )
                    db.commit()
                    stats["review_required"] += 1
                    continue
                if payment_id and _has_manual_disposition(
                    db,
                    booking,
                    payment_id,
                ):
                    # REFUNDED/IGNORED/operator-resolved evidence is never
                    # superseded by a scheduled process.
                    db.rollback()
                    stats["review_required"] += 1
                    continue

                outcome = _recover_exact_capture(db, booking, entity)
                stats[outcome] += 1
            except (httpx.HTTPError, ValueError):
                db.rollback()
                stats["provider_errors"] += 1
                logger.warning(
                    "Payment-link reconciliation lookup failed | "
                    "booking_id=%s",
                    booking_id,
                )
            except Exception as exc:
                db.rollback()
                stats["provider_errors"] += 1
                logger.error(
                    "Payment-link reconciliation failed | "
                    "booking_id=%s | reason=%s",
                    booking_id,
                    type(exc).__name__,
                )
    finally:
        if owned_client:
            client.close()

    return stats
