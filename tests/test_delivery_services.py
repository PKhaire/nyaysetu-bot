from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    Booking,
    BookingStatus,
    OutboxJob,
    PaymentReconciliation,
)
from services import (
    outbox_service,
    receipt_service,
    whatsapp_service,
)


@pytest.fixture
def delivery_db(monkeypatch):
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
    monkeypatch.setattr(receipt_service, "SessionLocal", testing_session)
    monkeypatch.setattr(whatsapp_service, "SessionLocal", testing_session)

    session = testing_session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _paid_booking(db, suffix: str = "1") -> Booking:
    booking = Booking(
        whatsapp_id=f"91900000000{suffix}",
        name="Receipt User",
        phone=f"91900000000{suffix}",
        state_name="Maharashtra",
        district_name="Pune",
        category="Family",
        subcategory="Divorce",
        date=date(2026, 8, 1),
        slot_code="3_4",
        slot_readable="3:00 PM - 4:00 PM",
        amount=499,
        status=BookingStatus.PAID,
        payment_token=f"delivery-token-{suffix}",
        razorpay_payment_link_id=f"plink-delivery-{suffix}",
        razorpay_payment_id=f"pay-delivery-{suffix}",
        payment_processed=True,
    )
    db.add(booking)
    db.commit()
    return booking


def _enqueue(db, kind: str, booking: Booking) -> int:
    job = outbox_service.enqueue_job(
        db,
        kind,
        {"booking_id": booking.id},
    )
    db.commit()
    return job.id


def test_structured_whatsapp_failure_is_retried(monkeypatch, delivery_db):
    booking = _paid_booking(delivery_db)
    job_id = _enqueue(delivery_db, "payment_success_message", booking)
    monkeypatch.setattr(
        outbox_service,
        "send_payment_success_message",
        lambda _booking: {"ok": False, "error": "provider_unavailable"},
    )

    assert outbox_service.process_job(job_id) is False

    delivery_db.expire_all()
    job = delivery_db.get(OutboxJob, job_id)
    assert job.status == outbox_service.PENDING
    assert job.attempts == 1
    assert job.last_error == "payment_success_message_not_sent"


def test_open_payment_review_alert_is_delivered_once(
    monkeypatch,
    delivery_db,
):
    reconciliation = PaymentReconciliation(
        provider="razorpay",
        payment_id="pay_review_delivery",
        reason="PROVIDER_AMOUNT_MISMATCH",
        status="OPEN",
    )
    delivery_db.add(reconciliation)
    delivery_db.flush()
    job = outbox_service.enqueue_job(
        delivery_db,
        "payment_reconciliation_alert",
        {"payment_reconciliation_id": reconciliation.id},
    )
    delivery_db.commit()
    email_send = MagicMock(return_value=True)
    monkeypatch.setattr(
        outbox_service,
        "send_payment_reconciliation_email",
        email_send,
    )

    assert outbox_service.process_job(job.id) is True

    delivery_db.expire_all()
    assert delivery_db.get(OutboxJob, job.id).status == outbox_service.COMPLETED
    email_send.assert_called_once()


def test_resolved_payment_review_alert_completes_without_sending(
    monkeypatch,
    delivery_db,
):
    reconciliation = PaymentReconciliation(
        provider="razorpay",
        payment_id="pay_resolved_delivery",
        reason="OPERATOR_RESOLVED",
        status="RESOLVED",
    )
    delivery_db.add(reconciliation)
    delivery_db.flush()
    job = outbox_service.enqueue_job(
        delivery_db,
        "payment_reconciliation_alert",
        {"payment_reconciliation_id": reconciliation.id},
    )
    delivery_db.commit()
    email_send = MagicMock(return_value=True)
    monkeypatch.setattr(
        outbox_service,
        "send_payment_reconciliation_email",
        email_send,
    )

    assert outbox_service.process_job(job.id) is True

    delivery_db.expire_all()
    assert delivery_db.get(OutboxJob, job.id).status == outbox_service.COMPLETED
    email_send.assert_not_called()


def test_composite_retry_does_not_repeat_completed_whatsapp_step(
    monkeypatch,
    delivery_db,
):
    booking = _paid_booking(delivery_db)
    job_id = _enqueue(delivery_db, "payment_followup", booking)
    whatsapp_send = MagicMock(return_value={"ok": True})
    email_send = MagicMock(return_value=False)
    monkeypatch.setattr(
        outbox_service,
        "send_payment_success_message",
        whatsapp_send,
    )
    monkeypatch.setattr(
        outbox_service,
        "send_booking_notification_email",
        email_send,
    )
    monkeypatch.setattr(outbox_service, "AUTO_SEND_RECEIPTS", False)

    assert outbox_service.process_job(job_id) is False
    delivery_db.expire_all()
    job = delivery_db.get(OutboxJob, job_id)
    progress = json.loads(job.payload_json)["_delivery"]
    assert progress["payment_success_message"] is True

    job.available_at = outbox_service._utc_now() - timedelta(seconds=1)
    delivery_db.commit()
    email_send.return_value = True

    assert outbox_service.process_job(job_id) is True
    assert whatsapp_send.call_count == 1
    assert email_send.call_count == 2


