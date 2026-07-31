from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from jobs import reconcile_payments as reconciliation_job
from models import (
    AdminAuditEvent,
    Booking,
    BookingFulfillment,
    BookingStatus,
    OutboxJob,
    PaymentReconciliation,
    User,
)
from services import fulfillment_service
from services import payment_reconciliation_service as reconciliation


_PAYMENT_FOLLOWUP_KINDS = (
    "payment_success_message",
    "booking_notification",
    "payment_receipt",
)


def _payment_followup_count(db) -> int:
    return (
        db.query(OutboxJob)
        .filter(OutboxJob.kind.in_(_PAYMENT_FOLLOWUP_KINDS))
        .count()
    )


class FakeResponse:
    def __init__(self, payload, *, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://api.razorpay.test/link")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "provider error",
                request=self.request,
                response=httpx.Response(
                    self.status_code,
                    request=self.request,
                ),
            )

    def json(self):
        return self.payload


class FakeClient:
    def __init__(
        self,
        payload=None,
        *,
        status_code=200,
        payment_payload=None,
    ):
        self.payload = payload
        self.payment_payload = payment_payload
        self.status_code = status_code
        self.paths = []

    def get(self, path):
        self.paths.append(path)
        payload = self.payload
        if path.startswith("/v1/payments/"):
            payload = self.payment_payload
            if payload is None:
                payload = _payment_entity_from_link(self.payload)
        return FakeResponse(payload, status_code=self.status_code)


class MappingClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.paths = []

    def get(self, path):
        self.paths.append(path)
        if path in self.payloads:
            return FakeResponse(self.payloads[path])
        if path.startswith("/v1/payments/"):
            payment_id = path.rsplit("/", 1)[-1]
            for link_entity in self.payloads.values():
                payment_entity = _payment_entity_from_link(link_entity)
                if payment_entity["id"] == payment_id:
                    return FakeResponse(payment_entity)
        raise KeyError(path)


@pytest.fixture
def reconciliation_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(reconciliation, "BOOKING_NOTIFICATION_EMAILS", [])
    monkeypatch.setattr(reconciliation, "PAYMENT_RECONCILIATION_EMAILS", [])
    monkeypatch.setattr(reconciliation, "AUTO_SEND_RECEIPTS", False)
    try:
        yield testing_session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _pending_booking(
    session_factory,
    *,
    serial: str = "123",
    created_at: datetime = datetime(2026, 7, 29, 10, 0),
) -> tuple[int, str, str]:
    db = session_factory()
    try:
        payment_token = f"reconciliation-token-{serial}"
        user = User(
            whatsapp_id=f"91990000{serial}",
            case_id=f"NS-RECONCILE-{serial}",
            name="Test User",
            flow_state="WAITING_PAYMENT",
            last_payment_link="https://rzp.test/link",
        )
        db.add(user)
        db.flush()
        booking = Booking(
            whatsapp_id=user.whatsapp_id,
            name="Test User",
            phone=user.whatsapp_id,
            state_name="Maharashtra",
            district_name="Pune",
            category="Family",
            subcategory="Other Family Issue",
            date=date(2026, 8, 3),
            slot_code="10_11",
            slot_readable="10:00 AM - 11:00 AM",
            amount=499,
            status=BookingStatus.PENDING,
            payment_token=payment_token,
            razorpay_payment_link_id=f"plink_Reconcile{serial}",
            payment_processed=False,
            created_at=created_at,
        )
        db.add(booking)
        db.commit()
        return (
            booking.id,
            booking.razorpay_payment_link_id,
            payment_token,
        )
    finally:
        db.close()


def _provider_entity(
    *,
    status="paid",
    amount=49_900,
    booking_id=1,
    payment_link_id="plink_Reconcile123",
    payment_token="reconciliation-token-123",
    payment_id="pay_Reconcile123",
):
    return {
        "id": payment_link_id,
        "status": status,
        "amount": 49_900,
        "amount_paid": amount if status == "paid" else 0,
        "currency": "INR",
        "accept_partial": False,
        "reference_id": payment_token,
        "notes": {
            "booking_id": str(booking_id),
            "booking_token": payment_token,
        },
        "payments": (
            [
                {
                    "payment_id": payment_id,
                    "status": "captured",
                    "amount": amount,
                }
            ]
            if status == "paid"
            else None
        ),
    }


