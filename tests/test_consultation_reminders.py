from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from jobs import consultation_reminders as reminder_job
from models import (
    Booking,
    BookingFulfillment,
    BookingStatus,
    OutboxJob,
    User,
)
from services import (
    consultation_reminder_policy as reminder_policy,
    consultation_reminder_service as reminder_service,
    outbox_service,
    whatsapp_service,
)


NOW = datetime(2026, 8, 3, 4, 30)


def _empty_templates() -> dict[str, dict[str, dict[str, str]]]:
    return {
        reminder_kind: {
            language: {"name": "", "language_code": ""}
            for language in ("en", "hi", "mr")
        }
        for reminder_kind in ("24h", "2h")
    }


def _configured_templates() -> dict[str, dict[str, dict[str, str]]]:
    values = _empty_templates()
    values["24h"]["en"] = {
        "name": "consultation_reminder_24h_en",
        "language_code": "en_US",
    }
    values["2h"]["en"] = {
        "name": "consultation_reminder_2h_en",
        "language_code": "en_US",
    }
    values["2h"]["hi"] = {
        "name": "consultation_reminder_2h_hi",
        "language_code": "hi",
    }
    return values


@pytest.fixture
def reminder_db(monkeypatch):
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
    monkeypatch.setattr(outbox_service, "SessionLocal", testing_session)
    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        _empty_templates(),
    )
    monkeypatch.setattr(
        reminder_service,
        "CONSULTATION_REMINDER_CATCHUP_MINUTES",
        30,
    )
    monkeypatch.setattr(
        outbox_service,
        "CONSULTATION_REMINDER_CATCHUP_MINUTES",
        30,
    )

    session = testing_session()
    try:
        yield session, testing_session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_fulfillment(
    db,
    *,
    suffix: int,
    scheduled_start_at: datetime,
    booking_status: BookingStatus = BookingStatus.PAID,
    fulfillment_status: str = "CONFIRMED",
    language: str = "English",
) -> tuple[Booking, BookingFulfillment]:
    whatsapp_id = f"91987654{suffix:04d}"
    db.add(
        User(
            whatsapp_id=whatsapp_id,
            language=language,
            case_id=f"NS-R{suffix:04d}",
        )
    )
    booking = Booking(
        whatsapp_id=whatsapp_id,
        name="Reminder User",
        phone=whatsapp_id,
        state_name="Maharashtra",
        district_name="Pune",
        category="Family",
        subcategory="Consultation",
        date=date(2026, 8, 4),
        slot_code="10_11",
        slot_readable="10:00 AM - 11:00 AM",
        amount=499,
        status=booking_status,
        payment_token=f"reminder-token-{suffix}",
        payment_processed=booking_status == BookingStatus.PAID,
    )
    db.add(booking)
    db.flush()
    fulfillment = BookingFulfillment(
        booking_id=booking.id,
        status=fulfillment_status,
        scheduled_start_at=scheduled_start_at,
    )
    db.add(fulfillment)
    db.commit()
    return booking, fulfillment


def _schedule(factory, **overrides):
    return reminder_service.schedule_consultation_reminders(
        now=NOW,
        session_factory=factory,
        **overrides,
    )


def test_reminders_are_disabled_until_a_complete_template_pair_exists(
    monkeypatch,
    reminder_db,
):
    db, factory = reminder_db
    _seed_fulfillment(
        db,
        suffix=1,
        scheduled_start_at=NOW + timedelta(hours=2),
    )

    report = _schedule(factory)

    assert report["enabled"] is False
    assert report["enqueued"] == 0
    assert db.query(OutboxJob).count() == 0

    partial = _empty_templates()
    partial["2h"]["en"]["name"] = "not_enabled_without_language"
    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        partial,
    )
    report = _schedule(factory)
    assert report["enabled"] is False
    assert db.query(OutboxJob).count() == 0


