from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.pool import StaticPool

import admin
from db import Base
from models import (
    AdminAuditEvent,
    Booking,
    BookingFulfillment,
    BookingStatus,
    PaymentReconciliation,
    SupportRequest,
    User,
)
from services.engagement_service import booking_status_message


@pytest.fixture
def admin_db(monkeypatch, app_module):
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
    monkeypatch.setattr(admin, "SessionLocal", testing_session)
    monkeypatch.setattr(admin, "ADMIN_TOKEN", "admin-test-token")
    app_module.app.config.update(TESTING=True)
    try:
        yield testing_session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _headers(*, operator=True):
    headers = {"Authorization": "Bearer admin-test-token"}
    if operator:
        headers["X-Operator-ID"] = "ops.user@example.com"
    return headers


def _seed_operations(session_factory):
    db = session_factory()
    try:
        user = User(
            whatsapp_id="919955551234",
            case_id="NS-ADMIN01",
            name="Admin Test User",
        )
        db.add(user)
        db.flush()
        support = SupportRequest(
            user_id=user.id,
            case_id=user.case_id,
            request_type="PAYMENT",
            message="Please check my payment.",
            status="OPEN",
        )
        booking = Booking(
            whatsapp_id=user.whatsapp_id,
            name=user.name,
            phone=user.whatsapp_id,
            state_name="Maharashtra",
            district_name="Pune",
            category="Family",
            subcategory="Other Family Issue",
            date=date(2026, 8, 3),
            slot_code="10_11",
            slot_readable="10:00 AM - 11:00 AM",
            amount=499,
            status=BookingStatus.PAID,
            payment_token="admin-token",
            razorpay_payment_link_id="plink_Admin123",
            razorpay_payment_id="pay_Admin123",
            payment_processed=True,
        )
        db.add_all([support, booking])
        db.flush()
        fulfillment = BookingFulfillment(
            booking_id=booking.id,
            status="UNASSIGNED",
        )
        reconciliation = PaymentReconciliation(
            provider="razorpay",
            payment_id="pay_Review123",
            payment_link_id=booking.razorpay_payment_link_id,
            booking_id=booking.id,
            reason="TEST_REVIEW",
            status="OPEN",
        )
        db.add_all([fulfillment, reconciliation])
        db.commit()
        return {
            "support_id": support.id,
            "booking_id": booking.id,
            "reconciliation_id": reconciliation.id,
        }
    finally:
        db.close()


