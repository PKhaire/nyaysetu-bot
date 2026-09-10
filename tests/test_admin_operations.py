from __future__ import annotations

import base64
from datetime import date, timedelta
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.pool import StaticPool

import admin
from db import Base
from services import document_catalogue as catalogue
from models import (
    AdminAuditEvent,
    Advocate,
    Booking,
    BookingFulfillment,
    BookingStatus,
    CaseBrief,
    DocumentAuditEvent,
    DocumentOrder,
    ManualContactEvent,
    OutboxJob,
    PaymentReconciliation,
    SupportRequest,
    User,
    utc_now,
)
from services.document_operations_service import DocumentOperationResult
from services.document_catalogue import PRODUCT_CODE
from services.engagement_service import booking_status_message
from services.admin_identity_service import (
    begin_operator_enrollment,
    confirm_operator_enrollment,
    set_operator_active,
    totp_code,
)


ADMIN_MFA_KEY = base64.urlsafe_b64encode(b"a" * 32).decode("ascii")


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
    monkeypatch.setattr(
        admin,
        "ADMIN_PASSWORD",
        "strong-admin-test-password",
    )
    monkeypatch.setattr(admin, "ADMIN_MFA_ENCRYPTION_KEY", ADMIN_MFA_KEY)
    original_config = {
        key: app_module.app.config.get(key)
        for key in (
            "SECRET_KEY",
            "SESSION_COOKIE_SECURE",
            "TESTING",
        )
    }
    app_module.app.config.update(
        TESTING=True,
        SECRET_KEY="test-browser-session-secret-value-123456",
        SESSION_COOKIE_SECURE=False,
    )
    admin._login_attempts.clear()
    try:
        yield testing_session
    finally:
        admin._login_attempts.clear()
        app_module.app.config.update(original_config)
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
        advocate = Advocate(
            name="Verified Advocate",
            email="advocate@example.test",
            phone="919988887777",
            bar_registration_number="MAH/1234/2020",
            category="Family",
            district="Pune",
            languages="English, Hindi, Marathi",
            active=True,
        )
        brief = CaseBrief(
            user_id=user.id,
            booking_id=booking.id,
            status="CONFIRMED",
            issue_summary="A family-law consultation is required.",
            legal_stage="Before court or formal filing",
            important_dates="No known immediate deadline",
            desired_outcome="Understand available legal options.",
            urgency="Standard",
            documents_json='["Agreement or contract"]',
            consent_version="case-brief-sharing-2026-08",
        )
        db.add_all([advocate, brief])
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
            "advocate_id": advocate.id,
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