def _payment_entity_from_link(link_entity):
    payment = (
        link_entity["payments"][0]
        if isinstance(link_entity, dict)
        and isinstance(link_entity.get("payments"), list)
        and len(link_entity["payments"]) == 1
        and isinstance(link_entity["payments"][0], dict)
        else {}
    )
    raw_currency = (
        link_entity.get("currency")
        if isinstance(link_entity, dict)
        else None
    )
    currency = (
        raw_currency.strip().upper()
        if isinstance(raw_currency, str) and raw_currency.strip()
        else "INR"
    )
    status = str(payment.get("status") or "")
    return {
        "id": payment.get("payment_id"),
        "entity": "payment",
        "amount": payment.get("amount"),
        "currency": currency,
        "status": status,
        "captured": status.lower() == "captured",
        "amount_refunded": 0,
        "refund_status": None,
    }


def test_exact_provider_capture_is_recovered_once(reconciliation_db):
    booking_id, payment_link_id, _ = _pending_booking(reconciliation_db)
    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(_provider_entity()),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats == {
        "checked": 1,
        "recovered": 1,
        "already_processed": 0,
        "not_paid": 0,
        "review_required": 0,
        "provider_errors": 0,
    }

    db = reconciliation_db()
    try:
        replay_stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(_provider_entity()),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()
    assert replay_stats["checked"] == 0

    db = reconciliation_db()
    try:
        booking = db.get(Booking, booking_id)
        assert booking.status == BookingStatus.PAID
        assert booking.payment_processed is True
        assert booking.razorpay_payment_id == "pay_Reconcile123"
        assert booking.razorpay_payment_link_id == payment_link_id

        fulfillment = (
            db.query(BookingFulfillment)
            .filter(BookingFulfillment.booking_id == booking_id)
            .one()
        )
        assert fulfillment.status == "UNASSIGNED"

        item = db.query(PaymentReconciliation).one()
        assert item.status == "AUTO_RESOLVED"
        assert item.reason == "PROVIDER_CAPTURE_RECOVERED"

        jobs = (
            db.query(OutboxJob)
            .filter(OutboxJob.kind.in_(_PAYMENT_FOLLOWUP_KINDS))
            .all()
        )
        assert [job.kind for job in jobs] == ["payment_success_message"]
        assert db.query(BookingFulfillment).count() == 1
        assert db.query(PaymentReconciliation).count() == 1
        assert db.query(AdminAuditEvent).count() == 1

        user = db.query(User).filter(User.whatsapp_id == booking.whatsapp_id).one()
        assert user.flow_state == "PAYMENT_CONFIRMED"
        assert user.last_payment_link is None
    finally:
        db.close()


def test_unpaid_link_is_left_unchanged(reconciliation_db):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(_provider_entity(status="created")),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["not_paid"] == 1
    db = reconciliation_db()
    try:
        assert db.get(Booking, booking_id).status == BookingStatus.PENDING
        assert db.query(PaymentReconciliation).count() == 0
    finally:
        db.close()