def test_failed_receipt_delivery_removes_private_file(
    monkeypatch,
    delivery_db,
    tmp_path,
):
    booking = _paid_booking(delivery_db)
    job_id = _enqueue(delivery_db, "payment_receipt", booking)
    receipt_path = tmp_path / "temporary-receipt.pdf"
    receipt_path.write_bytes(b"private receipt")

    monkeypatch.setattr(outbox_service, "AUTO_SEND_RECEIPTS", True)
    monkeypatch.setattr(
        outbox_service,
        "generate_pdf_receipt",
        lambda _booking: str(receipt_path),
    )
    receipt_send = MagicMock(
        return_value={"ok": False, "error": "transport_error"}
    )
    monkeypatch.setattr(
        outbox_service,
        "send_payment_receipt_pdf",
        receipt_send,
    )

    assert outbox_service.process_job(job_id) is False
    assert receipt_path.exists() is False
    receipt_send.assert_called_once_with(
        booking.whatsapp_id,
        str(receipt_path),
        booking_id=booking.id,
    )

    delivery_db.expire_all()
    job = delivery_db.get(OutboxJob, job_id)
    assert job.status == outbox_service.PENDING
    assert job.last_error == "payment_receipt_not_sent"


def test_receipt_delivery_tracks_only_explicit_booking(
    monkeypatch,
    delivery_db,
    tmp_path,
):
    first_booking = _paid_booking(delivery_db, "receipt-first")
    second_booking = _paid_booking(delivery_db, "receipt-second")
    second_booking.whatsapp_id = first_booking.whatsapp_id
    second_booking.phone = first_booking.phone
    delivery_db.commit()

    receipt_path = tmp_path / "explicit-booking-receipt.pdf"
    receipt_path.write_bytes(b"private receipt")
    monkeypatch.setattr(
        whatsapp_service,
        "send_document",
        MagicMock(return_value={"ok": True, "messages": [{"id": "accepted"}]}),
    )

    result = whatsapp_service.send_payment_receipt_pdf(
        first_booking.whatsapp_id,
        str(receipt_path),
        booking_id=first_booking.id,
    )

    assert result["ok"] is True
    assert result["receipt_status_recorded"] is True
    delivery_db.expire_all()
    assert delivery_db.get(Booking, first_booking.id).receipt_sent is True
    assert delivery_db.get(Booking, second_booking.id).receipt_sent is False


def test_outbox_health_separates_ready_and_deferred_work(delivery_db):
    now = outbox_service._utc_now()
    delivery_db.add_all(
        [
            OutboxJob(
                kind="payment_success_message",
                payload_json="{}",
                status=outbox_service.PENDING,
                available_at=now - timedelta(seconds=1),
                created_at=now - timedelta(minutes=2),
            ),
            OutboxJob(
                kind="payment_success_message",
                payload_json="{}",
                status=outbox_service.PENDING,
                available_at=now + timedelta(minutes=1),
                created_at=now - timedelta(minutes=1),
            ),
            OutboxJob(
                kind="payment_success_message",
                payload_json="{}",
                status=outbox_service.RUNNING,
                available_at=now,
                created_at=now - timedelta(seconds=30),
            ),
            OutboxJob(
                kind="payment_success_message",
                payload_json="{}",
                status=outbox_service.DEAD,
                available_at=now,
                created_at=now - timedelta(minutes=3),
            ),
            OutboxJob(
                kind="payment_success_message",
                payload_json="{}",
                status=outbox_service.COMPLETED,
                available_at=now,
                created_at=now - timedelta(minutes=10),
            ),
        ]
    )
    delivery_db.commit()

    health = outbox_service.get_outbox_health()

    assert health["backlog_count"] == 4
    assert health["ready_count"] == 1
    assert health["deferred_count"] == 1
    assert health["running_count"] == 1
    assert health["dead_count"] == 1
    assert health["oldest_age_seconds"] >= 179


def test_generated_receipts_use_unique_system_temp_files(delivery_db):
    booking = _paid_booking(delivery_db)
    paths = []
    try:
        first_path = receipt_service.generate_pdf_receipt(booking)
        paths.append(first_path)
        second_path = receipt_service.generate_pdf_receipt(booking)
        paths.append(second_path)

        assert first_path != second_path
        assert Path(first_path).parent == Path(tempfile.gettempdir())
        assert Path(second_path).parent == Path(tempfile.gettempdir())
        assert Path(first_path).name.startswith("nyaysetu-receipt-")
        assert Path(first_path).is_file()
        if os.name != "nt":
            assert oct(os.stat(first_path).st_mode & 0o777) == "0o600"

        delivery_db.expire_all()
        assert delivery_db.get(Booking, booking.id).receipt_generated is True
    finally:
        for path in paths:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
