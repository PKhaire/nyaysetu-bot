from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query

from models import (
    Booking,
    BookingStatus,
    OutboxJob,
    PaymentReconciliation,
    User,
    WebhookEvent,
)


RAZORPAY_SECRET = "test-razorpay-secret"


def _payment_payload(
    *,
    payment_id="pay_test001",
    payment_link_id="plink_test001",
    amount=49_900,
    currency="INR",
):
    return {
        "event": "payment_link.paid",
        "created_at": int(time.time()),
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "status": "captured",
                    "amount": amount,
                    "currency": currency,
                }
            },
            "payment_link": {
                "entity": {
                    "id": payment_link_id,
                    "status": "paid",
                }
            },
        },
    }


def _signed_payment_post(client, payload, *, secret=RAZORPAY_SECRET):
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/payment/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Razorpay-Signature": signature},
    )


def _create_pending_booking(
    session_factory,
    *,
    amount=499,
    payment_link_id="plink_test001",
):
    db = session_factory()
    try:
        user = User(
            whatsapp_id="919900001111",
            case_id="NS-PAYTEST",
            language="en",
            name="Payment Test",
            flow_state="WAITING_PAYMENT",
            welcome_sent=True,
            last_payment_link="https://rzp.test/pay",
        )
        booking = Booking(
            whatsapp_id=user.whatsapp_id,
            name=user.name,
            phone=user.whatsapp_id,
            state_name="Maharashtra",
            district_name="Pune",
            category="Family",
            subcategory="Divorce",
            date=time_to_date(),
            slot_code="3_4",
            slot_readable="03:00 PM - 04:00 PM",
            amount=amount,
            status=BookingStatus.PENDING,
            payment_token="payment-token-001",
            razorpay_payment_link_id=payment_link_id,
            payment_processed=False,
        )
        db.add_all([user, booking])
        db.commit()
        return booking.id
    finally:
        db.close()


def time_to_date():
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(days=1)).date()


def _configure_payment_route(monkeypatch, app_module):
    monkeypatch.setattr(
        app_module,
        "RAZORPAY_WEBHOOK_SECRET",
        RAZORPAY_SECRET,
        raising=False,
    )
    monkeypatch.setattr(app_module, "RAZORPAY_MODE", "test", raising=False)
    monkeypatch.setattr(
        app_module,
        "BOOKING_NOTIFICATION_EMAILS",
        (),
        raising=False,
    )
    monkeypatch.setattr(app_module, "AUTO_SEND_RECEIPTS", False, raising=False)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", RAZORPAY_SECRET)
    monkeypatch.setenv("RAZORPAY_MODE", "test")

    def current_capture(payment_link_id, payment_id):
        return (
            {
                "id": payment_link_id,
                "status": "paid",
                "amount": 49_900,
                "amount_paid": 49_900,
                "currency": "INR",
                "accept_partial": False,
                "reference_id": "payment-token-001",
                "notes": {
                    "booking_token": "payment-token-001",
                    "booking_id": "1",
                },
                "payments": [
                    {
                        "payment_id": payment_id,
                        "status": "captured",
                        "amount": 49_900,
                    }
                ],
            },
            {
                "id": payment_id,
                "entity": "payment",
                "status": "captured",
                "captured": True,
                "amount": 49_900,
                "currency": "INR",
                "amount_refunded": 0,
                "refund_status": None,
            },
        )

    monkeypatch.setattr(
        app_module,
        "fetch_current_razorpay_capture",
        current_capture,
    )


def test_payment_webhook_rejects_invalid_signature_before_mutation(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _configure_payment_route(monkeypatch, app_module)
    _create_pending_booking(isolated_app_db)
    payload = _payment_payload()
    body = json.dumps(payload, separators=(",", ":")).encode()

    response = client.post(
        "/payment/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Razorpay-Signature": "definitely-invalid"},
    )

    assert response.status_code in {400, 401, 403}
    db = isolated_app_db()
    try:
        booking = db.query(Booking).one()
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_processed is False
        assert db.query(WebhookEvent).count() == 0
        assert db.query(OutboxJob).count() == 0
    finally:
        db.close()


