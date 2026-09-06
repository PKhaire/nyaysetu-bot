"""Production-safety tests for Document Studio recovery and delivery."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    DocumentAnswerRevision,
    DocumentAuditEvent,
    DocumentOrder,
    OutboxJob,
    User,
    utc_now,
)
from services import (
    document_catalogue,
    document_operations_service,
    outbox_service,
)
from services.document_artifact_vault import MemoryArtifactVault
from services.document_operations_service import (
    enqueue_final_delivery,
    reconcile_document_order,
    reconcile_recent_document_payments,
    request_refund_review,
)
from services.document_release_service import record_approval, release_manifest
from services.document_renderer import golden_answers
from services.document_workflow import WorkflowResult


@pytest.fixture
def operations_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(outbox_service, "SessionLocal", factory)
    monkeypatch.setattr(document_catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(document_catalogue, "DOCUMENT_STUDIO_PRICE_INR", 299)
    monkeypatch.setattr(
        document_catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset({document_catalogue.PRODUCT_CODE}),
    )
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _approval_payload() -> dict:
    from datetime import timedelta

    from models import utc_now

    return {
        **release_manifest(),
        "reviewer_name": "Advocate Test Reviewer",
        "reviewer_enrolment_ref": "BAR-TEST-OPS-1",
        "authority_statement": "Approved exact synthetic operations package.",
        "authenticated_method": "test-authenticated-record",
        "authenticated_at": (utc_now() - timedelta(minutes=1)).isoformat()
        + "Z",
        "next_review_at": (utc_now() + timedelta(days=30)).isoformat() + "Z",
        "decision": "APPROVED",
    }


def _order(db, *, state: str = "PAYMENT_PENDING") -> tuple[DocumentOrder, User]:
    product = document_catalogue.resolve_product()
    user = User(
        whatsapp_id="919900007777",
        case_id="NS-DOC-OPS",
        name="Synthetic Operations User",
    )
    db.add(user)
    db.flush()
    answers = golden_answers()
    answers_json = json.dumps(answers, separators=(",", ":"), sort_keys=True)
    order = DocumentOrder(
        public_ref="DS-OPS123456789",
        user_id=user.id,
        product_code=product.code,
        template_version=product.template_version,
        state=state,
        current_step="review",
        draft_answers_json=answers_json,
        output_classification=product.output_classification,
        consent_version="document-studio-test",
        active_revision_number=1,
        schema_hash=product.schema_hash,
        template_hash=product.template_hash,
        preview_manifest_hash="a" * 64,
        price_minor=29_900,
        currency="INR",
        payment_token="document-ops-token",
        razorpay_payment_link_id="plink_document_ops_1",
        exception_code=("OLD_REVIEW_REASON" if state == "NEEDS_ATTENTION" else None),
        final_available_until=(
            utc_now() + timedelta(days=30)
            if state == "FINAL_AVAILABLE"
            else None
        ),
    )
    db.add(order)
    db.flush()
    db.add(
        DocumentAnswerRevision(
            document_order_id=order.id,
            revision_number=1,
            schema_version="test-schema",
            answers_json=answers_json,
            content_hash=hashlib.sha256(answers_json.encode()).hexdigest(),
        )
    )
    record_approval(db, _approval_payload(), recorded_by="test-operator")
    db.commit()
    return order, user


def _link(order: DocumentOrder, *, status: str = "paid") -> dict:
    payments = []
    if status == "paid":
        payments = [
            {
                "payment_id": "pay_document_ops_1",
                "status": "captured",
                "amount": order.price_minor,
            }
        ]
    return {
        "id": order.razorpay_payment_link_id,
        "entity": "payment_link",
        "status": status,
        "accept_partial": False,
        "amount": order.price_minor,
        "amount_paid": order.price_minor if status == "paid" else 0,
        "currency": "INR",
        "reference_id": order.payment_token,
        "notes": {
            "document_order_ref": order.public_ref,
            "revision_number": str(order.active_revision_number),
            "preview_manifest_hash": order.preview_manifest_hash,
            "product_code": order.product_code,
        },
        "payments": payments,
    }


def _payment(order: DocumentOrder) -> dict:
    return {
        "id": "pay_document_ops_1",
        "entity": "payment",
        "status": "captured",
        "captured": True,
        "amount": order.price_minor,
        "currency": "INR",
        "amount_refunded": 0,
        "refund_status": None,
    }


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _ProviderClient:
    def __init__(self, link: dict, payment: dict | None = None):
        self.link = link
        self.payment = payment
        self.paths = []

    def get(self, path: str):
        self.paths.append(path)
        if path.startswith("/v1/payment_links/"):
            return _Response(self.link)
        if path.startswith("/v1/payments/") and self.payment:
            return _Response(self.payment)
        raise AssertionError(path)


def test_exact_capture_recovers_reviewed_order_once(operations_db):
    db = operations_db()
    try:
        order, _ = _order(db, state="NEEDS_ATTENTION")
        provider = _ProviderClient(_link(order), _payment(order))
        vault = MemoryArtifactVault()

        result = reconcile_document_order(
            db,
            order.id,
            client=provider,
            vault=vault,
        )

        assert result.ok is True
        assert result.outcome == "recovered"
        db.expire_all()
        order = db.get(DocumentOrder, order.id)
        assert order.state == "FINAL_AVAILABLE"
        assert order.payment_processed is True
        assert order.razorpay_payment_id == "pay_document_ops_1"
        assert order.exception_code is None
        assert (
            db.query(OutboxJob)
            .filter(OutboxJob.kind == "document_final_delivery")
            .count()
            == 1
        )

        replay = reconcile_document_order(
            db,
            order.id,
            client=provider,
            vault=vault,
        )
        assert replay.outcome == "already_processed"
        assert len(provider.paths) == 2
        assert db.query(OutboxJob).count() == 1
    finally:
        db.close()


def test_unpaid_link_is_left_pending_without_audit_noise(operations_db):
    db = operations_db()
    try:
        order, _ = _order(db)
        initial_events = db.query(DocumentAuditEvent).count()
        provider = _ProviderClient(_link(order, status="created"))

        result = reconcile_document_order(db, order.id, client=provider)

        assert result.outcome == "not_paid"
        db.expire_all()
        assert db.get(DocumentOrder, order.id).state == "PAYMENT_PENDING"
        assert db.query(DocumentAuditEvent).count() == initial_events
    finally:
        db.close()


def test_mismatched_capture_enters_audited_review(operations_db):
    db = operations_db()
    try:
        order, _ = _order(db)
        link = _link(order)
        link["currency"] = "USD"
        provider = _ProviderClient(link, _payment(order))

        result = reconcile_document_order(db, order.id, client=provider)

        assert result.outcome == "review_required"
        assert result.reason_code == "DOCUMENT_PAYMENT_LINK_CURRENCY_MISMATCH"
        db.expire_all()
        order = db.get(DocumentOrder, order.id)
        assert order.state == "NEEDS_ATTENTION"
        assert order.payment_processed is False
        event = (
            db.query(DocumentAuditEvent)
            .filter(
                DocumentAuditEvent.event_type
                == "DOCUMENT_PAYMENT_REVIEW_REQUIRED"
            )
            .one()
        )
        assert "pay_document_ops_1" not in event.details_json
        assert len(json.loads(event.details_json)["payment_id_hash"]) == 64
    finally:
        db.close()


def test_refund_review_requires_explicit_reason_and_exact_refund(operations_db):
    db = operations_db()
    try:
        order, _ = _order(db, state="NEEDS_ATTENTION")
        rejected = request_refund_review(
            db,
            order,
            actor_ref="ops@example.test",
            reason="short",
        )
        assert rejected.ok is False

        requested = request_refund_review(
            db,
            order,
            actor_ref="ops@example.test",
            reason="Customer payment requires a manual full refund.",
        )
        db.commit()
        assert requested.ok is True
        assert order.state == "REFUND_REVIEW"

        payment = _payment(order)
        payment.update(
            {
                "status": "refunded",
                "captured": False,
                "amount_refunded": order.price_minor,
                "refund_status": "full",
            }
        )
        provider = _ProviderClient(_link(order), payment)
        result = reconcile_document_order(db, order.id, client=provider)

        assert result.outcome == "refund_confirmed"
        db.expire_all()
        assert db.get(DocumentOrder, order.id).state == "REFUNDED"
    finally:
        db.close()


def test_bounded_scan_reports_release_failure_without_accepting_payment(
    monkeypatch,
    operations_db,
):
    db = operations_db()
    try:
        order, _ = _order(db)
        provider = _ProviderClient(_link(order), _payment(order))
        monkeypatch.setattr(
            document_operations_service,
            "recover_verified_payment",
            MagicMock(side_effect=RuntimeError("synthetic storage failure")),
        )

        stats = reconcile_recent_document_payments(
            db,
            client=provider,
            vault=MemoryArtifactVault(),
            limit=1,
        )

        assert stats["checked"] == 1
        assert stats["release_failed"] == 1
        db.expire_all()
        order = db.get(DocumentOrder, order.id)
        assert order.state == "NEEDS_ATTENTION"
        assert order.payment_processed is False
        assert order.exception_code == "DOCUMENT_FINAL_RELEASE_FAILED"
    finally:
        db.close()


def test_final_delivery_keeps_links_out_of_durable_payload(
    monkeypatch,
    operations_db,
):
    db = operations_db()
    try:
        order, user = _order(db, state="FINAL_AVAILABLE")
        order.payment_processed = True
        order.razorpay_payment_id = "pay_document_ops_1"
        job = enqueue_final_delivery(
            db,
            order,
            dedupe_key="document-delivery-test",
        )
        db.commit()
        job_id = job.id
        send = MagicMock(return_value={"ok": True})
        monkeypatch.setattr(outbox_service, "send_text", send)
        monkeypatch.setattr(
            outbox_service,
            "download_links_for_user",
            lambda *_args, **_kwargs: WorkflowResult(
                True,
                "DOWNLOADS_READY",
                {
                    "FINAL_PDF": "https://private.example/fresh.pdf",
                    "FINAL_DOCX": "https://private.example/fresh.docx",
                },
            ),
        )
    finally:
        db.close()

    assert outbox_service.process_job(job_id) is True

    db = operations_db()
    try:
        job = db.get(OutboxJob, job_id)
        assert job.status == "COMPLETED"
        assert "private.example" not in job.payload_json
        assert "document_order_id" not in job.payload_json
        assert json.loads(job.payload_json) == {
            "_delivery": {"document_final_delivery": True}
        }
        sent_to, message = send.call_args.args
        assert sent_to == user.whatsapp_id
        assert "fresh.pdf" in message and "fresh.docx" in message
        assert (
            db.query(DocumentAuditEvent)
            .filter(
                DocumentAuditEvent.event_type
                == "DOCUMENT_FINAL_DELIVERY_ACCEPTED"
            )
            .count()
            == 1
        )
    finally:
        db.close()


def test_retryable_final_delivery_failure_retains_only_order_id(
    monkeypatch,
    operations_db,
):
    db = operations_db()
    try:
        order, _ = _order(db, state="FINAL_AVAILABLE")
        order.payment_processed = True
        order.razorpay_payment_id = "pay_document_ops_1"
        job = enqueue_final_delivery(
            db,
            order,
            dedupe_key="document-delivery-retry-test",
        )
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr(
        outbox_service,
        "download_links_for_user",
        lambda *_args, **_kwargs: WorkflowResult(
            True,
            "DOWNLOADS_READY",
            {
                "FINAL_PDF": "https://private.example/fresh.pdf",
                "FINAL_DOCX": "https://private.example/fresh.docx",
            },
        ),
    )
    monkeypatch.setattr(
        outbox_service,
        "send_text",
        lambda *_args, **_kwargs: {
            "ok": False,
            "error": "whatsapp_transport_error",
            "reason": "ConnectTimeout",
        },
    )

    assert outbox_service.process_job(job_id) is False

    db = operations_db()
    try:
        job = db.get(OutboxJob, job_id)
        assert job.status == "PENDING"
        assert json.loads(job.payload_json) == {
            "document_order_id": order.id
        }
        assert "private.example" not in job.payload_json
    finally:
        db.close()