def test_scheduler_enqueues_due_paid_active_fulfillments_once(
    monkeypatch,
    reminder_db,
):
    db, factory = reminder_db
    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        _configured_templates(),
    )
    _seed_fulfillment(
        db,
        suffix=10,
        scheduled_start_at=NOW + timedelta(hours=24),
    )
    _seed_fulfillment(
        db,
        suffix=11,
        scheduled_start_at=NOW + timedelta(hours=2),
        language="Hindi",
    )
    _seed_fulfillment(
        db,
        suffix=12,
        scheduled_start_at=NOW + timedelta(hours=2),
        booking_status=BookingStatus.PENDING,
    )
    _seed_fulfillment(
        db,
        suffix=13,
        scheduled_start_at=NOW + timedelta(hours=2),
        fulfillment_status="REFUND_REVIEW",
    )

    first = _schedule(factory)
    second = _schedule(factory)

    assert first["enqueued"] == 2
    assert first["scanned"] == 2
    assert second["enqueued"] == 0
    assert second["duplicates"] == 2

    jobs = db.query(OutboxJob).order_by(OutboxJob.id).all()
    assert len(jobs) == 2
    assert {job.kind for job in jobs} == {"consultation_reminder"}
    payloads = [json.loads(job.payload_json) for job in jobs]
    assert {payload["reminder_kind"] for payload in payloads} == {
        "2h",
        "24h",
    }
    assert all("template" not in payload for payload in payloads)
    assert len({job.dedupe_key for job in jobs}) == 2


def test_duplicate_rows_do_not_starve_later_work_in_a_bounded_batch(
    monkeypatch,
    reminder_db,
):
    db, factory = reminder_db
    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        _configured_templates(),
    )
    for suffix in range(20, 23):
        _seed_fulfillment(
            db,
            suffix=suffix,
            scheduled_start_at=NOW + timedelta(hours=2),
        )

    first = _schedule(factory, batch_size=2)
    second = _schedule(factory, batch_size=2)

    assert first["enqueued"] == 2
    assert first["more_remaining"] is True
    assert second["duplicates"] == 2
    assert second["enqueued"] == 1
    assert db.query(OutboxJob).count() == 3


def test_dry_run_and_reschedule_use_distinct_dedupe_keys(
    monkeypatch,
    reminder_db,
):
    db, factory = reminder_db
    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        _configured_templates(),
    )
    _, fulfillment = _seed_fulfillment(
        db,
        suffix=30,
        scheduled_start_at=NOW + timedelta(hours=24),
    )

    dry_run = _schedule(factory, dry_run=True)
    assert dry_run["would_enqueue"] == 1
    assert db.query(OutboxJob).count() == 0

    assert _schedule(factory)["enqueued"] == 1
    fulfillment.scheduled_start_at = NOW + timedelta(hours=2)
    db.commit()
    assert _schedule(factory)["enqueued"] == 1
    assert db.query(OutboxJob).count() == 2


def test_outbox_sends_only_the_current_approved_language_template(
    monkeypatch,
    reminder_db,
):
    db, factory = reminder_db
    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        _configured_templates(),
    )
    booking, _ = _seed_fulfillment(
        db,
        suffix=40,
        scheduled_start_at=NOW + timedelta(hours=2),
        language="Hindi",
    )
    assert _schedule(factory)["enqueued"] == 1
    job_id = db.query(OutboxJob.id).scalar()

    approved_send = MagicMock(return_value={"ok": True})
    free_form_send = MagicMock()
    monkeypatch.setattr(
        outbox_service,
        "send_approved_template",
        approved_send,
    )
    monkeypatch.setattr(whatsapp_service, "send_text", free_form_send)
    monkeypatch.setattr(outbox_service, "_utc_now", lambda: NOW)

    assert outbox_service.process_job(job_id) is True
    assert outbox_service.process_job(job_id) is False

    approved_send.assert_called_once()
    args, kwargs = approved_send.call_args
    assert args == (
        booking.whatsapp_id,
        "consultation_reminder_2h_hi",
        "hi",
    )
    parameters = kwargs["components"][0]["parameters"]
    assert parameters == [
        {"type": "text", "text": "04 Aug 2026 (Tuesday)"},
        {"type": "text", "text": "10:00 AM - 11:00 AM"},
    ]
    free_form_send.assert_not_called()

    db.expire_all()
    completed = db.get(OutboxJob, job_id)
    assert completed.status == outbox_service.COMPLETED
    assert json.loads(completed.payload_json)["_delivery"][
        "consultation_reminder"
    ] is True