def test_admin_requires_bearer_token_and_operator_for_mutations(
    client,
    admin_db,
):
    assert client.get("/admin/metrics").status_code == 401
    assert client.get("/admin/metrics", headers=_headers()).status_code == 200

    response = client.post(
        "/admin/availability/blackouts",
        headers=_headers(operator=False),
        json={"date": "2026-08-04", "reason": "Court holiday"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "valid_x_operator_id_required"


def test_support_resolution_is_audited(client, admin_db):
    seeded = _seed_operations(admin_db)
    response = client.patch(
        f"/admin/support/{seeded['support_id']}",
        headers=_headers(),
        json={
            "status": "RESOLVED",
            "assigned_to": "Support Team",
            "resolution_note": "Payment status explained to the user.",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "RESOLVED"

    db = admin_db()
    try:
        ticket = db.get(SupportRequest, seeded["support_id"])
        assert ticket.resolved_at is not None
        audit = db.query(AdminAuditEvent).one()
        assert audit.operator_id == "ops.user@example.com"
        assert audit.action == "support.update"
    finally:
        db.close()


def test_paid_consultation_assignment_and_completion_are_explicit(
    client,
    admin_db,
):
    seeded = _seed_operations(admin_db)
    booking_id = seeded["booking_id"]

    assigned = client.patch(
        f"/admin/fulfillments/{booking_id}",
        headers=_headers(),
        json={
            "status": "ASSIGNED",
            "assigned_to": "Verified Advocate",
        },
    )
    assert assigned.status_code == 200
    assert assigned.get_json()["item"]["fulfillment_status"] == "ASSIGNED"

    completed = client.patch(
        f"/admin/fulfillments/{booking_id}",
        headers=_headers(),
        json={
            "status": "COMPLETED",
            "operator_notes": "Consultation completed with the client.",
        },
    )
    assert completed.status_code == 200

    db = admin_db()
    try:
        assert db.get(Booking, booking_id).status == BookingStatus.COMPLETED
        fulfillment = (
            db.query(BookingFulfillment)
            .filter(BookingFulfillment.booking_id == booking_id)
            .one()
        )
        assert fulfillment.completed_at is not None
        assert db.query(AdminAuditEvent).count() == 2
    finally:
        db.close()


def test_refunded_fulfillment_revokes_entitlement_and_preserves_payment(
    client,
    admin_db,
    monkeypatch,
):
    lock_order = []
    original_with_for_update = Query.with_for_update

    def record_lock(query, *args, **kwargs):
        entity = query.column_descriptions[0].get("entity")
        if entity in {
            Booking,
            PaymentReconciliation,
            BookingFulfillment,
            User,
        }:
            lock_order.append(entity)
        return original_with_for_update(query, *args, **kwargs)

    monkeypatch.setattr(Query, "with_for_update", record_lock)
    seeded = _seed_operations(admin_db)
    booking_id = seeded["booking_id"]
    db = admin_db()
    try:
        fulfillment = (
            db.query(BookingFulfillment)
            .filter(BookingFulfillment.booking_id == booking_id)
            .one()
        )
        fulfillment.status = "REFUND_REVIEW"
        user = db.query(User).one()
        user.flow_state = "PAYMENT_CONFIRMED"
        user.ai_enabled = True
        user.temp_date = "2026-08-03"
        user.temp_slot = "10_11"
        user.last_payment_link = "https://rzp.example.test/link"
        db.commit()
    finally:
        db.close()

    response = client.patch(
        f"/admin/fulfillments/{booking_id}",
        headers=_headers(),
        json={
            "status": "REFUNDED",
            "operator_notes": "Full refund confirmed in Razorpay.",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["item"]
    assert payload["fulfillment_status"] == "REFUNDED"
    assert payload["payment_status"] == "CANCELLED"

    db = admin_db()
    try:
        booking = db.get(Booking, booking_id)
        fulfillment = (
            db.query(BookingFulfillment)
            .filter(BookingFulfillment.booking_id == booking_id)
            .one()
        )
        user = db.query(User).one()
        assert booking.status == BookingStatus.CANCELLED
        assert booking.payment_processed is True
        assert booking.razorpay_payment_id == "pay_Admin123"
        assert booking.razorpay_payment_link_id == "plink_Admin123"
        assert fulfillment.status == "REFUNDED"
        reconciliations = db.query(PaymentReconciliation).all()
        assert len(reconciliations) == 2
        assert {item.status for item in reconciliations} == {"REFUNDED"}
        exact_reconciliation = next(
            item
            for item in reconciliations
            if item.payment_id == booking.razorpay_payment_id
        )
        assert exact_reconciliation.booking_id == booking.id
        assert exact_reconciliation.reason == "FULFILLMENT_REFUNDED"
        assert (
            exact_reconciliation.resolution_note
            == "Full refund confirmed in Razorpay."
        )
        assert user.flow_state == "NORMAL"
        assert user.ai_enabled is False
        assert user.temp_date is None
        assert user.temp_slot is None
        assert user.last_payment_link is None
        assert "Payment refunded" in booking_status_message(user, booking)
    finally:
        db.close()
    assert lock_order[:4] == [
        Booking,
        PaymentReconciliation,
        BookingFulfillment,
        User,
    ]


def test_paid_fulfillment_cannot_be_cancelled_without_refund_workflow(
    client,
    admin_db,
):
    seeded = _seed_operations(admin_db)
    booking_id = seeded["booking_id"]

    response = client.patch(
        f"/admin/fulfillments/{booking_id}",
        headers=_headers(),
        json={
            "status": "CANCELLED",
            "operator_notes": "Customer requested cancellation.",
        },
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error": "invalid_fulfillment_transition",
        "from": "UNASSIGNED",
        "to": "CANCELLED",
    }
    db = admin_db()
    try:
        booking = db.get(Booking, booking_id)
        fulfillment = (
            db.query(BookingFulfillment)
            .filter(BookingFulfillment.booking_id == booking_id)
            .one()
        )
        assert booking.status == BookingStatus.PAID
        assert booking.payment_processed is True
        assert fulfillment.status == "UNASSIGNED"
        assert db.query(AdminAuditEvent).count() == 0
    finally:
        db.close()


def test_reconciliation_resolution_locks_booking_before_reviews(
    client,
    admin_db,
    monkeypatch,
):
    seeded = _seed_operations(admin_db)
    lock_order = []
    original_with_for_update = Query.with_for_update

    def record_lock(query, *args, **kwargs):
        entity = query.column_descriptions[0].get("entity")
        if entity in {Booking, PaymentReconciliation}:
            lock_order.append(entity)
        return original_with_for_update(query, *args, **kwargs)

    monkeypatch.setattr(Query, "with_for_update", record_lock)
    response = client.patch(
        (
            "/admin/payment-reconciliations/"
            f"{seeded['reconciliation_id']}"
        ),
        headers=_headers(),
        json={
            "status": "RESOLVED",
            "resolution_note": "Provider evidence reconciled.",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "RESOLVED"
    assert lock_order[:2] == [Booking, PaymentReconciliation]


def test_paid_reconciliation_refund_requires_fulfillment_workflow(
    client,
    admin_db,
):
    seeded = _seed_operations(admin_db)
    booking_id = seeded["booking_id"]
    reconciliation_id = seeded["reconciliation_id"]
    db = admin_db()
    try:
        user = db.query(User).one()
        user.flow_state = "PAYMENT_CONFIRMED"
        user.ai_enabled = True
        db.commit()
    finally:
        db.close()

    direct_refund = client.patch(
        f"/admin/payment-reconciliations/{reconciliation_id}",
        headers=_headers(),
        json={
            "status": "REFUNDED",
            "resolution_note": "Provider reports refund complete.",
        },
    )
    direct_initiation = client.patch(
        f"/admin/payment-reconciliations/{reconciliation_id}",
        headers=_headers(),
        json={
            "status": "REFUND_INITIATED",
            "resolution_note": "Refund submitted to provider.",
        },
    )

    assert direct_refund.status_code == 409
    assert (
        direct_refund.get_json()["error"]
        == "fulfillment_refund_required"
    )
    assert direct_initiation.status_code == 409
    assert (
        direct_initiation.get_json()["error"]
        == "fulfillment_refund_review_required"
    )

    review = client.patch(
        f"/admin/fulfillments/{booking_id}",
        headers=_headers(),
        json={
            "status": "REFUND_REVIEW",
            "operator_notes": "Refund requested by customer.",
        },
    )
    initiated = client.patch(
        f"/admin/payment-reconciliations/{reconciliation_id}",
        headers=_headers(),
        json={
            "status": "REFUND_INITIATED",
            "resolution_note": "Refund submitted to provider.",
        },
    )
    premature_completion = client.patch(
        f"/admin/payment-reconciliations/{reconciliation_id}",
        headers=_headers(),
        json={
            "status": "REFUNDED",
            "resolution_note": "Provider reports refund complete.",
        },
    )

    assert review.status_code == 200
    assert initiated.status_code == 200
    assert initiated.get_json()["status"] == "REFUND_INITIATED"
    assert premature_completion.status_code == 409
    assert (
        premature_completion.get_json()["error"]
        == "fulfillment_refund_required"
    )

    db = admin_db()
    try:
        booking = db.get(Booking, booking_id)
        fulfillment = (
            db.query(BookingFulfillment)
            .filter(BookingFulfillment.booking_id == booking_id)
            .one()
        )
        reconciliation = db.get(
            PaymentReconciliation,
            reconciliation_id,
        )
        user = db.query(User).one()
        # REFUND_INITIATED pauses fulfillment but is not proof that funds have
        # returned, so entitlement is revoked only on confirmed REFUNDED.
        assert booking.status == BookingStatus.PAID
        assert fulfillment.status == "REFUND_REVIEW"
        assert reconciliation.status == "REFUND_INITIATED"
        assert user.flow_state == "PAYMENT_CONFIRMED"
        assert user.ai_enabled is True
    finally:
        db.close()

    completed = client.patch(
        f"/admin/fulfillments/{booking_id}",
        headers=_headers(),
        json={
            "status": "REFUNDED",
            "operator_notes": "Full refund confirmed in Razorpay.",
        },
    )
    idempotent_financial_update = client.patch(
        f"/admin/payment-reconciliations/{reconciliation_id}",
        headers=_headers(),
        json={
            "status": "REFUNDED",
            "resolution_note": "Full refund confirmed in Razorpay.",
        },
    )

    assert completed.status_code == 200
    assert idempotent_financial_update.status_code == 200
    db = admin_db()
    try:
        booking = db.get(Booking, booking_id)
        fulfillment = (
            db.query(BookingFulfillment)
            .filter(BookingFulfillment.booking_id == booking_id)
            .one()
        )
        reconciliation = db.get(
            PaymentReconciliation,
            reconciliation_id,
        )
        user = db.query(User).one()
        assert booking.status == BookingStatus.CANCELLED
        assert fulfillment.status == "REFUNDED"
        assert reconciliation.status == "REFUNDED"
        assert user.flow_state == "NORMAL"
        assert user.ai_enabled is False
    finally:
        db.close()


def test_availability_and_payment_review_mutations_are_audited(
    client,
    admin_db,
):
    seeded = _seed_operations(admin_db)
    blackout = client.post(
        "/admin/availability/blackouts",
        headers=_headers(),
        json={"date": "2026-08-04", "reason": "Court holiday"},
    )
    assert blackout.status_code == 201

    capacity = client.post(
        "/admin/availability/capacity",
        headers=_headers(),
        json={
            "date": "2026-08-05",
            "slot_code": "3_4",
            "capacity": 2,
        },
    )
    assert capacity.status_code == 201

    resolved = client.patch(
        (
            "/admin/payment-reconciliations/"
            f"{seeded['reconciliation_id']}"
        ),
        headers=_headers(),
        json={
            "status": "RESOLVED",
            "resolution_note": "Matched against the provider dashboard.",
        },
    )
    assert resolved.status_code == 200

    db = admin_db()
    try:
        item = db.get(
            PaymentReconciliation,
            seeded["reconciliation_id"],
        )
        assert item.status == "RESOLVED"
        assert db.query(AdminAuditEvent).count() == 3
    finally:
        db.close()
