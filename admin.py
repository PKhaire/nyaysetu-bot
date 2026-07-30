"""Token-protected, privacy-minimised operational metrics blueprint."""

from __future__ import annotations

import hmac
import json
import re
from datetime import date, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_

from config import ADMIN_TOKEN
from db import SessionLocal
from models import (
    AdminAuditEvent,
    Advocate,
    AnalyticsEvent,
    Booking,
    BookingBlackout,
    BookingCapacityOverride,
    BookingFulfillment,
    BookingStatus,
    Feedback,
    InboundMessageEvent,
    OutboxJob,
    PaymentReconciliation,
    SupportRequest,
    User,
    WebhookEvent,
    utc_now,
)
from services.booking_service import SLOT_MAP, reschedule_paid_booking
from services.fulfillment_service import ensure_booking_fulfillment
from services.payment_reconciliation_service import (
    lock_matching_payment_reconciliations,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
_OPERATOR_PATTERN = re.compile(r"^[A-Za-z0-9._@+-]{2,120}$")


def _provided_token() -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.headers.get("X-Admin-Token", "").strip()


def _authorized() -> bool:
    provided = _provided_token()
    return bool(
        ADMIN_TOKEN
        and provided
        and hmac.compare_digest(provided, ADMIN_TOKEN)
    )


def _operator_id() -> str:
    value = request.headers.get("X-Operator-ID", "").strip()
    return value if _OPERATOR_PATTERN.fullmatch(value) else ""


def _json_body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _audit(
    db,
    *,
    action: str,
    target_type: str,
    target_id: str | int,
    before: dict,
    after: dict,
) -> None:
    db.add(
        AdminAuditEvent(
            operator_id=_operator_id(),
            action=action[:100],
            target_type=target_type[:80],
            target_id=str(target_id)[:120],
            before_json=json.dumps(before, sort_keys=True, default=str),
            after_json=json.dumps(after, sort_keys=True, default=str),
            request_id=request.headers.get("X-Request-ID", "")[:128] or None,
        )
    )


@admin_bp.before_request
def protect_admin_routes():
    if not ADMIN_TOKEN:
        return jsonify({"error": "not_found"}), 404
    if not _authorized():
        return (
            jsonify({"error": "unauthorized"}),
            401,
            {"WWW-Authenticate": "Bearer"},
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not _operator_id():
        return jsonify({"error": "valid_x_operator_id_required"}), 400
    return None


@admin_bp.after_request
def prevent_sensitive_caching(response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@admin_bp.get("/metrics")
def metrics():
    """Return aggregate operating metrics without contact or legal-message data."""

    db = SessionLocal()
    try:
        since = utc_now() - timedelta(days=30)
        booking_status_counts = {
            (status.value if isinstance(status, BookingStatus) else str(status)): count
            for status, count in (
                db.query(Booking.status, func.count(Booking.id))
                .group_by(Booking.status)
                .all()
            )
        }
        category_counts = {
            (category or "unknown"): count
            for category, count in (
                db.query(Booking.category, func.count(Booking.id))
                .filter(Booking.created_at >= since)
                .group_by(Booking.category)
                .all()
            )
        }
        avg_rating = db.query(func.avg(Feedback.rating)).scalar()
        paid_total = (
            db.query(func.coalesce(func.sum(Booking.amount), 0))
            .filter(
                Booking.status.in_(
                    (BookingStatus.PAID, BookingStatus.COMPLETED)
                )
            )
            .scalar()
        )
        outbox_counts = {
            str(status): int(count)
            for status, count in (
                db.query(OutboxJob.status, func.count(OutboxJob.id))
                .group_by(OutboxJob.status)
                .all()
            )
        }
        webhook_counts = {
            str(status): int(count)
            for status, count in (
                db.query(WebhookEvent.status, func.count(WebhookEvent.id))
                .group_by(WebhookEvent.status)
                .all()
            )
        }
        fulfillment_counts = {
            str(status): int(count)
            for status, count in (
                db.query(
                    BookingFulfillment.status,
                    func.count(BookingFulfillment.id),
                )
                .group_by(BookingFulfillment.status)
                .all()
            )
        }
        oldest_outbox = (
            db.query(func.min(OutboxJob.created_at))
            .filter(OutboxJob.status.in_(("PENDING", "RUNNING")))
            .scalar()
        )

        payload = {
            "generated_at": utc_now().isoformat(timespec="seconds") + "Z",
            "users": {
                "total": db.query(func.count(User.id)).scalar() or 0,
                "last_30_days": (
                    db.query(func.count(User.id))
                    .filter(User.created_at >= since)
                    .scalar()
                    or 0
                ),
            },
            "bookings": {
                "total": db.query(func.count(Booking.id)).scalar() or 0,
                "by_status": booking_status_counts,
                "last_30_days_by_category": category_counts,
                "recorded_paid_value_inr": int(paid_total or 0),
            },
            "support": {
                "open": (
                    db.query(func.count(SupportRequest.id))
                    .filter(SupportRequest.status == "OPEN")
                    .scalar()
                    or 0
                ),
            },
            "feedback": {
                "responses": db.query(func.count(Feedback.id)).scalar() or 0,
                "average_rating": (
                    round(float(avg_rating), 2) if avg_rating is not None else None
                ),
            },
            "analytics_events_last_30_days": (
                db.query(func.count(AnalyticsEvent.id))
                .filter(AnalyticsEvent.created_at >= since)
                .scalar()
                or 0
            ),
            "operations": {
                "outbox_by_status": outbox_counts,
                "oldest_active_outbox_at": (
                    oldest_outbox.isoformat() + "Z"
                    if oldest_outbox
                    else None
                ),
                "webhooks_by_status": webhook_counts,
                "fulfillments_by_status": fulfillment_counts,
                "open_payment_reconciliations": (
                    db.query(func.count(PaymentReconciliation.id))
                    .filter(PaymentReconciliation.status == "OPEN")
                    .scalar()
                    or 0
                ),
                "overdue_support": (
                    db.query(func.count(SupportRequest.id))
                    .filter(
                        SupportRequest.status.in_(
                            ("OPEN", "IN_PROGRESS", "WAITING_USER")
                        ),
                        SupportRequest.sla_due_at.is_not(None),
                        SupportRequest.sla_due_at < utc_now(),
                    )
                    .scalar()
                    or 0
                ),
                "active_inbound_claims": (
                    db.query(func.count(InboundMessageEvent.id))
                    .filter(InboundMessageEvent.status == "PROCESSING")
                    .scalar()
                    or 0
                ),
            },
        }
        return jsonify(payload)
    finally:
        db.close()


@admin_bp.get("/support")
def support_queue():
    """Return the newest support tickets for authorised operations staff."""

    limit = min(max(request.args.get("limit", default=25, type=int), 1), 100)
    status_filter = request.args.get("status", "").strip().upper()
    db = SessionLocal()
    try:
        query = (
            db.query(SupportRequest, User)
            .outerjoin(User, User.id == SupportRequest.user_id)
            .order_by(SupportRequest.created_at.desc())
        )
        if status_filter:
            query = query.filter(SupportRequest.status == status_filter)
        rows = query.limit(limit).all()
        return jsonify(
            {
                "items": [
                    {
                        "ticket_id": f"NSH-{item.id:06d}",
                        "case_id": item.case_id,
                        "type": item.request_type,
                        "subject": item.subject,
                        "message": item.message,
                        "status": item.status,
                        "priority": item.priority,
                        "assigned_to": item.assigned_to,
                        "resolution_note": item.resolution_note,
                        "whatsapp_id": user.whatsapp_id if user else None,
                        "sla_due_at": (
                            item.sla_due_at.isoformat() + "Z"
                            if item.sla_due_at
                            else None
                        ),
                        "created_at": item.created_at.isoformat() + "Z",
                        "updated_at": item.updated_at.isoformat() + "Z",
                        "resolved_at": (
                            item.resolved_at.isoformat() + "Z"
                            if item.resolved_at
                            else None
                        ),
                    }
                    for item, user in rows
                ]
            }
        )
    finally:
        db.close()


@admin_bp.patch("/support/<int:ticket_id>")
def update_support_ticket(ticket_id: int):
    body = _json_body()
    allowed_statuses = {
        "OPEN",
        "IN_PROGRESS",
        "WAITING_USER",
        "RESOLVED",
        "CLOSED",
    }
    allowed_priorities = {"LOW", "NORMAL", "HIGH", "URGENT"}

    db = SessionLocal()
    try:
        ticket = db.get(SupportRequest, ticket_id)
        if not ticket:
            return jsonify({"error": "support_ticket_not_found"}), 404

        before = {
            "status": ticket.status,
            "priority": ticket.priority,
            "assigned_to": ticket.assigned_to,
            "resolution_note": ticket.resolution_note,
        }
        if "status" in body:
            status = str(body["status"]).strip().upper()
            if status not in allowed_statuses:
                return jsonify({"error": "invalid_support_status"}), 400
            ticket.status = status
            ticket.resolved_at = (
                utc_now() if status in {"RESOLVED", "CLOSED"} else None
            )
        if "priority" in body:
            priority = str(body["priority"]).strip().upper()
            if priority not in allowed_priorities:
                return jsonify({"error": "invalid_support_priority"}), 400
            ticket.priority = priority
        if "assigned_to" in body:
            ticket.assigned_to = (
                str(body["assigned_to"]).strip()[:120] or None
            )
        if "resolution_note" in body:
            ticket.resolution_note = (
                str(body["resolution_note"]).strip()[:4_000] or None
            )
        if (
            ticket.status in {"RESOLVED", "CLOSED"}
            and not ticket.resolution_note
        ):
            return jsonify({"error": "resolution_note_required"}), 400

        after = {
            "status": ticket.status,
            "priority": ticket.priority,
            "assigned_to": ticket.assigned_to,
            "resolution_note": ticket.resolution_note,
        }
        _audit(
            db,
            action="support.update",
            target_type="support_request",
            target_id=ticket.id,
            before=before,
            after=after,
        )
        db.commit()
        return jsonify({"ok": True, "ticket_id": f"NSH-{ticket.id:06d}", **after})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _serialize_fulfillment(fulfillment, booking, user) -> dict:
    return {
        "booking_id": booking.id,
        "case_id": user.case_id if user else None,
        "whatsapp_id": booking.whatsapp_id,
        "name": booking.name,
        "category": booking.category,
        "subcategory": booking.subcategory,
        "date": booking.date.isoformat(),
        "slot_code": booking.slot_code,
        "slot": booking.slot_readable,
        "amount": booking.amount,
        "payment_status": (
            booking.status.value
            if isinstance(booking.status, BookingStatus)
            else str(booking.status)
        ),
        "fulfillment_status": (
            fulfillment.status if fulfillment else "MISSING"
        ),
        "advocate_id": fulfillment.advocate_id if fulfillment else None,
        "assigned_to": fulfillment.assigned_to if fulfillment else None,
        "operator_notes": fulfillment.operator_notes if fulfillment else None,
        "sla_due_at": (
            fulfillment.sla_due_at.isoformat() + "Z"
            if fulfillment and fulfillment.sla_due_at
            else None
        ),
        "updated_at": (
            fulfillment.updated_at.isoformat() + "Z"
            if fulfillment
            else None
        ),
    }


@admin_bp.get("/fulfillments")
def fulfillment_queue():
    limit = min(max(request.args.get("limit", default=50, type=int), 1), 200)
    status_filter = request.args.get("status", "").strip().upper()
    db = SessionLocal()
    try:
        query = (
            db.query(BookingFulfillment, Booking, User)
            .join(Booking, Booking.id == BookingFulfillment.booking_id)
            .outerjoin(User, User.whatsapp_id == Booking.whatsapp_id)
            .order_by(
                BookingFulfillment.sla_due_at.asc(),
                Booking.id.asc(),
            )
        )
        if status_filter:
            query = query.filter(
                BookingFulfillment.status == status_filter
            )
        rows = query.limit(limit).all()
        return jsonify(
            {
                "items": [
                    _serialize_fulfillment(fulfillment, booking, user)
                    for fulfillment, booking, user in rows
                ]
            }
        )
    finally:
        db.close()


_FULFILLMENT_TRANSITIONS = {
    "UNASSIGNED": {
        "ASSIGNED",
        "RESCHEDULE_REQUIRED",
        "REFUND_REVIEW",
    },
    "ASSIGNED": {
        "CONFIRMED",
        "COMPLETED",
        "NO_SHOW",
        "RESCHEDULE_REQUIRED",
        "REFUND_REVIEW",
    },
    "CONFIRMED": {
        "COMPLETED",
        "NO_SHOW",
        "RESCHEDULE_REQUIRED",
        "REFUND_REVIEW",
    },
    "RESCHEDULE_REQUIRED": {"ASSIGNED", "REFUND_REVIEW", "REFUNDED"},
    "REFUND_REVIEW": {"ASSIGNED", "REFUNDED"},
    "NO_SHOW": {"COMPLETED", "REFUND_REVIEW"},
    "COMPLETED": set(),
    "REFUNDED": set(),
    "CANCELLED": set(),
}


@admin_bp.patch("/fulfillments/<int:booking_id>")
def update_fulfillment(booking_id: int):
    body = _json_body()
    requested_status = str(body.get("status") or "").strip().upper()
    if not requested_status:
        return jsonify({"error": "status_required"}), 400

    db = SessionLocal()
    try:
        # Lock booking first everywhere this workflow may mutate both rows.
        # Payment acceptance uses the same booking -> fulfillment order, which
        # prevents stale status writes and avoids a lock-order deadlock.
        booking = (
            db.query(Booking)
            .filter(Booking.id == booking_id)
            .with_for_update()
            .first()
        )
        if not booking:
            return jsonify({"error": "booking_not_found"}), 404
        locked_reconciliations = lock_matching_payment_reconciliations(
            db,
            payment_id=booking.razorpay_payment_id,
            payment_link_id=booking.razorpay_payment_link_id,
        )
        fulfillment = (
            db.query(BookingFulfillment)
            .filter(BookingFulfillment.booking_id == booking_id)
            .with_for_update()
            .first()
        )
        if not fulfillment:
            if booking.status not in (
                BookingStatus.PAID,
                BookingStatus.COMPLETED,
            ):
                return jsonify({"error": "booking_is_not_paid"}), 409
            fulfillment = BookingFulfillment(
                booking_id=booking_id,
                status="UNASSIGNED",
            )
            db.add(fulfillment)
            db.flush()

        current_status = fulfillment.status or "UNASSIGNED"
        allowed = _FULFILLMENT_TRANSITIONS.get(current_status, set())
        if requested_status != current_status and requested_status not in allowed:
            return (
                jsonify(
                    {
                        "error": "invalid_fulfillment_transition",
                        "from": current_status,
                        "to": requested_status,
                    }
                ),
                409,
            )

        notes = str(body.get("operator_notes") or "").strip()
        if requested_status in {
            "COMPLETED",
            "NO_SHOW",
            "RESCHEDULE_REQUIRED",
            "REFUND_REVIEW",
            "REFUNDED",
            "CANCELLED",
        } and len(notes) < 5:
            return jsonify({"error": "operator_notes_required"}), 400

        before = {
            "status": current_status,
            "payment_status": (
                booking.status.value
                if isinstance(booking.status, BookingStatus)
                else str(booking.status)
            ),
            "advocate_id": fulfillment.advocate_id,
            "assigned_to": fulfillment.assigned_to,
            "date": booking.date.isoformat(),
            "slot_code": booking.slot_code,
        }

        reschedule_date = body.get("reschedule_date")
        reschedule_slot = body.get("reschedule_slot_code")
        if bool(reschedule_date) != bool(reschedule_slot):
            return (
                jsonify(
                    {
                        "error": (
                            "reschedule_date_and_slot_must_be_provided_together"
                        )
                    }
                ),
                400,
            )
        if reschedule_date and reschedule_slot:
            error = reschedule_paid_booking(
                db,
                booking,
                str(reschedule_date),
                str(reschedule_slot),
            )
            if error:
                db.rollback()
                return jsonify({"error": "reschedule_unavailable", "detail": error}), 409
            ensure_booking_fulfillment(db, booking)

        advocate_id = body.get("advocate_id")
        if advocate_id is not None:
            try:
                advocate_id = int(advocate_id)
            except (TypeError, ValueError):
                return jsonify({"error": "invalid_advocate_id"}), 400
            advocate = db.get(Advocate, advocate_id)
            if not advocate or not advocate.active:
                return jsonify({"error": "active_advocate_not_found"}), 404
            fulfillment.advocate_id = advocate_id
            fulfillment.assigned_to = advocate.name
        if "assigned_to" in body:
            fulfillment.assigned_to = (
                str(body["assigned_to"]).strip()[:160] or None
            )
        if requested_status in {"ASSIGNED", "CONFIRMED"} and not (
            fulfillment.advocate_id or fulfillment.assigned_to
        ):
            return jsonify({"error": "assignment_required"}), 400

        user = (
            db.query(User)
            .filter(User.whatsapp_id == booking.whatsapp_id)
            .with_for_update()
            .first()
        )
        now = utc_now()
        fulfillment.status = requested_status
        if notes:
            fulfillment.operator_notes = notes[:4_000]
        if requested_status == "ASSIGNED":
            fulfillment.assigned_at = now
        elif requested_status == "CONFIRMED":
            fulfillment.confirmed_at = now
        elif requested_status == "COMPLETED":
            fulfillment.completed_at = now
            booking.status = BookingStatus.COMPLETED
        elif requested_status == "REFUNDED":
            # Keep immutable amount/provider/payment identifiers, but revoke
            # this booking's service entitlement using the existing non-paid
            # terminal state. Fulfillment remains the explicit refund truth.
            booking.status = BookingStatus.CANCELLED
            refund_reconciliations = list(locked_reconciliations)
            exact_reconciliation = next(
                (
                    item
                    for item in refund_reconciliations
                    if item.payment_id == booking.razorpay_payment_id
                ),
                None,
            )
            if booking.razorpay_payment_id and not exact_reconciliation:
                exact_reconciliation = PaymentReconciliation(
                    provider="razorpay",
                    payment_id=booking.razorpay_payment_id,
                    payment_link_id=booking.razorpay_payment_link_id,
                    booking_id=booking.id,
                    reason="FULFILLMENT_REFUNDED",
                    status="REFUNDED",
                    expected_amount=int(booking.amount) * 100,
                    received_amount=int(booking.amount) * 100,
                    currency="INR",
                )
                db.add(exact_reconciliation)
                refund_reconciliations.append(exact_reconciliation)
            for reconciliation in refund_reconciliations:
                reconciliation.status = "REFUNDED"
                reconciliation.resolved_at = now
                reconciliation.resolved_by = _operator_id()
                reconciliation.resolution_note = notes[:4_000]
                if reconciliation.booking_id is None:
                    reconciliation.booking_id = booking.id
                if not reconciliation.payment_link_id:
                    reconciliation.payment_link_id = (
                        booking.razorpay_payment_link_id
                    )
            other_paid_booking = (
                db.query(Booking.id)
                .filter(
                    Booking.whatsapp_id == booking.whatsapp_id,
                    Booking.id != booking.id,
                    Booking.status == BookingStatus.PAID,
                )
                .first()
            )
            if user and not other_paid_booking:
                user.flow_state = "NORMAL"
                user.ai_enabled = False
                user.temp_date = None
                user.temp_slot = None
                user.last_payment_link = None

        after = {
            "status": fulfillment.status,
            "payment_status": (
                booking.status.value
                if isinstance(booking.status, BookingStatus)
                else str(booking.status)
            ),
            "advocate_id": fulfillment.advocate_id,
            "assigned_to": fulfillment.assigned_to,
            "date": booking.date.isoformat(),
            "slot_code": booking.slot_code,
            "operator_notes": fulfillment.operator_notes,
        }
        _audit(
            db,
            action="fulfillment.update",
            target_type="booking",
            target_id=booking.id,
            before=before,
            after=after,
        )
        db.commit()
        return jsonify(
            {
                "ok": True,
                "item": _serialize_fulfillment(
                    fulfillment,
                    booking,
                    user,
                ),
            }
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@admin_bp.get("/payment-reconciliations")
def payment_reconciliation_queue():
    limit = min(max(request.args.get("limit", default=50, type=int), 1), 200)
    status_filter = request.args.get("status", "OPEN").strip().upper()
    db = SessionLocal()
    try:
        query = db.query(PaymentReconciliation).order_by(
            PaymentReconciliation.created_at.asc()
        )
        if status_filter:
            query = query.filter(
                PaymentReconciliation.status == status_filter
            )
        rows = query.limit(limit).all()
        return jsonify(
            {
                "items": [
                    {
                        "id": item.id,
                        "payment_id": item.payment_id,
                        "payment_link_id": item.payment_link_id,
                        "booking_id": item.booking_id,
                        "reason": item.reason,
                        "status": item.status,
                        "expected_amount": item.expected_amount,
                        "received_amount": item.received_amount,
                        "currency": item.currency,
                        "created_at": item.created_at.isoformat() + "Z",
                    }
                    for item in rows
                ]
            }
        )
    finally:
        db.close()


@admin_bp.patch("/payment-reconciliations/<int:item_id>")
def resolve_payment_reconciliation(item_id: int):
    body = _json_body()
    status = str(body.get("status") or "").strip().upper()
    note = str(body.get("resolution_note") or "").strip()
    if status not in {"RESOLVED", "REFUND_INITIATED", "REFUNDED", "IGNORED"}:
        return jsonify({"error": "invalid_resolution_status"}), 400
    if len(note) < 5:
        return jsonify({"error": "resolution_note_required"}), 400

    db = SessionLocal()
    try:
        item = None
        associated_booking = None
        for _attempt in range(3):
            snapshot = (
                db.query(
                    PaymentReconciliation.booking_id,
                    PaymentReconciliation.payment_id,
                    PaymentReconciliation.payment_link_id,
                )
                .filter(PaymentReconciliation.id == item_id)
                .first()
            )
            if not snapshot:
                return (
                    jsonify(
                        {"error": "payment_reconciliation_not_found"}
                    ),
                    404,
                )

            booking_filters = []
            if snapshot.booking_id is not None:
                booking_filters.append(Booking.id == snapshot.booking_id)
            if snapshot.payment_id:
                booking_filters.append(
                    Booking.razorpay_payment_id == snapshot.payment_id
                )
            if snapshot.payment_link_id:
                booking_filters.append(
                    Booking.razorpay_payment_link_id
                    == snapshot.payment_link_id
                )
            if booking_filters:
                locked_bookings = (
                    db.query(Booking)
                    .filter(or_(*booking_filters))
                    .order_by(Booking.id.asc())
                    .with_for_update()
                    .all()
                )
            else:
                locked_bookings = []

            locked_items = lock_matching_payment_reconciliations(
                db,
                payment_id=snapshot.payment_id,
                payment_link_id=snapshot.payment_link_id,
            )
            item = next(
                (
                    candidate
                    for candidate in locked_items
                    if candidate.id == item_id
                ),
                None,
            )
            if not item:
                db.rollback()
                continue
            current_identity = (
                item.booking_id,
                item.payment_id,
                item.payment_link_id,
            )
            if current_identity == tuple(snapshot):
                associated_booking = next(
                    (
                        booking
                        for booking in locked_bookings
                        if item.booking_id is not None
                        and booking.id == item.booking_id
                    ),
                    None,
                )
                if associated_booking is None:
                    associated_booking = next(
                        (
                            booking
                            for booking in locked_bookings
                            if (
                                item.payment_id
                                and booking.razorpay_payment_id
                                == item.payment_id
                            )
                            or (
                                item.payment_link_id
                                and booking.razorpay_payment_link_id
                                == item.payment_link_id
                            )
                        ),
                        None,
                    )
                break
            # Its association changed before the row lock. Release every lock
            # and retry so the current booking is always locked first.
            db.rollback()
            item = None

        if item is None:
            return jsonify({"error": "reconciliation_changed_retry"}), 409

        fulfillment = None
        if associated_booking and status in {
            "REFUND_INITIATED",
            "REFUNDED",
        }:
            fulfillment = (
                db.query(BookingFulfillment)
                .filter(
                    BookingFulfillment.booking_id
                    == associated_booking.id
                )
                .with_for_update()
                .first()
            )

        accepted_payment = bool(
            associated_booking
            and (
                associated_booking.payment_processed
                or associated_booking.status
                in (BookingStatus.PAID, BookingStatus.COMPLETED)
            )
        )
        if (
            status == "REFUND_INITIATED"
            and associated_booking
            and accepted_payment
        ):
            if item.status == "REFUNDED":
                db.rollback()
                return jsonify({"error": "refund_already_completed"}), 409
            if not fulfillment or fulfillment.status != "REFUND_REVIEW":
                db.rollback()
                return (
                    jsonify(
                        {
                            "error": (
                                "fulfillment_refund_review_required"
                            ),
                            "required_status": "REFUND_REVIEW",
                        }
                    ),
                    409,
                )

        if (
            status == "REFUNDED"
            and associated_booking
            and accepted_payment
            and (
                not fulfillment
                or fulfillment.status != "REFUNDED"
                or associated_booking.status != BookingStatus.CANCELLED
            )
        ):
            db.rollback()
            return (
                jsonify(
                    {
                        "error": "fulfillment_refund_required",
                        "required_fulfillment_status": "REFUNDED",
                        "required_booking_status": "CANCELLED",
                    }
                ),
                409,
            )

        before = {"status": item.status}
        item.status = status
        item.resolution_note = note[:4_000]
        item.resolved_by = _operator_id()
        item.resolved_at = utc_now()
        _audit(
            db,
            action="payment_reconciliation.resolve",
            target_type="payment_reconciliation",
            target_id=item.id,
            before=before,
            after={"status": status, "resolution_note": item.resolution_note},
        )
        db.commit()
        return jsonify({"ok": True, "id": item.id, "status": item.status})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@admin_bp.get("/outbox")
def outbox_queue():
    limit = min(max(request.args.get("limit", default=50, type=int), 1), 200)
    status_filter = request.args.get("status", "").strip().upper()
    db = SessionLocal()
    try:
        query = db.query(OutboxJob).order_by(OutboxJob.created_at.asc())
        if status_filter:
            query = query.filter(OutboxJob.status == status_filter)
        rows = query.limit(limit).all()
        return jsonify(
            {
                "items": [
                    {
                        "id": item.id,
                        "kind": item.kind,
                        "status": item.status,
                        "attempts": item.attempts,
                        "available_at": item.available_at.isoformat() + "Z",
                        "last_error": item.last_error,
                        "created_at": item.created_at.isoformat() + "Z",
                    }
                    for item in rows
                ]
            }
        )
    finally:
        db.close()


@admin_bp.post("/outbox/<int:job_id>/retry")
def retry_outbox_job(job_id: int):
    db = SessionLocal()
    try:
        job = db.get(OutboxJob, job_id)
        if not job:
            return jsonify({"error": "outbox_job_not_found"}), 404
        if job.status not in {"DEAD", "FAILED"}:
            return jsonify({"error": "outbox_job_not_retryable"}), 409
        before = {
            "status": job.status,
            "attempts": job.attempts,
            "last_error": job.last_error,
        }
        job.status = "PENDING"
        job.attempts = 0
        job.last_error = None
        job.available_at = utc_now()
        _audit(
            db,
            action="outbox.retry",
            target_type="outbox_job",
            target_id=job.id,
            before=before,
            after={"status": job.status, "attempts": job.attempts},
        )
        db.commit()
        return jsonify({"ok": True, "job_id": job.id})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


@admin_bp.get("/availability")
def availability():
    from_date = _parse_date(request.args.get("from")) or utc_now().date()
    to_date = _parse_date(request.args.get("to")) or (
        from_date + timedelta(days=90)
    )
    if to_date < from_date or (to_date - from_date).days > 366:
        return jsonify({"error": "invalid_availability_range"}), 400

    db = SessionLocal()
    try:
        blackouts = (
            db.query(BookingBlackout)
            .filter(
                BookingBlackout.date.between(from_date, to_date),
                BookingBlackout.active.is_(True),
            )
            .order_by(BookingBlackout.date.asc(), BookingBlackout.id.asc())
            .all()
        )
        overrides = (
            db.query(BookingCapacityOverride)
            .filter(
                BookingCapacityOverride.date.between(from_date, to_date),
                BookingCapacityOverride.active.is_(True),
            )
            .order_by(
                BookingCapacityOverride.date.asc(),
                BookingCapacityOverride.id.asc(),
            )
            .all()
        )
        return jsonify(
            {
                "blackouts": [
                    {
                        "id": item.id,
                        "date": item.date.isoformat(),
                        "slot_code": item.slot_code,
                        "reason": item.reason,
                    }
                    for item in blackouts
                ],
                "capacity_overrides": [
                    {
                        "id": item.id,
                        "date": item.date.isoformat(),
                        "slot_code": item.slot_code,
                        "capacity": item.capacity,
                    }
                    for item in overrides
                ],
            }
        )
    finally:
        db.close()


@admin_bp.post("/availability/blackouts")
def create_blackout():
    body = _json_body()
    blackout_date = _parse_date(body.get("date"))
    slot_code = str(body.get("slot_code") or "").strip() or None
    reason = str(body.get("reason") or "").strip()
    if not blackout_date or (slot_code and slot_code not in SLOT_MAP):
        return jsonify({"error": "invalid_blackout_date_or_slot"}), 400
    if len(reason) < 3:
        return jsonify({"error": "blackout_reason_required"}), 400

    db = SessionLocal()
    try:
        item = (
            db.query(BookingBlackout)
            .filter(
                BookingBlackout.date == blackout_date,
                BookingBlackout.slot_code == slot_code,
            )
            .order_by(BookingBlackout.id.desc())
            .first()
        )
        before = {}
        if not item:
            item = BookingBlackout(
                date=blackout_date,
                slot_code=slot_code,
                reason=reason[:255],
                created_by=_operator_id(),
            )
            db.add(item)
            db.flush()
        else:
            before = {
                "active": item.active,
                "reason": item.reason,
            }
            item.active = True
            item.reason = reason[:255]
            item.created_by = _operator_id()
        _audit(
            db,
            action="availability.blackout.create",
            target_type="booking_blackout",
            target_id=item.id,
            before=before,
            after={
                "date": item.date,
                "slot_code": item.slot_code,
                "reason": item.reason,
                "active": item.active,
            },
        )
        db.commit()
        return jsonify({"ok": True, "id": item.id}), 201
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@admin_bp.delete("/availability/blackouts/<int:item_id>")
def deactivate_blackout(item_id: int):
    db = SessionLocal()
    try:
        item = db.get(BookingBlackout, item_id)
        if not item:
            return jsonify({"error": "blackout_not_found"}), 404
        before = {"active": item.active}
        item.active = False
        _audit(
            db,
            action="availability.blackout.deactivate",
            target_type="booking_blackout",
            target_id=item.id,
            before=before,
            after={"active": False},
        )
        db.commit()
        return jsonify({"ok": True})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@admin_bp.post("/availability/capacity")
def create_capacity_override():
    body = _json_body()
    override_date = _parse_date(body.get("date"))
    slot_code = str(body.get("slot_code") or "").strip() or None
    try:
        capacity = int(body.get("capacity"))
    except (TypeError, ValueError):
        capacity = -1
    if not override_date or (slot_code and slot_code not in SLOT_MAP):
        return jsonify({"error": "invalid_capacity_date_or_slot"}), 400
    if capacity < 0 or capacity > 100:
        return jsonify({"error": "capacity_must_be_between_0_and_100"}), 400

    db = SessionLocal()
    try:
        item = (
            db.query(BookingCapacityOverride)
            .filter(
                BookingCapacityOverride.date == override_date,
                BookingCapacityOverride.slot_code == slot_code,
            )
            .order_by(BookingCapacityOverride.id.desc())
            .first()
        )
        before = {}
        if not item:
            item = BookingCapacityOverride(
                date=override_date,
                slot_code=slot_code,
                capacity=capacity,
                created_by=_operator_id(),
            )
            db.add(item)
            db.flush()
        else:
            before = {
                "active": item.active,
                "capacity": item.capacity,
            }
            item.active = True
            item.capacity = capacity
            item.created_by = _operator_id()
        _audit(
            db,
            action="availability.capacity.upsert",
            target_type="booking_capacity_override",
            target_id=item.id,
            before=before,
            after={
                "date": item.date,
                "slot_code": item.slot_code,
                "capacity": item.capacity,
                "active": item.active,
            },
        )
        db.commit()
        return jsonify({"ok": True, "id": item.id}), 201
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@admin_bp.delete("/availability/capacity/<int:item_id>")
def deactivate_capacity_override(item_id: int):
    db = SessionLocal()
    try:
        item = db.get(BookingCapacityOverride, item_id)
        if not item:
            return jsonify({"error": "capacity_override_not_found"}), 404
        before = {"active": item.active}
        item.active = False
        _audit(
            db,
            action="availability.capacity.deactivate",
            target_type="booking_capacity_override",
            target_id=item.id,
            before=before,
            after={"active": False},
        )
        db.commit()
        return jsonify({"ok": True})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@admin_bp.get("/audit")
def audit_log():
    limit = min(max(request.args.get("limit", default=100, type=int), 1), 500)
    db = SessionLocal()
    try:
        rows = (
            db.query(AdminAuditEvent)
            .order_by(AdminAuditEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return jsonify(
            {
                "items": [
                    {
                        "id": item.id,
                        "operator_id": item.operator_id,
                        "action": item.action,
                        "target_type": item.target_type,
                        "target_id": item.target_id,
                        "before": json.loads(item.before_json or "{}"),
                        "after": json.loads(item.after_json or "{}"),
                        "request_id": item.request_id,
                        "created_at": item.created_at.isoformat() + "Z",
                    }
                    for item in rows
                ]
            }
        )
    finally:
        db.close()