def test_disabling_template_after_enqueue_is_a_permanent_no_send(
    monkeypatch,
    reminder_db,
):
    db, factory = reminder_db
    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        _configured_templates(),
    )
    _seed_fulfillment(
        db,
        suffix=50,
        scheduled_start_at=NOW + timedelta(hours=2),
    )
    assert _schedule(factory)["enqueued"] == 1
    job_id = db.query(OutboxJob.id).scalar()

    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        _empty_templates(),
    )
    approved_send = MagicMock(return_value={"ok": True})
    monkeypatch.setattr(
        outbox_service,
        "send_approved_template",
        approved_send,
    )
    monkeypatch.setattr(outbox_service, "_utc_now", lambda: NOW)

    assert outbox_service.process_job(job_id) is False
    approved_send.assert_not_called()

    db.expire_all()
    failed = db.get(OutboxJob, job_id)
    assert failed.status == outbox_service.DEAD
    assert (
        failed.last_error
        == "consultation_reminder_template_not_configured"
    )


def test_ambiguous_transport_result_is_not_automatically_retried(
    monkeypatch,
    reminder_db,
):
    db, factory = reminder_db
    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        _configured_templates(),
    )
    _seed_fulfillment(
        db,
        suffix=55,
        scheduled_start_at=NOW + timedelta(hours=2),
    )
    assert _schedule(factory)["enqueued"] == 1
    job_id = db.query(OutboxJob.id).scalar()

    approved_send = MagicMock(
        return_value={
            "ok": False,
            "error": "whatsapp_transport_error",
            "reason": "ReadTimeout",
        }
    )
    monkeypatch.setattr(
        outbox_service,
        "send_approved_template",
        approved_send,
    )
    monkeypatch.setattr(outbox_service, "_utc_now", lambda: NOW)

    assert outbox_service.process_job(job_id) is False
    approved_send.assert_called_once()
    db.expire_all()
    failed = db.get(OutboxJob, job_id)
    assert failed.status == outbox_service.DEAD
    assert failed.last_error == "consultation_reminder_delivery_ambiguous"


@pytest.mark.parametrize(
    ("fulfillment_status", "processing_time"),
    [
        ("REFUND_REVIEW", NOW),
        ("CONFIRMED", NOW + timedelta(minutes=31)),
    ],
)
def test_obsolete_or_stale_reminders_complete_without_sending(
    monkeypatch,
    reminder_db,
    fulfillment_status,
    processing_time,
):
    db, factory = reminder_db
    monkeypatch.setattr(
        reminder_policy,
        "CONSULTATION_REMINDER_TEMPLATES",
        _configured_templates(),
    )
    _, fulfillment = _seed_fulfillment(
        db,
        suffix=60 if fulfillment_status == "REFUND_REVIEW" else 61,
        scheduled_start_at=NOW + timedelta(hours=2),
    )
    assert _schedule(factory)["enqueued"] == 1
    job_id = db.query(OutboxJob.id).scalar()
    fulfillment.status = fulfillment_status
    db.commit()

    approved_send = MagicMock(return_value={"ok": True})
    monkeypatch.setattr(
        outbox_service,
        "send_approved_template",
        approved_send,
    )
    monkeypatch.setattr(
        outbox_service,
        "_utc_now",
        lambda: processing_time,
    )

    assert outbox_service.process_job(job_id) is True
    approved_send.assert_not_called()
    db.expire_all()
    assert db.get(OutboxJob, job_id).status == outbox_service.COMPLETED


def test_approved_template_transport_always_builds_template_payload(
    monkeypatch,
):
    send = MagicMock(return_value={"ok": True})
    monkeypatch.setattr(whatsapp_service, "_send", send)
    components = [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": "04 Aug 2026"}],
        }
    ]

    assert whatsapp_service.send_approved_template(
        "919876543210",
        "consultation_reminder_2h_en",
        "en_US",
        components,
    ) == {"ok": True}

    payload = send.call_args.args[0]
    assert payload["type"] == "template"
    assert "text" not in payload
    assert payload["template"] == {
        "name": "consultation_reminder_2h_en",
        "language": {"code": "en_US"},
        "components": components,
    }


def test_scheduler_command_redacts_failures(monkeypatch, capsys):
    private_message = "database password and user phone"
    monkeypatch.setattr(
        reminder_job,
        "schedule_consultation_reminders",
        MagicMock(side_effect=RuntimeError(private_message)),
    )

    assert reminder_job.main([]) == 1
    output = capsys.readouterr().out
    assert private_message not in output
    assert json.loads(output) == {
        "error": "consultation_reminder_scheduling_failed",
        "error_type": "RuntimeError",
        "ok": False,
    }