def test_ambiguous_paid_link_creates_review_without_confirming(
    reconciliation_db,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    entity = _provider_entity(amount=10_000)
    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(entity),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["review_required"] == 1
    db = reconciliation_db()
    try:
        booking = db.get(Booking, booking_id)
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_processed is False
        item = db.query(PaymentReconciliation).one()
        assert item.status == "OPEN"
        assert item.reason == "PROVIDER_AMOUNT_MISMATCH"
    finally:
        db.close()


def test_review_enqueues_one_deduplicated_operations_alert(
    reconciliation_db,
    monkeypatch,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    monkeypatch.setattr(
        reconciliation,
        "PAYMENT_RECONCILIATION_EMAILS",
        ["operations@example.test"],
    )
    entity = _provider_entity(amount=10_000)

    for _ in range(2):
        db = reconciliation_db()
        try:
            stats = reconciliation.reconcile_recent_payment_links(
                db,
                client=FakeClient(entity),
                now=datetime(2026, 7, 29, 12, 0),
            )
            assert stats["review_required"] == 1
        finally:
            db.close()

    db = reconciliation_db()
    try:
        item = db.query(PaymentReconciliation).one()
        jobs = (
            db.query(OutboxJob)
            .filter(OutboxJob.kind == "payment_reconciliation_alert")
            .all()
        )
        assert db.get(Booking, booking_id).payment_processed is False
        assert len(jobs) == 1
        assert jobs[0].dedupe_key == (
            f"payment-review:{item.id}:PROVIDER_AMOUNT_MISMATCH"
        )
    finally:
        db.close()


def test_provider_failure_is_counted_and_does_not_log_secrets(
    reconciliation_db,
    caplog,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient({}, status_code=503),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["provider_errors"] == 1
    assert "rzp_test_key_secret" not in caplog.text
    db = reconciliation_db()
    try:
        assert db.get(Booking, booking_id).status == BookingStatus.PENDING
    finally:
        db.close()


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("missing_currency", "PROVIDER_CURRENCY_MISMATCH"),
        ("null_currency", "PROVIDER_CURRENCY_MISMATCH"),
        ("blank_currency", "PROVIDER_CURRENCY_MISMATCH"),
        ("missing_notes", "PROVIDER_NOTES_MISSING"),
        ("numeric_note_booking_id", "PROVIDER_NOTE_BOOKING_MISMATCH"),
        ("invalid_payment_id", "PAYMENT_ID_INVALID"),
        ("partial_enabled", "PARTIAL_PAYMENT_CONFIGURATION"),
        ("multiple_captures", "CAPTURE_COUNT_MISMATCH"),
        ("uncaptured_payment", "PAYMENT_NOT_CAPTURED"),
        ("missing_reference", "PROVIDER_REFERENCE_MISMATCH"),
    ],
)
def test_malformed_or_ambiguous_capture_never_confirms_booking(
    reconciliation_db,
    case,
    expected_reason,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    entity = deepcopy(_provider_entity())
    if case == "missing_currency":
        entity.pop("currency")
    elif case == "null_currency":
        entity["currency"] = None
    elif case == "blank_currency":
        entity["currency"] = "   "
    elif case == "missing_notes":
        entity.pop("notes")
    elif case == "numeric_note_booking_id":
        entity["notes"]["booking_id"] = booking_id
    elif case == "invalid_payment_id":
        entity["payments"][0]["payment_id"] = "../pay_invalid"
    elif case == "partial_enabled":
        entity["accept_partial"] = True
    elif case == "multiple_captures":
        entity["payments"].append(deepcopy(entity["payments"][0]))
    elif case == "uncaptured_payment":
        entity["payments"][0]["status"] = "authorized"
    elif case == "missing_reference":
        entity.pop("reference_id")

    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(entity),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["review_required"] == 1
    db = reconciliation_db()
    try:
        booking = db.get(Booking, booking_id)
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_processed is False
        item = db.query(PaymentReconciliation).one()
        assert item.reason == expected_reason
        assert db.query(BookingFulfillment).count() == 0
        assert _payment_followup_count(db) == 0
        assert db.query(AdminAuditEvent).count() == 0
    finally:
        db.close()


def test_explicit_empty_provider_currency_uses_documented_inr_default(
    reconciliation_db,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    entity = _provider_entity()
    entity["currency"] = ""

    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(entity),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["recovered"] == 1
    db = reconciliation_db()
    try:
        assert db.get(Booking, booking_id).payment_processed is True
        assert db.query(PaymentReconciliation).one().currency == "INR"
    finally:
        db.close()


@pytest.mark.parametrize("payload", [[], "not-an-object", None])
def test_non_object_provider_response_is_rejected(
    reconciliation_db,
    payload,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(payload),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["provider_errors"] == 1
    db = reconciliation_db()
    try:
        assert db.get(Booking, booking_id).payment_processed is False
        assert db.query(PaymentReconciliation).count() == 0
    finally:
        db.close()


def test_unexpected_provider_exception_does_not_log_secrets(
    reconciliation_db,
    caplog,
):
    secret = "rzp_live_private_secret"
    booking_id, _, _ = _pending_booking(reconciliation_db)

    class ExplodingClient:
        def get(self, _path):
            raise RuntimeError(f"{secret}: provider payload unavailable")

    db = reconciliation_db()
    try:
        with caplog.at_level(logging.ERROR):
            stats = reconciliation.reconcile_recent_payment_links(
                db,
                client=ExplodingClient(),
                now=datetime(2026, 7, 29, 12, 0),
            )
    finally:
        db.close()

    assert stats["provider_errors"] == 1
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    db = reconciliation_db()
    try:
        assert db.get(Booking, booking_id).payment_processed is False
    finally:
        db.close()


def test_followup_failure_rolls_back_entire_payment_acceptance(
    reconciliation_db,
    monkeypatch,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    monkeypatch.setattr(
        reconciliation,
        "enqueue_job",
        MagicMock(side_effect=RuntimeError("outbox unavailable")),
    )

    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(_provider_entity()),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["provider_errors"] == 1
    db = reconciliation_db()
    try:
        booking = db.get(Booking, booking_id)
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_processed is False
        assert booking.razorpay_payment_id is None
        assert db.query(BookingFulfillment).count() == 0
        assert db.query(PaymentReconciliation).count() == 0
        assert _payment_followup_count(db) == 0
        assert db.query(AdminAuditEvent).count() == 0
        user = db.query(User).filter(User.whatsapp_id == booking.whatsapp_id).one()
        assert user.flow_state == "WAITING_PAYMENT"
        assert user.last_payment_link == "https://rzp.test/link"
    finally:
        db.close()


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("refunded", "PAYMENT_ALREADY_REFUNDED"),
        ("capture_flag_false", "PAYMENT_DETAIL_NOT_CAPTURED"),
        ("wrong_id", "PAYMENT_DETAIL_ID_MISMATCH"),
        ("wrong_entity", "PAYMENT_DETAIL_ENTITY_MISMATCH"),
        ("wrong_amount", "PAYMENT_DETAIL_AMOUNT_MISMATCH"),
        ("wrong_currency", "PAYMENT_DETAIL_CURRENCY_MISMATCH"),
    ],
)
def test_payment_detail_must_be_exact_and_unrefunded(
    reconciliation_db,
    case,
    expected_reason,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    link_entity = _provider_entity()
    payment_entity = _payment_entity_from_link(link_entity)
    if case == "refunded":
        payment_entity["amount_refunded"] = 10_000
        payment_entity["refund_status"] = "partial"
    elif case == "capture_flag_false":
        payment_entity["captured"] = False
    elif case == "wrong_id":
        payment_entity["id"] = "pay_Different123"
    elif case == "wrong_entity":
        payment_entity["entity"] = "refund"
    elif case == "wrong_amount":
        payment_entity["amount"] = 10_000
    elif case == "wrong_currency":
        payment_entity["currency"] = "USD"

    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(
                link_entity,
                payment_payload=payment_entity,
            ),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["review_required"] == 1
    db = reconciliation_db()
    try:
        assert db.get(Booking, booking_id).payment_processed is False
        assert db.query(PaymentReconciliation).one().reason == expected_reason
        assert db.query(BookingFulfillment).count() == 0
        assert _payment_followup_count(db) == 0
    finally:
        db.close()


def test_malformed_payment_detail_response_is_retryable_provider_error(
    reconciliation_db,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(
                _provider_entity(),
                payment_payload=[],
            ),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["provider_errors"] == 1
    db = reconciliation_db()
    try:
        assert db.get(Booking, booking_id).payment_processed is False
        assert db.query(PaymentReconciliation).count() == 0
    finally:
        db.close()


@pytest.mark.parametrize("review_key", ["payment", "link"])
def test_manual_payment_disposition_is_never_auto_confirmed(
    reconciliation_db,
    review_key,
):
    booking_id, payment_link_id, _ = _pending_booking(reconciliation_db)
    db = reconciliation_db()
    try:
        db.add(
            PaymentReconciliation(
                provider="razorpay",
                payment_id=(
                    "pay_Reconcile123"
                    if review_key == "payment"
                    else f"link:{payment_link_id}"
                ),
                payment_link_id=payment_link_id,
                booking_id=booking_id,
                reason="OPERATOR_REFUND",
                status="REFUNDED",
                resolution_note="Refund completed by finance.",
            )
        )
        db.commit()
    finally:
        db.close()

    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(_provider_entity()),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["review_required"] == 1
    db = reconciliation_db()
    try:
        assert db.get(Booking, booking_id).payment_processed is False
        item = db.query(PaymentReconciliation).one()
        assert item.status == "REFUNDED"
        assert item.reason == "OPERATOR_REFUND"
        assert item.resolution_note == "Refund completed by finance."
        assert _payment_followup_count(db) == 0
    finally:
        db.close()


def test_payment_identity_collision_preserves_original_association(
    reconciliation_db,
):
    booking_id, payment_link_id, _ = _pending_booking(reconciliation_db)
    other_id, other_link_id, _ = _pending_booking(
        reconciliation_db,
        serial="999",
    )
    db = reconciliation_db()
    try:
        other = db.get(Booking, other_id)
        other.status = BookingStatus.PAID
        other.payment_processed = True
        other.razorpay_payment_id = "pay_Reconcile123"
        db.add(
            PaymentReconciliation(
                provider="razorpay",
                payment_id="pay_Reconcile123",
                payment_link_id=other_link_id,
                booking_id=other_id,
                reason="ORIGINAL_ASSOCIATION",
                status="OPEN",
            )
        )
        db.commit()
    finally:
        db.close()

    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=FakeClient(_provider_entity(booking_id=booking_id)),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["review_required"] == 1
    db = reconciliation_db()
    try:
        assert db.get(Booking, booking_id).payment_processed is False
        original = (
            db.query(PaymentReconciliation)
            .filter(
                PaymentReconciliation.payment_id == "pay_Reconcile123"
            )
            .one()
        )
        assert original.booking_id == other_id
        assert original.payment_link_id == other_link_id
        collision = (
            db.query(PaymentReconciliation)
            .filter(
                PaymentReconciliation.payment_id
                == f"link:{payment_link_id}"
            )
            .one()
        )
        assert collision.booking_id == booking_id
        assert collision.reason == "PAYMENT_IDENTITY_COLLISION"
    finally:
        db.close()


def test_concurrent_different_payment_is_flagged_not_silently_replayed(
    reconciliation_db,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)

    class ConcurrentPaymentClient(FakeClient):
        def get(self, path):
            concurrent_db = reconciliation_db()
            try:
                booking = concurrent_db.get(Booking, booking_id)
                booking.status = BookingStatus.PAID
                booking.payment_processed = True
                booking.razorpay_payment_id = "pay_ConcurrentOther"
                concurrent_db.commit()
            finally:
                concurrent_db.close()
            return super().get(path)

    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=ConcurrentPaymentClient(_provider_entity()),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["review_required"] == 1
    db = reconciliation_db()
    try:
        booking = db.get(Booking, booking_id)
        assert booking.razorpay_payment_id == "pay_ConcurrentOther"
        item = db.query(PaymentReconciliation).one()
        assert item.reason == "BOOKING_ALREADY_PAID_WITH_DIFFERENT_PAYMENT"
        assert _payment_followup_count(db) == 0
    finally:
        db.close()


def test_concurrent_malformed_capture_is_preserved_for_review(
    reconciliation_db,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    entity = _provider_entity()
    entity["currency"] = None

    class ConcurrentSamePaymentClient(FakeClient):
        def get(self, path):
            concurrent_db = reconciliation_db()
            try:
                booking = concurrent_db.get(Booking, booking_id)
                booking.status = BookingStatus.PAID
                booking.payment_processed = True
                booking.razorpay_payment_id = "pay_Reconcile123"
                concurrent_db.commit()
            finally:
                concurrent_db.close()
            return super().get(path)

    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=ConcurrentSamePaymentClient(entity),
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert stats["review_required"] == 1
    assert stats["already_processed"] == 0
    db = reconciliation_db()
    try:
        booking = db.get(Booking, booking_id)
        assert booking.razorpay_payment_id == "pay_Reconcile123"
        item = db.query(PaymentReconciliation).one()
        assert item.reason == "PROVIDER_CURRENCY_MISMATCH"
        assert item.status == "OPEN"
        assert _payment_followup_count(db) == 0
    finally:
        db.close()


def test_recent_capture_is_not_starved_by_old_unpaid_backlog(
    reconciliation_db,
):
    old_id, old_link, old_token = _pending_booking(
        reconciliation_db,
        serial="001",
        created_at=datetime(2026, 7, 28, 8, 0),
    )
    new_id, new_link, new_token = _pending_booking(
        reconciliation_db,
        serial="002",
        created_at=datetime(2026, 7, 29, 11, 0),
    )
    client = MappingClient(
        {
            f"/v1/payment_links/{old_link}": _provider_entity(
                status="created",
                booking_id=old_id,
                payment_link_id=old_link,
                payment_token=old_token,
                payment_id="pay_Reconcile001",
            ),
            f"/v1/payment_links/{new_link}": _provider_entity(
                booking_id=new_id,
                payment_link_id=new_link,
                payment_token=new_token,
                payment_id="pay_Reconcile002",
            ),
        }
    )

    db = reconciliation_db()
    try:
        stats = reconciliation.reconcile_recent_payment_links(
            db,
            client=client,
            limit=1,
            now=datetime(2026, 7, 29, 12, 0),
        )
    finally:
        db.close()

    assert client.paths == [
        f"/v1/payment_links/{new_link}",
        "/v1/payments/pay_Reconcile002",
    ]
    assert stats["recovered"] == 1
    db = reconciliation_db()
    try:
        assert db.get(Booking, old_id).payment_processed is False
        assert db.get(Booking, new_id).payment_processed is True
    finally:
        db.close()


def test_fulfillment_retry_does_not_extend_existing_sla(
    reconciliation_db,
    monkeypatch,
):
    booking_id, _, _ = _pending_booking(reconciliation_db)
    first_now = datetime(2026, 7, 29, 12, 0)
    monkeypatch.setattr(fulfillment_service, "utc_now", lambda: first_now)

    db = reconciliation_db()
    try:
        booking = db.get(Booking, booking_id)
        booking.status = BookingStatus.PAID
        booking.payment_processed = True
        fulfillment = fulfillment_service.ensure_booking_fulfillment(
            db,
            booking,
        )
        db.commit()
        original_sla = fulfillment.sla_due_at

        monkeypatch.setattr(
            fulfillment_service,
            "utc_now",
            lambda: first_now + timedelta(hours=3),
        )
        replay = fulfillment_service.ensure_booking_fulfillment(db, booking)
        db.commit()

        assert replay.sla_due_at == original_sla
        assert db.query(BookingFulfillment).count() == 1
    finally:
        db.close()


def test_reconciliation_job_reports_provider_errors_and_closes_session(
    monkeypatch,
    capsys,
):
    db = MagicMock()
    stats = {
        "checked": 2,
        "recovered": 1,
        "already_processed": 0,
        "not_paid": 0,
        "review_required": 0,
        "provider_errors": 1,
    }
    reconcile = MagicMock(return_value=stats)
    monkeypatch.setattr(
        reconciliation_job,
        "SessionLocal",
        MagicMock(return_value=db),
    )
    monkeypatch.setattr(
        reconciliation_job,
        "reconcile_recent_payment_links",
        reconcile,
    )

    result = reconciliation_job.main(["--limit", "25"])

    assert result == 2
    reconcile.assert_called_once_with(db, limit=25)
    db.close.assert_called_once_with()
    assert json.loads(capsys.readouterr().out) == {"ok": False, **stats}


def test_reconciliation_job_rolls_back_and_sanitizes_failures(
    monkeypatch,
    capsys,
):
    db = MagicMock()
    monkeypatch.setattr(
        reconciliation_job,
        "SessionLocal",
        MagicMock(return_value=db),
    )
    monkeypatch.setattr(
        reconciliation_job,
        "reconcile_recent_payment_links",
        MagicMock(
            side_effect=RuntimeError(
                "rzp_live_secret must not appear in output"
            )
        ),
    )

    result = reconciliation_job.main([])

    assert result == 2
    db.rollback.assert_called_once_with()
    db.close.assert_called_once_with()
    output = capsys.readouterr().out
    assert "rzp_live_secret" not in output
    assert json.loads(output) == {"error": "RuntimeError", "ok": False}