def test_payment_webhook_rejects_malformed_provider_ids_before_lookup(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _configure_payment_route(monkeypatch, app_module)
    _create_pending_booking(isolated_app_db)
    provider_lookup_called = False

    def provider_lookup(*_args, **_kwargs):
        nonlocal provider_lookup_called
        provider_lookup_called = True
        raise AssertionError("malformed identifiers must not reach Razorpay")

    monkeypatch.setattr(
        app_module,
        "fetch_current_razorpay_capture",
        provider_lookup,
    )

    response = _signed_payment_post(
        client,
        _payment_payload(payment_id="pay_bad-id"),
    )

    assert response.status_code == 400
    assert provider_lookup_called is False
    db = isolated_app_db()
    try:
        booking = db.query(Booking).one()
        assert booking.status == BookingStatus.PENDING
        assert db.query(WebhookEvent).count() == 0
        assert db.query(PaymentReconciliation).count() == 0
    finally:
        db.close()


def test_payment_webhook_verifies_signature_before_parsing_json(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _configure_payment_route(monkeypatch, app_module)
    invalid_json = b"{this-is-not-json"

    invalid_signature = client.post(
        "/payment/webhook",
        data=invalid_json,
        content_type="application/json",
        headers={"X-Razorpay-Signature": "invalid"},
    )
    valid_signature = hmac.new(
        RAZORPAY_SECRET.encode(),
        invalid_json,
        hashlib.sha256,
    ).hexdigest()
    invalid_json_response = client.post(
        "/payment/webhook",
        data=invalid_json,
        content_type="application/json",
        headers={"X-Razorpay-Signature": valid_signature},
    )

    assert invalid_signature.status_code == 400
    assert invalid_signature.get_data(as_text=True) == "Invalid signature"
    assert invalid_json_response.status_code == 400
    assert invalid_json_response.get_data(as_text=True) == "Invalid JSON"


def test_payment_webhook_accepts_booking_stored_price_not_current_global_price(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
    deferred_threads,
):
    _configure_payment_route(monkeypatch, app_module)
    booking_id = _create_pending_booking(isolated_app_db, amount=499)
    monkeypatch.setattr(app_module, "BOOKING_PRICE", 999)

    response = _signed_payment_post(
        client,
        _payment_payload(amount=49_900),
    )

    assert response.status_code == 200
    assert len(deferred_threads) == 1
    db = isolated_app_db()
    try:
        booking = db.get(Booking, booking_id)
        user = db.query(User).filter_by(whatsapp_id=booking.whatsapp_id).one()
        event = db.query(WebhookEvent).one()
        assert booking.status == BookingStatus.PAID
        assert booking.payment_processed is True
        assert booking.razorpay_payment_id == "pay_test001"
        assert event.status == "DONE"
        assert event.event_id == "pay_test001"
        assert event.processed_at is not None
        assert user.flow_state == app_module.PAYMENT_CONFIRMED
        assert user.last_payment_link is None
        assert (
            db.query(OutboxJob)
            .filter_by(kind="payment_success_message")
            .count()
            == 1
        )
        assert db.query(OutboxJob).count() == 1
    finally:
        db.close()


def test_payment_webhook_rejects_amount_not_matching_stored_booking(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
    deferred_threads,
):
    _configure_payment_route(monkeypatch, app_module)
    booking_id = _create_pending_booking(isolated_app_db, amount=499)

    response = _signed_payment_post(
        client,
        _payment_payload(amount=99_900),
    )

    assert response.status_code == 202
    db = isolated_app_db()
    try:
        booking = db.get(Booking, booking_id)
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_processed is False
        assert db.query(OutboxJob).count() == 0
        event = db.query(WebhookEvent).one()
        assert event.status == "AMOUNT_MISMATCH"
        reconciliation = db.query(PaymentReconciliation).one()
        assert reconciliation.status == "OPEN"
        assert reconciliation.reason == "AMOUNT_OR_CURRENCY_MISMATCH"
    finally:
        db.close()


def test_payment_retry_does_not_reopen_refunded_reconciliation(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _configure_payment_route(monkeypatch, app_module)
    _create_pending_booking(isolated_app_db, amount=499)
    payload = _payment_payload(amount=99_900)

    first = _signed_payment_post(client, payload)
    assert first.status_code == 202

    db = isolated_app_db()
    try:
        reconciliation = db.query(PaymentReconciliation).one()
        reconciliation.status = "REFUNDED"
        reconciliation.resolved_by = "operator@example.test"
        reconciliation.resolved_at = app_module.utc_now()
        reconciliation.resolution_note = "Refund confirmed in provider portal."
        db.commit()
    finally:
        db.close()

    replay = _signed_payment_post(client, payload)

    assert replay.status_code == 202
    db = isolated_app_db()
    try:
        reconciliation = db.query(PaymentReconciliation).one()
        assert reconciliation.status == "REFUNDED"
        assert reconciliation.resolved_by == "operator@example.test"
        assert (
            reconciliation.resolution_note
            == "Refund confirmed in provider portal."
        )
    finally:
        db.close()


@pytest.mark.parametrize(
    "terminal_status",
    ["IGNORED", "RESOLVED", "REFUND_INITIATED", "REFUNDED"],
)
def test_exact_delayed_payment_preserves_manual_terminal_disposition(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    terminal_status,
):
    _configure_payment_route(monkeypatch, app_module)
    booking_id = _create_pending_booking(isolated_app_db)
    db = isolated_app_db()
    try:
        db.add(
            PaymentReconciliation(
                provider="razorpay",
                payment_id="pay_test001",
                payment_link_id="plink_test001",
                booking_id=booking_id,
                reason="OPERATOR_REVIEW",
                status=terminal_status,
                resolved_by="ops.user@example.test",
                resolved_at=app_module.utc_now(),
                resolution_note="Disposition confirmed against provider data.",
            )
        )
        db.commit()
    finally:
        db.close()

    def unavailable_provider(*_args, **_kwargs):
        raise AssertionError(
            "terminal operator dispositions must not depend on Razorpay"
        )

    monkeypatch.setattr(
        app_module,
        "fetch_current_razorpay_capture",
        unavailable_provider,
    )
    response = _signed_payment_post(client, _payment_payload())

    assert response.status_code == 202
    db = isolated_app_db()
    try:
        booking = db.get(Booking, booking_id)
        reconciliation = db.query(PaymentReconciliation).one()
        event = db.query(WebhookEvent).one()
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_processed is False
        assert reconciliation.status == terminal_status
        assert reconciliation.resolved_by == "ops.user@example.test"
        assert event.status == "MANUAL_DISPOSITION"
        assert db.query(OutboxJob).count() == 0
    finally:
        db.close()


def test_unmatched_terminal_disposition_stops_delayed_webhook_retries(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _configure_payment_route(monkeypatch, app_module)
    db = isolated_app_db()
    try:
        db.add(
            PaymentReconciliation(
                provider="razorpay",
                payment_id="pay_unmatched001",
                payment_link_id="plink_unmatched001",
                booking_id=None,
                reason="BOOKING_NOT_FOUND",
                status="IGNORED",
                resolved_by="ops.user@example.test",
                resolved_at=app_module.utc_now(),
                resolution_note="Provider evidence reviewed; no action needed.",
            )
        )
        db.commit()
    finally:
        db.close()

    def unavailable_provider(*_args, **_kwargs):
        raise AssertionError(
            "closed unmatched cases must not depend on Razorpay"
        )

    monkeypatch.setattr(
        app_module,
        "fetch_current_razorpay_capture",
        unavailable_provider,
    )

    response = _signed_payment_post(
        client,
        _payment_payload(
            payment_id="pay_unmatched001",
            payment_link_id="plink_unmatched001",
        ),
    )

    assert response.status_code == 202
    db = isolated_app_db()
    try:
        reconciliation = db.query(PaymentReconciliation).one()
        event = db.query(WebhookEvent).one()
        assert reconciliation.status == "IGNORED"
        assert reconciliation.booking_id is None
        assert reconciliation.resolved_by == "ops.user@example.test"
        assert event.status == "MANUAL_DISPOSITION"
        assert db.query(Booking).count() == 0
        assert db.query(OutboxJob).count() == 0
    finally:
        db.close()


def test_terminal_lookup_locks_open_and_terminal_matching_reviews(
    monkeypatch,
    app_module,
    isolated_app_db,
):
    booking_id = _create_pending_booking(isolated_app_db)
    db = isolated_app_db()
    try:
        db.add_all(
            [
                PaymentReconciliation(
                    provider="razorpay",
                    payment_id="pay_test001",
                    payment_link_id="plink_test001",
                    booking_id=booking_id,
                    reason="OPEN_REVIEW",
                    status="OPEN",
                ),
                PaymentReconciliation(
                    provider="razorpay",
                    payment_id="pay_terminal002",
                    payment_link_id="plink_test001",
                    booking_id=booking_id,
                    reason="OPERATOR_REVIEW",
                    status="REFUND_INITIATED",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    locked_sql = []
    original_with_for_update = Query.with_for_update

    def record_lock(query, *args, **kwargs):
        locked_query = original_with_for_update(query, *args, **kwargs)
        entity = query.column_descriptions[0].get("entity")
        if entity is PaymentReconciliation:
            locked_sql.append(
                str(
                    locked_query.statement.compile(
                        dialect=postgresql.dialect()
                    )
                )
            )
        return locked_query

    monkeypatch.setattr(Query, "with_for_update", record_lock)
    db = isolated_app_db()
    try:
        disposition = app_module._find_manual_payment_disposition(
            db,
            payment_id="pay_test001",
            payment_link_id="plink_test001",
        )
        assert disposition.payment_id == "pay_terminal002"
        assert disposition.status == "REFUND_INITIATED"
    finally:
        db.rollback()
        db.close()

    assert len(locked_sql) == 1
    assert "FOR UPDATE" in locked_sql[0]
    where_clause = locked_sql[0].split("\nWHERE ", maxsplit=1)[1]
    where_clause = where_clause.split("\nORDER BY ", maxsplit=1)[0]
    assert "payment_reconciliations.status IN" not in where_clause


def test_current_refunded_payment_is_queued_without_granting_entitlement(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _configure_payment_route(monkeypatch, app_module)
    booking_id = _create_pending_booking(isolated_app_db)
    valid_fetch = app_module.fetch_current_razorpay_capture

    def refunded_capture(payment_link_id, payment_id):
        payment_link, payment = valid_fetch(payment_link_id, payment_id)
        payment["amount_refunded"] = payment["amount"]
        payment["refund_status"] = "full"
        return payment_link, payment

    monkeypatch.setattr(
        app_module,
        "fetch_current_razorpay_capture",
        refunded_capture,
    )

    response = _signed_payment_post(client, _payment_payload())

    assert response.status_code == 202
    db = isolated_app_db()
    try:
        booking = db.get(Booking, booking_id)
        reconciliation = db.query(PaymentReconciliation).one()
        event = db.query(WebhookEvent).one()
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_processed is False
        assert reconciliation.status == "OPEN"
        assert reconciliation.reason == "PAYMENT_ALREADY_REFUNDED"
        assert event.status == "CURRENT_STATE_REVIEW"
        assert db.query(OutboxJob).count() == 0
    finally:
        db.close()


def test_provider_verification_failure_requests_retry_without_entitlement(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _configure_payment_route(monkeypatch, app_module)
    booking_id = _create_pending_booking(isolated_app_db)

    def unavailable_provider(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        app_module,
        "fetch_current_razorpay_capture",
        unavailable_provider,
    )

    response = _signed_payment_post(client, _payment_payload())

    assert response.status_code == 503
    db = isolated_app_db()
    try:
        booking = db.get(Booking, booking_id)
        event = db.query(WebhookEvent).one()
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_processed is False
        assert event.status == "FAILED"
        assert db.query(PaymentReconciliation).count() == 0
        assert db.query(OutboxJob).count() == 0
    finally:
        db.close()


def test_payment_webhook_replay_is_idempotent(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
    deferred_threads,
):
    _configure_payment_route(monkeypatch, app_module)
    booking_id = _create_pending_booking(isolated_app_db)
    payload = _payment_payload()

    first = _signed_payment_post(client, payload)
    replay = _signed_payment_post(client, payload)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert len(deferred_threads) == 1
    db = isolated_app_db()
    try:
        booking = db.get(Booking, booking_id)
        user = db.query(User).filter_by(whatsapp_id=booking.whatsapp_id).one()
        event = db.query(WebhookEvent).one()
        assert booking.status == BookingStatus.PAID
        assert booking.razorpay_payment_id == "pay_test001"
        assert event.status == "DONE"
        assert user.flow_state == app_module.PAYMENT_CONFIRMED
        assert user.last_payment_link is None
        assert (
            db.query(OutboxJob)
            .filter_by(kind="payment_success_message")
            .count()
            == 1
        )
        assert db.query(OutboxJob).count() == 1
    finally:
        db.close()


def test_payment_processing_failure_returns_retryable_status(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
    deferred_threads,
):
    _configure_payment_route(monkeypatch, app_module)
    booking_id = _create_pending_booking(isolated_app_db)

    def fail_payment_update(*args, **kwargs):
        raise RuntimeError("temporary database failure")

    monkeypatch.setattr(app_module, "mark_booking_as_paid", fail_payment_update)
    response = _signed_payment_post(client, _payment_payload())

    assert 500 <= response.status_code < 600
    db = isolated_app_db()
    try:
        booking = db.get(Booking, booking_id)
        user = db.query(User).filter_by(whatsapp_id=booking.whatsapp_id).one()
        event = db.query(WebhookEvent).one()
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_processed is False
        assert user.flow_state == "WAITING_PAYMENT"
        assert user.last_payment_link == "https://rzp.test/pay"
        assert event.status == "FAILED"
        assert db.query(OutboxJob).count() == 0
    finally:
        db.close()


def test_captured_payment_without_booking_requests_provider_retry(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _configure_payment_route(monkeypatch, app_module)

    response = _signed_payment_post(
        client,
        _payment_payload(payment_link_id="plink_unknown"),
    )

    assert 500 <= response.status_code < 600
    db = isolated_app_db()
    try:
        event = db.query(WebhookEvent).one()
        assert event.status == "UNMATCHED"
        reconciliation = db.query(PaymentReconciliation).one()
        assert reconciliation.status == "OPEN"
        assert reconciliation.reason == "BOOKING_NOT_FOUND"
        assert db.query(OutboxJob).count() == 0
    finally:
        db.close()


def test_health_endpoints_distinguish_liveness_and_readiness(
    monkeypatch,
    app_module,
    client,
):
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.get_json()["ok"] is True

    monkeypatch.setattr(
        app_module,
        "get_db_health",
        lambda: {"ok": False, "backend": "sqlite", "latency_ms": 1.25},
    )
    not_ready = client.get("/health/ready")

    assert not_ready.status_code == 503
    assert not_ready.get_json()["ok"] is False
    assert not_ready.get_json()["database"]["ok"] is False
    assert not_ready.headers["X-Content-Type-Options"] == "nosniff"


def test_production_readiness_rejects_sqlite(
    monkeypatch,
    app_module,
    client,
):
    monkeypatch.setattr(app_module, "ENV", "production")
    monkeypatch.setattr(
        app_module,
        "get_db_health",
        lambda: {"ok": True, "backend": "sqlite", "latency_ms": 1.0},
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["database"]["production_compatible"] is False


def test_production_readiness_validates_secret_policy_and_contact_contract(
    monkeypatch,
    app_module,
    client,
):
    production_values = {
        "ENV": "production",
        "ADMIN_TOKEN": "a" * 32,
        "AUTO_CREATE_SCHEMA": False,
        "WHATSAPP_APP_SECRET": "b" * 32,
        "WHATSAPP_APP_SECRET_PREVIOUS": "",
        "WHATSAPP_PHONE_ID": "1234567890",
        "WHATSAPP_TOKEN": "whatsapp-production-token-with-entropy",
        "WHATSAPP_VERIFY_TOKEN": "verify-token-with-entropy",
        "RAZORPAY_MODE": "live",
        "RAZORPAY_KEY_ID": "rzp_live_releasekey",
        "RAZORPAY_KEY_SECRET": "razorpay-key-secret",
        "RAZORPAY_WEBHOOK_SECRET": "razorpay-webhook-secret",
        "RAZORPAY_WEBHOOK_SECRET_PREVIOUS": "",
        "AI_SAFETY_IDENTIFIER_SECRET": "c" * 32,
        "SENDGRID_API_KEY": "SG.release-test-token",
        "SENDGRID_FROM_EMAIL": "notifications@example.test",
        "BOOKING_NOTIFICATION_EMAILS": ["bookings@example.test"],
        "SUPPORT_NOTIFICATION_EMAILS": ["support-ops@example.test"],
        "SUPPORT_EMAIL": "support@example.test",
        "PRIVACY_EMAIL": "privacy@example.test",
        "PRIVACY_POLICY_URL": "https://example.test/privacy",
        "TERMS_OF_SERVICE_URL": "https://example.test/terms",
        "REFUND_POLICY_URL": "https://example.test/refunds",
        "CANCELLATION_POLICY_URL": "https://example.test/cancellations",
        "LEGAL_CONTENT_REVIEWED_ON": datetime.now(
            app_module.IST
        ).date().isoformat(),
    }
    for name, value in production_values.items():
        monkeypatch.setattr(app_module, name, value)
    monkeypatch.setattr(
        app_module,
        "get_db_health",
        lambda: {"ok": True, "backend": "postgresql", "latency_ms": 1.0},
    )
    monkeypatch.setattr(
        app_module,
        "get_schema_revision",
        lambda: app_module.EXPECTED_SCHEMA_REVISION,
    )

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.get_json()["configuration"] == "ok"

    monkeypatch.setattr(app_module, "PRIVACY_POLICY_URL", "http://example.test")
    invalid_policy = client.get("/health/ready")
    assert invalid_policy.status_code == 503
    assert invalid_policy.get_json()["configuration"] == "incomplete"

    monkeypatch.setattr(
        app_module,
        "PRIVACY_POLICY_URL",
        production_values["PRIVACY_POLICY_URL"],
    )
    weak_secrets = {
        "WHATSAPP_APP_SECRET": "short",
        "WHATSAPP_APP_SECRET_PREVIOUS": "short",
        "WHATSAPP_TOKEN": "short",
        "RAZORPAY_KEY_SECRET": "short",
        "RAZORPAY_WEBHOOK_SECRET_PREVIOUS": "short",
        "SENDGRID_API_KEY": "SG.short",
    }
    for name, weak_value in weak_secrets.items():
        monkeypatch.setattr(app_module, name, weak_value)
        weak = client.get("/health/ready")
        assert weak.status_code == 503, name
        assert weak.get_json()["configuration"] == "incomplete"
        monkeypatch.setattr(app_module, name, production_values[name])

    monkeypatch.setattr(
        app_module,
        "WHATSAPP_APP_SECRET_PREVIOUS",
        "d" * 32,
    )
    monkeypatch.setattr(
        app_module,
        "RAZORPAY_WEBHOOK_SECRET_PREVIOUS",
        "rotating-webhook-secret",
    )
    rotating = client.get("/health/ready")
    assert rotating.status_code == 200
    assert rotating.get_json()["configuration"] == "ok"