def _browser_login(client, *, operator_id="ops.user@example.com"):
    login_page = client.get("/admin/login")
    assert login_page.status_code == 200
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["admin_csrf_token"]
    response = client.post(
        "/admin/login",
        data={
            "operator_id": operator_id,
            "password": "strong-admin-test-password",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/appointments")


def test_admin_browser_login_dashboard_and_security_headers(client, admin_db):
    unauthenticated = client.get("/admin/appointments")
    assert unauthenticated.status_code == 302
    assert unauthenticated.headers["Location"].endswith("/admin/login")

    invalid_page = client.get("/admin/login")
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["admin_csrf_token"]
    invalid = client.post(
        "/admin/login",
        data={
            "operator_id": "ops.user@example.com",
            "password": "incorrect-password-value",
            "csrf_token": csrf_token,
        },
    )
    assert invalid_page.status_code == 200
    assert invalid.status_code == 200
    assert b"Invalid operator ID or password" in invalid.data

    _browser_login(client)
    dashboard = client.get("/admin/appointments")

    assert dashboard.status_code == 200
    assert b"Appointment control desk" in dashboard.data
    assert dashboard.headers["Cache-Control"] == "no-store, max-age=0"
    assert dashboard.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in dashboard.headers["Content-Security-Policy"]


def test_named_admin_browser_login_requires_password_and_authenticator_code(
    client,
    admin_db,
):
    now = datetime.now(timezone.utc)
    db = admin_db()
    try:
        enrollment = begin_operator_enrollment(
            db,
            operator_id="Named.Admin@example.com",
            display_name="Named Administrator",
            role="ADMIN",
            password="named admin password value",
            encryption_key=ADMIN_MFA_KEY,
            now=now,
        )
        confirm_operator_enrollment(
            db,
            operator_id=enrollment.operator_id,
            verification_code=totp_code(enrollment.secret, timestamp=now),
            encryption_key=ADMIN_MFA_KEY,
            now=now,
        )
        db.commit()
    finally:
        db.close()

    login_page = client.get("/admin/login")
    assert b"Authenticator code" in login_page.data
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["admin_csrf_token"]

    missing_code = client.post(
        "/admin/login",
        data={
            "operator_id": "named.admin@example.com",
            "password": "named admin password value",
            "csrf_token": csrf_token,
        },
    )
    assert missing_code.status_code == 200

    authenticated = client.post(
        "/admin/login",
        data={
            "operator_id": "named.admin@example.com",
            "password": "named admin password value",
            "verification_code": totp_code(
                enrollment.secret,
                timestamp=datetime.now(timezone.utc),
            ),
            "csrf_token": csrf_token,
        },
    )
    assert authenticated.status_code == 302
    assert authenticated.headers["Location"].endswith("/admin/appointments")
    with client.session_transaction() as browser_session:
        assert browser_session["operator_id"] == "named.admin@example.com"
        assert browser_session["admin_role"] == "ADMIN"
        assert browser_session["admin_mfa_authenticated"] is True
    db = admin_db()
    try:
        login_audit = db.query(AdminAuditEvent).one()
        assert login_audit.operator_id == "named.admin@example.com"
        assert login_audit.action == "admin.login"
        assert "totp" in login_audit.after_json
    finally:
        db.close()


@pytest.mark.parametrize("role", ("VIEWER", "OPERATOR"))
def test_named_non_admin_can_read_but_cannot_change_admin_only_data(
    client,
    admin_db,
    role,
):
    now = datetime.now(timezone.utc)
    operator_id = f"{role.lower()}@example.com"
    db = admin_db()
    try:
        enrollment = begin_operator_enrollment(
            db,
            operator_id=operator_id,
            display_name=f"Named {role.title()}",
            role=role,
            password="non admin password is long enough",
            encryption_key=ADMIN_MFA_KEY,
            now=now,
        )
        confirm_operator_enrollment(
            db,
            operator_id=enrollment.operator_id,
            verification_code=totp_code(enrollment.secret, timestamp=now),
            encryption_key=ADMIN_MFA_KEY,
            now=now,
        )
        db.commit()
    finally:
        db.close()

    client.get("/admin/login")
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["admin_csrf_token"]
    login = client.post(
        "/admin/login",
        data={
            "operator_id": enrollment.operator_id,
            "password": "non admin password is long enough",
            "verification_code": totp_code(
                enrollment.secret,
                timestamp=datetime.now(timezone.utc),
            ),
            "csrf_token": csrf_token,
        },
    )
    assert login.status_code == 302
    assert client.get("/admin/metrics").status_code == 200

    with client.session_transaction() as browser_session:
        csrf_token = browser_session["admin_csrf_token"]
    forbidden = client.post(
        "/admin/availability/blackouts",
        headers={"X-CSRF-Token": csrf_token},
        json={"date": "2026-09-15", "reason": "Security role test"},
    )

    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"] == "insufficient_role"


def test_named_admin_audit_actor_cannot_be_overridden_by_request_header(
    client,
    admin_db,
):
    now = datetime.now(timezone.utc)
    db = admin_db()
    try:
        enrollment = begin_operator_enrollment(
            db,
            operator_id="verified.admin@example.com",
            display_name="Verified Administrator",
            role="ADMIN",
            password="verified password is long enough",
            encryption_key=ADMIN_MFA_KEY,
            now=now,
        )
        confirm_operator_enrollment(
            db,
            operator_id=enrollment.operator_id,
            verification_code=totp_code(enrollment.secret, timestamp=now),
            encryption_key=ADMIN_MFA_KEY,
            now=now,
        )
        db.commit()
    finally:
        db.close()

    client.get("/admin/login")
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["admin_csrf_token"]
    login = client.post(
        "/admin/login",
        data={
            "operator_id": enrollment.operator_id,
            "password": "verified password is long enough",
            "verification_code": totp_code(
                enrollment.secret,
                timestamp=datetime.now(timezone.utc),
            ),
            "csrf_token": csrf_token,
        },
    )
    assert login.status_code == 302

    with client.session_transaction() as browser_session:
        csrf_token = browser_session["admin_csrf_token"]
    changed = client.post(
        "/admin/availability/blackouts",
        headers={
            "X-CSRF-Token": csrf_token,
            "X-Operator-ID": "spoofed.actor@example.com",
        },
        json={"date": "2026-09-15", "reason": "Audit identity test"},
    )
    assert changed.status_code == 201

    db = admin_db()
    try:
        event = (
            db.query(AdminAuditEvent)
            .filter(AdminAuditEvent.action == "availability.blackout.create")
            .one()
        )
        assert event.operator_id == "verified.admin@example.com"
    finally:
        db.close()


def test_disabling_and_reenabling_named_operator_invalidates_old_session(
    client,
    admin_db,
):
    now = datetime.now(timezone.utc)
    db = admin_db()
    try:
        enrollments = {}
        for operator_id in (
            "session.admin@example.com",
            "backup.admin@example.com",
        ):
            enrollment = begin_operator_enrollment(
                db,
                operator_id=operator_id,
                display_name=operator_id,
                role="ADMIN",
                password="session password is long enough",
                encryption_key=ADMIN_MFA_KEY,
                now=now,
            )
            confirm_operator_enrollment(
                db,
                operator_id=operator_id,
                verification_code=totp_code(
                    enrollment.secret,
                    timestamp=now,
                ),
                encryption_key=ADMIN_MFA_KEY,
                now=now,
            )
            enrollments[operator_id] = enrollment
        db.commit()
    finally:
        db.close()

    client.get("/admin/login")
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["admin_csrf_token"]
    login = client.post(
        "/admin/login",
        data={
            "operator_id": "session.admin@example.com",
            "password": "session password is long enough",
            "verification_code": totp_code(
                enrollments["session.admin@example.com"].secret,
                timestamp=datetime.now(timezone.utc),
            ),
            "csrf_token": csrf_token,
        },
    )
    assert login.status_code == 302

    db = admin_db()
    try:
        set_operator_active(
            db,
            operator_id="session.admin@example.com",
            active=False,
        )
        set_operator_active(
            db,
            operator_id="session.admin@example.com",
            active=True,
        )
        db.commit()
    finally:
        db.close()

    expired = client.get("/admin/appointments")
    assert expired.status_code == 302
    assert expired.headers["Location"].endswith("/admin/login")


def test_admin_browser_session_requires_csrf_and_audits_operator(
    client,
    admin_db,
):
    ids = _seed_operations(admin_db)
    _browser_login(client, operator_id="browser.ops@example.com")

    queue = client.get("/admin/fulfillments")
    workflow = client.get("/admin/fulfillment-workflow")
    assert queue.status_code == 200
    assert workflow.status_code == 200

    missing_csrf = client.patch(
        f"/admin/fulfillments/{ids['booking_id']}",
        json={"status": "ASSIGNED", "assigned_to": "Advocate One"},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.get_json()["error"] == "invalid_csrf_token"

    with client.session_transaction() as browser_session:
        csrf_token = browser_session["admin_csrf_token"]
    updated = client.patch(
        f"/admin/fulfillments/{ids['booking_id']}",
        headers={"X-CSRF-Token": csrf_token},
        json={"status": "ASSIGNED", "advocate_id": ids["advocate_id"]},
    )
    assert updated.status_code == 200
    assert updated.get_json()["item"]["fulfillment_status"] == "ASSIGNED"

    db = admin_db()
    try:
        audit = db.query(AdminAuditEvent).order_by(AdminAuditEvent.id.desc()).first()
        assert audit.operator_id == "browser.ops@example.com"
    finally:
        db.close()

    logged_out = client.post(
        "/admin/logout",
        data={"csrf_token": csrf_token},
    )
    assert logged_out.status_code == 302
    assert client.get("/admin/fulfillments").status_code == 401


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
            "advocate_id": seeded["advocate_id"],
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


def test_queue_masks_contact_and_reveal_and_manual_handover_are_audited(
    client,
    admin_db,
):
    seeded = _seed_operations(admin_db)
    booking_id = seeded["booking_id"]

    queue_response = client.get("/admin/fulfillments", headers=_headers())
    assert queue_response.status_code == 200
    queue_item = queue_response.get_json()["items"][0]
    assert queue_item["contact_masked"] == "••••••1234"
    assert "whatsapp_id" not in queue_item
    assert queue_item["case_brief"]["issue_summary"].startswith("A family")
    assert queue_item["case_brief"]["preparation_status"] == "INCOMPLETE"

    missing_reason = client.post(
        f"/admin/fulfillments/{booking_id}/contact-reveal",
        headers=_headers(),
        json={"reason": "short"},
    )
    assert missing_reason.status_code == 400

    revealed = client.post(
        f"/admin/fulfillments/{booking_id}/contact-reveal",
        headers=_headers(),
        json={"reason": "Contacting client about paid appointment assignment."},
    )
    assert revealed.status_code == 200
    assert revealed.get_json()["contact"] == "919955551234"

    assigned = client.patch(
        f"/admin/fulfillments/{booking_id}",
        headers=_headers(),
        json={
            "status": "ASSIGNED",
            "advocate_id": seeded["advocate_id"],
        },
    )
    assert assigned.status_code == 200

    contacted = client.post(
        f"/admin/fulfillments/{booking_id}/contact-events",
        headers=_headers(),
        json={
            "audience": "CLIENT",
            "channel": "WHATSAPP",
            "outcome": "INFORMATION_SHARED",
            "notes": "Appointment and assigned advocate details shared manually.",
        },
    )
    assert contacted.status_code == 201
    assert contacted.get_json()["event"]["operator_id"] == "ops.user@example.com"

    db = admin_db()
    try:
        actions = {
            item.action for item in db.query(AdminAuditEvent).all()
        }
        assert "client_contact.reveal" in actions
        assert "manual_contact.record" in actions
        event = db.query(ManualContactEvent).one()
        assert event.audience == "CLIENT"
        assert event.outcome == "INFORMATION_SHARED"
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


def test_document_studio_ledger_excludes_answers_and_contact_data(
    client,
    admin_db,
):
    db = admin_db()
    try:
        user = User(
            whatsapp_id="919900009999",
            case_id="NS-DOC-ADMIN",
            name="Private Synthetic User",
        )
        db.add(user)
        db.flush()
        db.add(
            DocumentOrder(
                public_ref="DSU-ADMIN01",
                user_id=user.id,
                product_code=(
                    "mh_residential_leave_licence_11m_self_service"
                ),
                template_version="mh-ll-11m-self-service-2026-08-v1",
                state="DRAFTING",
                current_step="licensee_full_name",
                draft_answers_json=(
                    '{"licensor_full_name":"Do Not Expose This Answer"}'
                ),
                output_classification="SELF_SERVICE_DRAFT",
                uat_only=False,
                release_status="CANDIDATE",
                exception_code="AWAITING_EXACT_APPROVAL",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/admin/document-orders", headers=_headers())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["scope"] == "all_document_orders"
    assert payload["capacity"]["limit"] == 10
    assert payload["capacity"]["used"] == 0
    assert payload["capacity"]["remaining"] == 10
    assert payload["items"] == [
        {
            "reference": "DSU-ADMIN01",
            "product_code": (
                "mh_residential_leave_licence_11m_self_service"
            ),
            "template_version": "mh-ll-11m-self-service-2026-08-v1",
            "state": "DRAFTING",
            "current_step": "licensee_full_name",
            "output_classification": "SELF_SERVICE_DRAFT",
            "release_status": "CANDIDATE",
            "exception_code": "AWAITING_EXACT_APPROVAL",
            "payment_processed": False,
            "final_available_until": None,
            "created_at": payload["items"][0]["created_at"],
            "updated_at": payload["items"][0]["updated_at"],
        }
    ]
    serialized = response.get_data(as_text=True)
    assert "Do Not Expose This Answer" not in serialized
    assert "919900009999" not in serialized
    assert "Private Synthetic User" not in serialized


def test_document_release_endpoint_uses_explicit_product_code(
    client,
    admin_db,
):
    response = client.get(
        f"/admin/document-template-release?product_code={PRODUCT_CODE}",
        headers=_headers(),
    )
    unknown = client.get(
        "/admin/document-template-release?product_code=unknown_product",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.get_json()["manifest"]["product_code"] == PRODUCT_CODE
    assert unknown.status_code == 404
    assert unknown.get_json() == {"error": "unknown_document_product"}


def test_document_admin_views_filter_by_registered_product(
    client,
    admin_db,
):
    db = admin_db()
    try:
        user = User(
            whatsapp_id="919911110001",
            case_id="NS-PRODUCT-FILTER",
        )
        db.add(user)
        db.flush()
        current = DocumentOrder(
            public_ref="DS-PRODUCT-CURRENT",
            user_id=user.id,
            product_code=PRODUCT_CODE,
            template_version="current-v1",
            state="DRAFTING",
            current_step="review",
            draft_answers_json="{}",
            output_classification="SELF_SERVICE_DRAFT",
        )
        other = DocumentOrder(
            public_ref="DS-PRODUCT-OTHER",
            user_id=user.id,
            product_code="historical_removed_product",
            template_version="historical-v1",
            state="ABANDONED",
            current_step="closed",
            draft_answers_json="{}",
            output_classification="SELF_SERVICE_DRAFT",
        )
        db.add_all((current, other))
        db.flush()
        db.add_all(
            (
                AdminAuditEvent(
                    operator_id="test-operator",
                    action="document_order.reconcile",
                    target_type="document_order",
                    target_id=current.public_ref,
                ),
                AdminAuditEvent(
                    operator_id="test-operator",
                    action="document_order.reconcile",
                    target_type="document_order",
                    target_id=other.public_ref,
                ),
            )
        )
        db.commit()
    finally:
        db.close()

    orders = client.get(
        f"/admin/document-orders?product_code={PRODUCT_CODE}",
        headers=_headers(),
    )
    metrics = client.get(
        f"/admin/metrics?product_code={PRODUCT_CODE}",
        headers=_headers(),
    )
    audit = client.get(
        f"/admin/audit?product_code={PRODUCT_CODE}",
        headers=_headers(),
    )
    unknown = client.get(
        "/admin/document-orders?product_code=unknown_product",
        headers=_headers(),
    )

    assert orders.status_code == 200
    assert orders.get_json()["scope"] == f"document_product:{PRODUCT_CODE}"
    assert [item["reference"] for item in orders.get_json()["items"]] == [
        "DS-PRODUCT-CURRENT"
    ]
    assert metrics.status_code == 200
    operations = metrics.get_json()["operations"]
    assert operations["document_product_scope"] == PRODUCT_CODE
    assert operations["document_orders_by_state"] == {"DRAFTING": 1}
    assert operations["document_orders_by_product"] == {
        PRODUCT_CODE: {"DRAFTING": 1}
    }
    assert audit.status_code == 200
    assert audit.get_json()["product_scope"] == PRODUCT_CODE
    assert [item["target_id"] for item in audit.get_json()["items"]] == [
        "DS-PRODUCT-CURRENT"
    ]
    assert unknown.status_code == 404


def test_document_product_admin_endpoint_is_non_secret_and_fail_closed(
    monkeypatch,
    client,
    admin_db,
):
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_PRICE_INR", 299)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_PRICES_INR_CONFIGURED",
        False,
    )
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset({PRODUCT_CODE}),
    )

    response = client.get("/admin/document-products", headers=_headers())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["configuration"] == {
        "ok": True,
        "reason_code": "CONFIGURED",
        "enabled_product_codes": [PRODUCT_CODE],
    }
    assert payload["release"]["ok"] is False
    assert payload["release"]["reason_code"] == (
        "ADVOCATE_APPROVAL_MISSING"
    )
    assert payload["items"][0]["customer_visible"] is True
    serialized = response.get_data(as_text=True).lower()
    assert "reviewer_name" not in serialized
    assert "enrolment" not in serialized


def _seed_document_operation(session_factory, *, state="FINAL_AVAILABLE"):
    db = session_factory()
    try:
        user = User(
            whatsapp_id="919911112222",
            case_id="NS-DOC-OPS-ADMIN",
            name="Private Document Customer",
        )
        db.add(user)
        db.flush()
        order = DocumentOrder(
            public_ref="DS-ADMINOPS01",
            user_id=user.id,
            product_code="mh_residential_leave_licence_11m_self_service",
            template_version="mh-ll-en-2026-08-candidate-1",
            state=state,
            current_step="review",
            draft_answers_json='{"private":"never expose"}',
            output_classification="SELF_SERVICE_DRAFT",
            payment_token="admin-document-payment-token",
            razorpay_payment_link_id="plink_admin_document_1",
            razorpay_payment_id=(
                "pay_admin_document_1" if state == "FINAL_AVAILABLE" else None
            ),
            payment_processed=state == "FINAL_AVAILABLE",
            final_available_until=(
                utc_now() + timedelta(days=30)
                if state == "FINAL_AVAILABLE"
                else None
            ),
        )
        db.add(order)
        db.flush()
        db.add(
            DocumentAuditEvent(
                document_order_id=order.id,
                actor_type="SYSTEM",
                event_type="DOCUMENT_TEST_EVENT",
                from_state="PAYMENT_PENDING",
                to_state=state,
                details_json='{"reason_code":"TEST_ONLY"}',
            )
        )
        db.commit()
        return order.id
    finally:
        db.close()


def test_document_order_detail_is_privacy_safe(client, admin_db):
    _seed_document_operation(admin_db)

    response = client.get(
        "/admin/document-orders/DS-ADMINOPS01",
        headers=_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "FINAL_AVAILABLE"
    assert payload["payment_link_present"] is True
    assert payload["payment_id_present"] is True
    assert payload["events"][0]["event_type"] == "DOCUMENT_TEST_EVENT"
    serialized = response.get_data(as_text=True)
    assert "never expose" not in serialized
    assert "919911112222" not in serialized
    assert "Private Document Customer" not in serialized
    assert "plink_admin_document_1" not in serialized
    assert "pay_admin_document_1" not in serialized


def test_admin_can_trigger_audited_document_reconciliation(
    monkeypatch,
    client,
    admin_db,
):
    order_id = _seed_document_operation(admin_db, state="NEEDS_ATTENTION")
    result = DocumentOperationResult(
        True,
        "recovered",
        "DOCUMENT_FINAL_RECOVERED",
        "DS-ADMINOPS01",
        42,
    )
    monkeypatch.setattr(admin, "reconcile_document_order", lambda *_a, **_k: result)

    response = client.post(
        "/admin/document-orders/DS-ADMINOPS01/reconcile",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.get_json()["outcome"] == "recovered"
    db = admin_db()
    try:
        audit = (
            db.query(AdminAuditEvent)
            .filter(AdminAuditEvent.action == "document_order.reconcile")
            .one()
        )
        assert audit.target_id == "DS-ADMINOPS01"
        assert audit.operator_id == "ops.user@example.com"
        assert db.get(DocumentOrder, order_id) is not None
    finally:
        db.close()


def test_admin_refund_review_and_redelivery_are_audited(
    client,
    admin_db,
):
    order_id = _seed_document_operation(admin_db)

    refund = client.post(
        "/admin/document-orders/DS-ADMINOPS01/refund-review",
        headers=_headers(),
        json={"reason": "Manual full refund approved after customer request."},
    )
    assert refund.status_code == 200

    db = admin_db()
    try:
        order = db.get(DocumentOrder, order_id)
        assert order.state == "REFUND_REVIEW"
        # Restore entitlement to exercise the separate redelivery operation.
        order.state = "FINAL_AVAILABLE"
        db.commit()
    finally:
        db.close()

    redelivery = client.post(
        "/admin/document-orders/DS-ADMINOPS01/redeliver",
        headers=_headers(),
        json={
            "reason": "Customer requested a fresh pair of download links.",
            "idempotency_key": "support-ticket-1234",
        },
    )
    assert redelivery.status_code == 202
    replay = client.post(
        "/admin/document-orders/DS-ADMINOPS01/redeliver",
        headers=_headers(),
        json={
            "reason": "Customer repeated the same support request.",
            "idempotency_key": "support-ticket-1234",
        },
    )
    assert replay.status_code == 202
    assert (
        replay.get_json()["delivery_job_id"]
        == redelivery.get_json()["delivery_job_id"]
    )

    db = admin_db()
    try:
        assert (
            db.query(OutboxJob)
            .filter(OutboxJob.kind == "document_final_delivery")
            .count()
            == 1
        )
        actions = {
            row[0]
            for row in db.query(AdminAuditEvent.action)
            .filter(
                AdminAuditEvent.action.in_(
                    (
                        "document_order.refund_review",
                        "document_order.redeliver",
                    )
                )
            )
            .all()
        }
        assert actions == {
            "document_order.refund_review",
            "document_order.redeliver",
        }
    finally:
        db.close()
