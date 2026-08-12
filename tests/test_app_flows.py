from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from models import Booking, InboundMessageEvent, OutboxJob, SupportRequest, User
from services import outbox_service


WHATSAPP_SECRET = "test-whatsapp-secret"


def _whatsapp_payload(
    *,
    message_id,
    wa_id="919911112222",
    text=None,
    interactive_id=None,
):
    if interactive_id is not None:
        message = {
            "from": wa_id,
            "id": message_id,
            "type": "interactive",
            "interactive": {
                "type": "list_reply",
                "list_reply": {"id": interactive_id, "title": "Selected"},
            },
        }
    else:
        message = {
            "from": wa_id,
            "id": message_id,
            "type": "text",
            "text": {"body": text or ""},
        }

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "contacts": [{"wa_id": wa_id}],
                            "messages": [message],
                        },
                    }
                ]
            }
        ],
    }


def _signed_whatsapp_post(client, payload, *, secret=WHATSAPP_SECRET):
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": f"sha256={signature}"},
    )


def test_whatsapp_webhook_rejects_invalid_signature_without_claiming_message(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    body = json.dumps(
        _whatsapp_payload(message_id="wamid.invalid-signature", text="menu"),
        separators=(",", ":"),
    ).encode()

    response = client.post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )

    assert response.status_code == 403
    db = isolated_app_db()
    try:
        assert db.query(InboundMessageEvent).count() == 0
        assert db.query(User).count() == 0
    finally:
        db.close()


def test_whatsapp_webhook_rejects_messages_without_durable_identity(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    malformed_payloads = [
        _whatsapp_payload(message_id=None, text="menu"),
        _whatsapp_payload(
            message_id="wamid.invalid-sender",
            wa_id="not-a-phone-number",
            text="menu",
        ),
        _whatsapp_payload(message_id="x" * 256, text="menu"),
    ]

    responses = [
        _signed_whatsapp_post(client, payload)
        for payload in malformed_payloads
    ]

    assert all(response.status_code == 400 for response in responses)
    db = isolated_app_db()
    try:
        assert db.query(InboundMessageEvent).count() == 0
        assert db.query(User).count() == 0
    finally:
        db.close()


def _create_user(session_factory, *, flow_state, **overrides):
    values = {
        "whatsapp_id": "919911112222",
        "case_id": "NS-FLOWTEST",
        "language": "en",
        "name": "Flow Test",
        "flow_state": flow_state,
        "welcome_sent": True,
    }
    values.update(overrides)
    db = session_factory()
    try:
        user = User(**values)
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _secure_whatsapp_route(monkeypatch, app_module):
    monkeypatch.setattr(
        app_module,
        "WHATSAPP_APP_SECRET",
        WHATSAPP_SECRET,
    )
    monkeypatch.setattr(app_module, "ALLOW_INSECURE_WEBHOOKS", False)
    monkeypatch.setattr(app_module, "ENV", "production")


def _website_advocate_intake(*, summary="My employer has not paid my salary."):
    return "\n".join(
        [
            "Hi NyaySetu, I want to request consultation coordination with an "
            "independent advocate.",
            "",
            "Category: Employment and workplace",
            "Preferred language: English",
            "Known timing: No known immediate deadline",
            f"Question summary: {summary}",
            "",
            "I understand this is NyaySetu intake, not emergency assistance "
            "or a confirmed advocate-client relationship. Please share "
            "availability, scope, professional details and price before any "
            "booking.",
        ]
    )


def test_website_advocate_intake_is_recorded_and_acknowledged(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
    deferred_threads,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    user_id = _create_user(
        isolated_app_db,
        flow_state=app_module.NORMAL,
        language="hi",
    )
    monkeypatch.setattr(
        app_module,
        "SUPPORT_NOTIFICATION_EMAILS",
        ("support@example.com",),
    )

    response = _signed_whatsapp_post(
        client,
        _whatsapp_payload(
            message_id="wamid.website-advocate-intake",
            text=_website_advocate_intake(),
        ),
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "advocate_intake_recorded"
    db = isolated_app_db()
    try:
        user = db.get(User, user_id)
        support_request = db.query(SupportRequest).one()
        job = db.query(OutboxJob).one()
        assert user.language == "en"
        assert user.flow_state == app_module.NORMAL
        assert support_request.request_type == "ADVOCATE_INTAKE"
        assert support_request.subject == (
            "Advocate intake: Employment and workplace"
        )
        assert "Question summary: My employer" in support_request.message
        assert json.loads(job.payload_json) == {
            "support_request_id": support_request.id
        }
        assert deferred_threads == [job.id]
    finally:
        db.close()

    acknowledgement = transport_spies["text"].call_args.args[1]
    assert "NSH-000001" in acknowledgement
    assert "not a confirmed booking" in acknowledgement
    transport_spies["home"].assert_called_once()


def test_website_advocate_intake_duplicate_is_not_recorded_twice(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    _create_user(isolated_app_db, flow_state=app_module.NORMAL)
    monkeypatch.setattr(app_module, "SUPPORT_NOTIFICATION_EMAILS", ())
    message = _website_advocate_intake()

    first = _signed_whatsapp_post(
        client,
        _whatsapp_payload(message_id="wamid.intake-first", text=message),
    )
    second = _signed_whatsapp_post(
        client,
        _whatsapp_payload(message_id="wamid.intake-second", text=message),
    )

    assert first.get_json()["status"] == "advocate_intake_recorded"
    assert second.get_json()["status"] == "advocate_intake_already_recorded"
    db = isolated_app_db()
    try:
        assert db.query(SupportRequest).count() == 1
    finally:
        db.close()
    assert transport_spies["text"].call_count == 2


def test_lookalike_advocate_message_is_not_saved_as_intake(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    _create_user(isolated_app_db, flow_state=app_module.NORMAL)
    malformed = _website_advocate_intake().replace(
        "Category: Employment and workplace",
        "Category: Unapproved category",
    )

    response = _signed_whatsapp_post(
        client,
        _whatsapp_payload(
            message_id="wamid.invalid-advocate-intake",
            text=malformed,
        ),
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ignored"
    db = isolated_app_db()
    try:
        assert db.query(SupportRequest).count() == 0
    finally:
        db.close()
    transport_spies["text"].assert_not_called()


def test_menu_is_persistent_and_does_not_destroy_booking_progress(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    user_id = _create_user(
        isolated_app_db,
        flow_state=app_module.ASK_SLOT,
        temp_date=(
            datetime.now(timezone.utc) + timedelta(days=1)
        ).date().isoformat(),
    )

    response = _signed_whatsapp_post(
        client,
        _whatsapp_payload(message_id="wamid.menu", text="menu"),
    )

    assert response.status_code == 200
    transport_spies["home"].assert_called_once()
    db = isolated_app_db()
    try:
        assert db.get(User, user_id).flow_state == app_module.ASK_SLOT
    finally:
        db.close()


def test_rate_limits_cover_early_menu_routes_and_dedupe_notices(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    _create_user(isolated_app_db, flow_state=app_module.NORMAL)
    monkeypatch.setattr(app_module, "USER_MSG_LIMIT", 2)
    monkeypatch.setattr(app_module, "GLOBAL_REQ_LIMIT", 100)

    responses = [
        _signed_whatsapp_post(
            client,
            _whatsapp_payload(
                message_id=f"wamid.menu-rate-{index}",
                text="menu",
            ),
        )
        for index in range(4)
    ]

    assert all(response.status_code == 200 for response in responses)
    assert transport_spies["home"].call_count == 2
    assert transport_spies["text"].call_count == 1
    assert responses[2].get_json()["status"] == "rate_limited"
    assert responses[3].get_json()["status"] == "rate_limited"

    db = isolated_app_db()
    try:
        assert (
            db.query(InboundMessageEvent)
            .filter(InboundMessageEvent.status == "DONE")
            .count()
            == 4
        )
    finally:
        db.close()


def test_global_rate_limit_covers_early_routes_and_dedupes_busy_message(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    _create_user(isolated_app_db, flow_state=app_module.NORMAL)
    monkeypatch.setattr(app_module, "USER_MSG_LIMIT", 100)
    monkeypatch.setattr(app_module, "GLOBAL_REQ_LIMIT", 1)

    responses = [
        _signed_whatsapp_post(
            client,
            _whatsapp_payload(
                message_id=f"wamid.global-rate-{index}",
                text="menu",
            ),
        )
        for index in range(3)
    ]

    assert all(response.status_code == 200 for response in responses)
    assert transport_spies["home"].call_count == 1
    assert transport_spies["text"].call_count == 1
    assert responses[1].get_json()["status"] == "rate_limited"
    assert responses[2].get_json()["status"] == "rate_limited"


def test_process_local_rate_limit_state_is_bounded_and_prunes_idle_users(
    monkeypatch,
    app_module,
):
    clock = {"now": 1_000.0}
    monkeypatch.setattr(
        app_module.time_module,
        "time",
        lambda: clock["now"],
    )
    monkeypatch.setattr(app_module, "_RATE_LIMIT_STATE_MAX_KEYS", 3)
    monkeypatch.setattr(
        app_module,
        "_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS",
        0.0,
    )
    app_module._rate_limit_last_cleanup = 0.0

    for index in range(10):
        clock["now"] += 1
        wa_id = f"91990000{index:02d}"
        assert app_module.is_user_rate_limited(wa_id) is False
        assert app_module.is_ai_rate_limited(wa_id) is False
        assert app_module.should_send_rate_limit_notice(
            "user",
            wa_id,
            1,
        )
        assert app_module.should_send_maintenance_notice(
            wa_id,
            clock["now"],
        )

    assert len(app_module.user_message_times) <= 3
    assert len(app_module.user_last_ai_call) <= 3
    assert len(app_module._rate_limit_notice_times) <= 3
    assert len(app_module.maintenance_last_sent) <= 3

    clock["now"] += 10_000
    assert app_module.is_user_rate_limited("919911112222") is False
    assert set(app_module.user_message_times) == {"919911112222"}
    assert app_module.user_last_ai_call == {}
    assert app_module._rate_limit_notice_times == {}


def test_outbox_fast_path_is_bounded_and_releases_submission_slot(
    monkeypatch,
    app_module,
):
    slots = MagicMock()
    slots.acquire.return_value = False
    executor = MagicMock()
    monkeypatch.setattr(app_module, "_outbox_submission_slots", slots)
    monkeypatch.setattr(app_module, "_outbox_executor", executor)

    assert app_module.submit_outbox_job(41) is False
    executor.submit.assert_not_called()

    slots.acquire.return_value = True
    processed = MagicMock()
    monkeypatch.setattr(app_module, "process_job", processed)
    executor.submit.side_effect = lambda callback, job_id: callback(job_id)

    assert app_module.submit_outbox_job(42) is True
    processed.assert_called_once_with(42)
    slots.release.assert_called_once_with()


def test_booking_home_action_shows_scope_before_collecting_details(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    user_id = _create_user(
        isolated_app_db,
        flow_state=app_module.NORMAL,
    )

    response = _signed_whatsapp_post(
        client,
        _whatsapp_payload(
            message_id="wamid.booking-scope",
            interactive_id=app_module.HOME_BUTTON_IDS["book"],
        ),
    )

    assert response.status_code == 200
    db = isolated_app_db()
    try:
        user = db.get(User, user_id)
        assert user.flow_state == app_module.REVIEW_SERVICE
        assert db.query(Booking).count() == 0
    finally:
        db.close()

    prompt = transport_spies["buttons"].call_args.args[1]
    assert str(app_module.BOOKING_PRICE) in prompt


def test_legal_guides_form_a_multilingual_tree_with_feedback_and_booking(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    _create_user(
        isolated_app_db,
        flow_state=app_module.NORMAL,
        language="hi",
    )
    events = MagicMock()
    monkeypatch.setattr(app_module, "record_event", events)

    responses = [
        _signed_whatsapp_post(
            client,
            _whatsapp_payload(
                message_id="wamid.guides-root",
                interactive_id=app_module.MORE_MENU_IDS["guides"],
            ),
        ),
        _signed_whatsapp_post(
            client,
            _whatsapp_payload(
                message_id="wamid.guides-job",
                interactive_id="guidecat::job",
            ),
        ),
        _signed_whatsapp_post(
            client,
            _whatsapp_payload(
                message_id="wamid.guides-salary",
                interactive_id="guide::job::unpaid_salary",
            ),
        ),
        _signed_whatsapp_post(
            client,
            _whatsapp_payload(
                message_id="wamid.guides-feedback",
                interactive_id="guidefb::yes::job::unpaid_salary",
            ),
        ),
    ]

    assert all(response.status_code == 200 for response in responses)
    assert transport_spies["list"].call_count == 2
    category_rows = transport_spies["list"].call_args_list[0].kwargs["rows"]
    issue_rows = transport_spies["list"].call_args_list[1].kwargs["rows"]
    assert len(category_rows) == len(app_module.CATEGORY_SUBCATEGORIES)
    assert any(row["id"] == "guidecat::job" for row in category_rows)
    assert any(row["id"] == "guide::job::unpaid_salary" for row in issue_rows)

    guide_message = transport_spies["text"].call_args_list[0].args[1]
    guide_call = transport_spies["buttons"].call_args_list[0]
    assert "Abhi kya karein" in guide_message
    assert "Baki Tankhwa" in guide_message
    assert any(button["id"] == "book_now" for button in guide_call.args[2])

    feedback_events = [
        call
        for call in events.call_args_list
        if call.args and call.args[0] == "legal_guide_feedback"
    ]
    assert len(feedback_events) == 1
    assert feedback_events[0].args[1]["helpful"] is True


def test_slot_selection_requires_review_before_payment_link_creation(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    user_id = _create_user(
        isolated_app_db,
        flow_state=app_module.ASK_SLOT,
        state_name="Maharashtra",
        district_name="Pune",
        category="Family",
        subcategory="Divorce",
        temp_date=(
            datetime.now(timezone.utc) + timedelta(days=1)
        ).date().isoformat(),
    )

    response = _signed_whatsapp_post(
        client,
        _whatsapp_payload(
            message_id="wamid.slot-review",
            interactive_id="slot_3_4",
        ),
    )

    assert response.status_code == 200
    db = isolated_app_db()
    try:
        user = db.get(User, user_id)
        assert user.flow_state == app_module.REVIEW_BOOKING
        assert user.temp_slot == "3_4"
        assert db.query(Booking).count() == 0
    finally:
        db.close()

    review_prompt = transport_spies["buttons"].call_args.args[1]
    assert str(app_module.BOOKING_PRICE) in review_prompt


def test_failed_message_is_released_for_provider_retry(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    _create_user(isolated_app_db, flow_state=app_module.NORMAL)
    payload = _whatsapp_payload(message_id="wamid.retryable", text="menu")
    transport_spies["home"].side_effect = RuntimeError("temporary transport error")

    failed = _signed_whatsapp_post(client, payload)

    assert 500 <= failed.status_code < 600
    db = isolated_app_db()
    try:
        event = (
            db.query(InboundMessageEvent)
            .filter_by(message_id="wamid.retryable")
            .one()
        )
        assert event.status == "FAILED"
        assert event.attempts == 1
    finally:
        db.close()

    transport_spies["home"].side_effect = None
    retried = _signed_whatsapp_post(client, payload)
    assert retried.status_code == 200

    db = isolated_app_db()
    try:
        event = (
            db.query(InboundMessageEvent)
            .filter_by(message_id="wamid.retryable")
            .one()
        )
        assert event.status == "DONE"
        assert event.attempts == 2
    finally:
        db.close()


def test_committed_state_is_not_replayed_when_safe_delivery_is_deferred(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    deferred_threads,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    user_id = _create_user(isolated_app_db, flow_state=app_module.NORMAL)
    payload = _whatsapp_payload(
        message_id="wamid.committed-delivery-retry",
        interactive_id=app_module.MORE_MENU_IDS["language"],
    )
    initial_send = MagicMock(
        return_value={
            "ok": False,
            "error": "whatsapp_transport_error",
            "reason": "ConnectTimeout",
        }
    )
    monkeypatch.setattr(app_module, "_wa_send_buttons", initial_send)

    first = _signed_whatsapp_post(client, payload)

    assert first.status_code == 200
    assert first.get_json()["status"] == "delivery_queued"
    db = isolated_app_db()
    try:
        user = db.get(User, user_id)
        event = (
            db.query(InboundMessageEvent)
            .filter_by(message_id="wamid.committed-delivery-retry")
            .one()
        )
        job = (
            db.query(OutboxJob)
            .filter_by(kind=outbox_service.CONVERSATION_DELIVERY_KIND)
            .one()
        )
        job_id = job.id
        queued_payload = json.loads(job.payload_json)
        assert user.flow_state == app_module.ASK_LANGUAGE
        assert event.status == "DONE"
        assert event.attempts == 1
        assert event.last_error.startswith("OutboundDeliveryQueued:")
        assert job.status == outbox_service.PENDING
        assert queued_payload["operation"] == "buttons"
        assert queued_payload["to"] == user.whatsapp_id
    finally:
        db.close()
    assert deferred_threads == [job_id]

    duplicate = _signed_whatsapp_post(client, payload)

    assert duplicate.status_code == 200
    assert duplicate.get_json()["status"] == "duplicate_ignored"
    assert initial_send.call_count == 1

    monkeypatch.setattr(outbox_service, "SessionLocal", isolated_app_db)
    worker_send = MagicMock(
        return_value={
            "ok": False,
            "error": "whatsapp_transport_error",
            "reason": "ConnectError",
        }
    )
    monkeypatch.setattr(outbox_service, "send_buttons", worker_send)

    assert outbox_service.process_job(job_id) is False
    db = isolated_app_db()
    try:
        job = db.get(OutboxJob, job_id)
        assert job.status == outbox_service.PENDING
        assert job.attempts == 1
        assert "body" in json.loads(job.payload_json)
        job.available_at = outbox_service._utc_now() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    worker_send.return_value = {"ok": True, "messages": [{"id": "accepted"}]}
    assert outbox_service.process_job(job_id) is True

    db = isolated_app_db()
    try:
        event = (
            db.query(InboundMessageEvent)
            .filter_by(message_id="wamid.committed-delivery-retry")
            .one()
        )
        job = db.get(OutboxJob, job_id)
        terminal_payload = json.loads(job.payload_json)
        assert event.status == "DONE"
        assert event.attempts == 1
        assert job.status == outbox_service.COMPLETED
        assert terminal_payload == {
            "_delivery": {"whatsapp_conversation_delivery": True}
        }
    finally:
        db.close()
    assert worker_send.call_count == 2


def test_ambiguous_delivery_is_not_retried_or_reinterpreted(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    deferred_threads,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    user_id = _create_user(isolated_app_db, flow_state=app_module.NORMAL)
    payload = _whatsapp_payload(
        message_id="wamid.ambiguous-delivery",
        interactive_id=app_module.MORE_MENU_IDS["language"],
    )
    ambiguous_send = MagicMock(
        return_value={
            "ok": False,
            "error": "whatsapp_transport_error",
            "reason": "ReadTimeout",
        }
    )
    monkeypatch.setattr(app_module, "_wa_send_buttons", ambiguous_send)

    first = _signed_whatsapp_post(client, payload)
    duplicate = _signed_whatsapp_post(client, payload)

    assert first.status_code == 200
    assert first.get_json()["status"] == "delivery_not_retried"
    assert duplicate.status_code == 200
    assert duplicate.get_json()["status"] == "duplicate_ignored"
    assert ambiguous_send.call_count == 1
    assert deferred_threads == []

    db = isolated_app_db()
    try:
        user = db.get(User, user_id)
        event = (
            db.query(InboundMessageEvent)
            .filter_by(message_id="wamid.ambiguous-delivery")
            .one()
        )
        assert user.flow_state == app_module.ASK_LANGUAGE
        assert event.status == "DONE"
        assert event.attempts == 1
        assert event.last_error.startswith(
            "OutboundDeliveryAmbiguousNotRetried:"
        )
        assert db.query(OutboxJob).count() == 0
    finally:
        db.close()


def test_batched_messages_are_drained_safely_across_provider_retry(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
    transport_spies,
):
    _secure_whatsapp_route(monkeypatch, app_module)
    _create_user(isolated_app_db, flow_state=app_module.NORMAL)
    payload = _whatsapp_payload(message_id="wamid.batch-1", text="menu")
    messages = payload["entry"][0]["changes"][0]["value"]["messages"]
    messages.append(
        {
            "from": "919911112222",
            "id": "wamid.batch-2",
            "type": "text",
            "text": {"body": "menu"},
        }
    )

    first = _signed_whatsapp_post(client, payload)

    assert first.status_code == 503
    db = isolated_app_db()
    try:
        claimed = {
            row[0]
            for row in (
                db.query(InboundMessageEvent.message_id)
                .filter(InboundMessageEvent.status == "DONE")
                .all()
            )
        }
        assert claimed == {"wamid.batch-1"}
    finally:
        db.close()

    second = _signed_whatsapp_post(client, payload)
    assert second.status_code == 200
    assert transport_spies["home"].call_count == 2

    db = isolated_app_db()
    try:
        claimed = {
            row[0]
            for row in (
                db.query(InboundMessageEvent.message_id)
                .filter(InboundMessageEvent.status == "DONE")
                .all()
            )
        }
        assert claimed == {"wamid.batch-1", "wamid.batch-2"}
    finally:
        db.close()
