from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import WEBHOOK_EVENT_TTL_DAYS
from db import Base
from jobs import maintenance as maintenance_command
from models import (
    AdminOperator,
    Advocate,
    AnalyticsEvent,
    Booking,
    BookingFulfillment,
    BookingStatus,
    CaseBrief,
    Conversation,
    DocumentAccessEvent,
    DocumentAdvocateAssignment,
    DocumentAnswerRevision,
    DocumentArtifact,
    DocumentCapacityReservation,
    DocumentEvidenceArtifact,
    DocumentLegalHold,
    DocumentOrder,
    Feedback,
    InboundMessageEvent,
    OutboxJob,
    PaymentReconciliation,
    ProcessedMessage,
    SupportRequest,
    User,
    WebhookEvent,
)
from services import maintenance_service
from services.document_artifact_vault import MemoryArtifactVault


@pytest.fixture
def maintenance_db():
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
    try:
        yield testing_session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _booking(
    *,
    suffix: str,
    created_at: datetime,
    status: BookingStatus,
) -> Booking:
    return Booking(
        whatsapp_id=f"91990000{suffix}",
        name=f"Private User {suffix}",
        phone=f"91990000{suffix}",
        state_name="Maharashtra",
        district_name="Pune",
        category="Family",
        subcategory="Other Family Issue",
        date=created_at.date(),
        slot_code="10_11",
        slot_readable="10:00 AM - 11:00 AM",
        amount=499,
        status=status,
        payment_token=f"maintenance-token-{suffix}",
        razorpay_payment_link_id=f"plink-maintenance-{suffix}",
        created_at=created_at,
    )


def _seed_retention_matrix(session_factory, now: datetime) -> dict[str, int]:
    old_webhook_time = now - timedelta(
        days=WEBHOOK_EVENT_TTL_DAYS + 1
    )
    old_processed_time = now - timedelta(
        days=maintenance_service.PROCESSED_MESSAGE_TTL_DAYS + 1
    )
    old_analytics_time = now - timedelta(
        days=maintenance_service.ANALYTICS_EVENT_TTL_DAYS + 1
    )
    old_outbox_time = now - timedelta(
        days=maintenance_service.OUTBOX_COMPLETED_TTL_DAYS + 1
    )
    old_booking_time = now - timedelta(
        minutes=maintenance_service.PAYMENT_LINK_TTL_MINUTES + 1
    )

    db = session_factory()
    try:
        user = User(
            whatsapp_id="919811111111",
            case_id="NS-MAINTENANCE",
            name="Private User",
        )
        db.add(user)
        db.flush()

        support = SupportRequest(
            user_id=user.id,
            case_id=user.case_id,
            message="Private support details must remain",
            sla_due_at=now - timedelta(hours=1),
        )
        support_without_sla = SupportRequest(
            user_id=user.id,
            case_id=user.case_id,
            message="Legacy support details must remain",
            created_at=now
            - timedelta(hours=maintenance_service.SUPPORT_SLA_HOURS + 1),
        )
        feedback = Feedback(
            user_id=user.id,
            rating=5,
            comment="Private feedback must remain",
        )
        conversation = Conversation(
            user_whatsapp_id=user.whatsapp_id,
            direction="user",
            text="Private legal question must remain",
            created_at=old_analytics_time,
        )

        old_pending = _booking(
            suffix="01",
            created_at=old_booking_time,
            status=BookingStatus.PENDING,
        )
        recent_pending = _booking(
            suffix="02",
            created_at=now,
            status=BookingStatus.PENDING,
        )
        paid = _booking(
            suffix="03",
            created_at=old_booking_time,
            status=BookingStatus.PAID,
        )
        db.add_all([old_pending, recent_pending, paid])
        db.flush()
        fulfillment = BookingFulfillment(
            booking_id=paid.id,
            status="UNASSIGNED",
            sla_due_at=now - timedelta(minutes=30),
        )

        old_done_webhook = WebhookEvent(
            provider="razorpay",
            event_id="pay-old-done",
            status="DONE",
            received_at=old_webhook_time,
            processed_at=old_webhook_time,
            expires_at=now - timedelta(seconds=1),
        )
        recent_done_webhook = WebhookEvent(
            provider="razorpay",
            event_id="pay-recent-done",
            status="DONE",
            received_at=now,
            processed_at=now,
            expires_at=now + timedelta(days=1),
        )
        failed_webhook = WebhookEvent(
            provider="razorpay",
            event_id="pay-failed",
            status="FAILED",
            received_at=old_webhook_time,
            expires_at=now - timedelta(days=1),
        )
        unmatched_webhook = WebhookEvent(
            provider="razorpay",
            event_id="pay-unmatched",
            status="UNMATCHED",
            received_at=old_webhook_time,
            expires_at=now - timedelta(days=1),
        )

        old_done_inbound = InboundMessageEvent(
            message_id="wamid.inbound-old-done",
            status="DONE",
            attempts=1,
            received_at=old_processed_time,
            processed_at=old_processed_time,
            expires_at=now - timedelta(seconds=1),
        )
        recent_done_inbound = InboundMessageEvent(
            message_id="wamid.inbound-recent-done",
            status="DONE",
            attempts=1,
            received_at=now,
            processed_at=now,
            expires_at=now + timedelta(days=1),
        )
        failed_inbound = InboundMessageEvent(
            message_id="wamid.inbound-failed",
            status="FAILED",
            attempts=2,
            received_at=old_processed_time,
            expires_at=now - timedelta(days=1),
        )
        processing_inbound = InboundMessageEvent(
            message_id="wamid.inbound-processing",
            status="PROCESSING",
            attempts=2,
            received_at=old_processed_time,
            lease_expires_at=now - timedelta(hours=1),
            expires_at=now - timedelta(days=1),
        )

        old_message = ProcessedMessage(
            message_id="wamid.old-ambiguous",
            created_at=old_processed_time,
        )
        recent_message = ProcessedMessage(
            message_id="wamid.recent",
            created_at=now,
        )

        old_analytics = AnalyticsEvent(
            event_name="old_event",
            properties_json="{}",
            created_at=old_analytics_time,
        )
        recent_analytics = AnalyticsEvent(
            event_name="recent_event",
            properties_json="{}",
            created_at=now,
        )

        old_completed_outbox = OutboxJob(
            kind="payment_success_message",
            payload_json='{"booking_id":1}',
            status="COMPLETED",
            created_at=old_outbox_time,
            updated_at=old_outbox_time,
        )
        recent_completed_outbox = OutboxJob(
            kind="payment_success_message",
            payload_json='{"booking_id":2}',
            status="COMPLETED",
            created_at=now,
            updated_at=now,
        )
        old_cancelled_outbox = OutboxJob(
            kind="booking_notification",
            payload_json='{"cancelled_reason":"email_notifications_disabled"}',
            status="CANCELLED",
            created_at=old_outbox_time,
            updated_at=old_outbox_time,
        )
        dead_outbox = OutboxJob(
            kind="payment_success_message",
            payload_json='{"booking_id":3}',
            status="DEAD",
            created_at=old_webhook_time,
            updated_at=old_webhook_time,
        )
        failed_outbox = OutboxJob(
            kind="payment_success_message",
            payload_json='{"booking_id":4}',
            status="FAILED",
            created_at=old_webhook_time,
            updated_at=old_webhook_time,
        )
        stale_reconciliation = PaymentReconciliation(
            payment_id="pay-reconciliation-stale",
            payment_link_id="plink-reconciliation-stale",
            reason="UNMATCHED_PAYMENT",
            status="OPEN",
            created_at=now
            - timedelta(
                days=maintenance_service.PAYMENT_RECONCILIATION_LOOKBACK_DAYS
                + 1
            ),
        )
        recent_reconciliation = PaymentReconciliation(
            payment_id="pay-reconciliation-recent",
            payment_link_id="plink-reconciliation-recent",
            reason="AMOUNT_MISMATCH",
            status="OPEN",
            created_at=now,
        )
        resolved_reconciliation = PaymentReconciliation(
            payment_id="pay-reconciliation-resolved",
            payment_link_id="plink-reconciliation-resolved",
            reason="UNMATCHED_PAYMENT",
            status="RESOLVED",
            created_at=old_analytics_time,
            resolved_at=now,
        )

        db.add_all(
            [
                support,
                support_without_sla,
                feedback,
                conversation,
                fulfillment,
                old_done_webhook,
                recent_done_webhook,
                failed_webhook,
                unmatched_webhook,
                old_done_inbound,
                recent_done_inbound,
                failed_inbound,
                processing_inbound,
                old_message,
                recent_message,
                old_analytics,
                recent_analytics,
                old_completed_outbox,
                recent_completed_outbox,
                old_cancelled_outbox,
                dead_outbox,
                failed_outbox,
                stale_reconciliation,
                recent_reconciliation,
                resolved_reconciliation,
            ]
        )
        db.commit()
        return {
            "old_pending": old_pending.id,
            "recent_pending": recent_pending.id,
            "paid": paid.id,
            "old_done_webhook": old_done_webhook.id,
            "recent_done_webhook": recent_done_webhook.id,
            "failed_webhook": failed_webhook.id,
            "unmatched_webhook": unmatched_webhook.id,
            "old_done_inbound": old_done_inbound.id,
            "recent_done_inbound": recent_done_inbound.id,
            "failed_inbound": failed_inbound.id,
            "processing_inbound": processing_inbound.id,
            "old_completed_outbox": old_completed_outbox.id,
            "recent_completed_outbox": recent_completed_outbox.id,
            "old_cancelled_outbox": old_cancelled_outbox.id,
            "dead_outbox": dead_outbox.id,
            "failed_outbox": failed_outbox.id,
            "fulfillment": fulfillment.id,
            "stale_reconciliation": stale_reconciliation.id,
            "recent_reconciliation": recent_reconciliation.id,
            "resolved_reconciliation": resolved_reconciliation.id,
        }
    finally:
        db.close()


def test_dry_run_reports_without_mutation_and_skips_ambiguous_messages(
    maintenance_db,
):
    now = datetime(2026, 7, 29, 12, 0, 0)
    ids = _seed_retention_matrix(maintenance_db, now)

    report = maintenance_service.run_maintenance(
        dry_run=True,
        batch_size=25,
        now=now,
        session_factory=maintenance_db,
    )

    assert report["ok"] is True
    assert report["dry_run"] is True
    assert report["categories"]["pending_bookings"]["would_affect"] == 1
    assert report["categories"]["webhook_events"]["would_affect"] == 1
    assert report["categories"]["inbound_message_events"]["would_affect"] == 1
    assert report["categories"]["analytics_events"]["would_affect"] == 1
    assert report["categories"]["completed_outbox_jobs"]["would_affect"] == 2

    processed = report["categories"]["legacy_processed_messages"]
    assert processed["eligible_in_batch"] == 1
    assert processed["affected"] == 0
    assert processed["would_affect"] == 0
    assert processed["skipped"] is True
    assert processed["skip_reason"] == "legacy_claims_are_never_pruned"
    assert (
        report["categories"]["completed_outbox_jobs"]["retention_source"]
        == "OUTBOX_COMPLETED_TTL_DAYS"
    )

    risks = report["operational_risks"]
    assert risks["fulfillment"]["overdue"]["count"] == 1
    assert risks["support"]["overdue"]["count"] == 1
    assert (
        risks["support"]["active_without_sla_beyond_configured_sla"]["count"]
        == 1
    )
    assert risks["payment_reconciliation"]["open"]["count"] == 2
    assert (
        risks["payment_reconciliation"]["open_older_than_lookback"]["count"]
        == 1
    )
    assert risks["summary"]["alert_required"] is True
    assert risks["summary"]["financial_evidence_mutated"] is False

    db = maintenance_db()
    try:
        assert db.get(Booking, ids["old_pending"]).status == BookingStatus.PENDING
        assert db.get(WebhookEvent, ids["old_done_webhook"]) is not None
        assert db.get(InboundMessageEvent, ids["old_done_inbound"]) is not None
        assert db.query(AnalyticsEvent).count() == 2
        assert db.get(OutboxJob, ids["old_completed_outbox"]) is not None
        assert db.get(OutboxJob, ids["old_cancelled_outbox"]) is not None
        assert db.query(ProcessedMessage).count() == 2
    finally:
        db.close()


def test_execution_prunes_only_safe_terminal_records(maintenance_db):
    now = datetime(2026, 7, 29, 12, 0, 0)
    ids = _seed_retention_matrix(maintenance_db, now)

    report = maintenance_service.run_maintenance(
        batch_size=25,
        now=now,
        session_factory=maintenance_db,
    )

    assert report["categories"]["pending_bookings"]["affected"] == 1
    assert report["categories"]["webhook_events"]["affected"] == 1
    assert report["categories"]["inbound_message_events"]["affected"] == 1
    assert report["categories"]["analytics_events"]["affected"] == 1
    assert report["categories"]["completed_outbox_jobs"]["affected"] == 2
    assert report["categories"]["legacy_processed_messages"]["affected"] == 0

    db = maintenance_db()
    try:
        assert db.get(Booking, ids["old_pending"]).status == BookingStatus.EXPIRED
        assert db.get(Booking, ids["recent_pending"]).status == BookingStatus.PENDING
        assert db.get(Booking, ids["paid"]).status == BookingStatus.PAID
        assert db.query(Booking).count() == 3

        assert db.get(WebhookEvent, ids["old_done_webhook"]) is None
        assert db.get(WebhookEvent, ids["recent_done_webhook"]) is not None
        assert db.get(WebhookEvent, ids["failed_webhook"]) is not None
        assert db.get(WebhookEvent, ids["unmatched_webhook"]) is not None
        assert db.get(InboundMessageEvent, ids["old_done_inbound"]) is None
        assert db.get(InboundMessageEvent, ids["recent_done_inbound"]) is not None
        assert db.get(InboundMessageEvent, ids["failed_inbound"]) is not None
        assert db.get(InboundMessageEvent, ids["processing_inbound"]) is not None

        assert db.query(AnalyticsEvent).count() == 1
        assert db.get(OutboxJob, ids["old_completed_outbox"]) is None
        assert db.get(OutboxJob, ids["old_cancelled_outbox"]) is None
        assert db.get(OutboxJob, ids["recent_completed_outbox"]) is not None
        assert db.get(OutboxJob, ids["dead_outbox"]) is not None
        assert db.get(OutboxJob, ids["failed_outbox"]) is not None

        assert db.query(ProcessedMessage).count() == 2
        assert db.query(User).count() == 1
        assert db.query(SupportRequest).count() == 2
        assert db.query(Feedback).count() == 1
        assert db.query(Conversation).count() == 1
        assert db.get(BookingFulfillment, ids["fulfillment"]) is not None
        assert (
            db.get(PaymentReconciliation, ids["stale_reconciliation"]).status
            == "OPEN"
        )
        assert (
            db.get(PaymentReconciliation, ids["recent_reconciliation"]).status
            == "OPEN"
        )
        assert (
            db.get(PaymentReconciliation, ids["resolved_reconciliation"]).status
            == "RESOLVED"
        )
    finally:
        db.close()


def test_unattached_case_briefs_expire_but_paid_booking_brief_is_preserved(
    maintenance_db,
):
    now = datetime(2026, 8, 18, 12, 0, 0)
    expired_at = now - timedelta(
        days=maintenance_service.CASE_BRIEF_UNATTACHED_TTL_DAYS + 1
    )
    db = maintenance_db()
    try:
        user = User(
            whatsapp_id="919822222222",
            case_id="NS-BRIEF-RETENTION",
            name="Private Client",
        )
        paid = _booking(
            suffix="44",
            created_at=expired_at,
            status=BookingStatus.PAID,
        )
        db.add_all([user, paid])
        db.flush()
        abandoned = CaseBrief(
            user_id=user.id,
            status="CONFIRMED",
            issue_summary="Sensitive abandoned narrative",
            created_at=expired_at,
            updated_at=expired_at,
        )
        attached = CaseBrief(
            user_id=user.id,
            booking_id=paid.id,
            status="CONFIRMED",
            issue_summary="Paid consultation preparation",
            created_at=expired_at,
            updated_at=expired_at,
        )
        db.add_all([abandoned, attached])
        db.commit()
        abandoned_id = abandoned.id
        attached_id = attached.id
    finally:
        db.close()

    report = maintenance_service.run_maintenance(
        batch_size=25,
        now=now,
        session_factory=maintenance_db,
    )

    assert report["categories"]["unattached_case_briefs"]["affected"] == 1
    db = maintenance_db()
    try:
        assert db.get(CaseBrief, abandoned_id) is None
        assert db.get(CaseBrief, attached_id) is not None
    finally:
        db.close()


def test_each_category_is_bounded_and_reports_more_work(maintenance_db):
    now = datetime(2026, 7, 29, 12, 0, 0)
    old = now - timedelta(
        days=maintenance_service.ANALYTICS_EVENT_TTL_DAYS + 1
    )
    db = maintenance_db()
    try:
        db.add_all(
            AnalyticsEvent(
                event_name=f"old_{index}",
                properties_json="{}",
                created_at=old - timedelta(seconds=index),
            )
            for index in range(3)
        )
        db.commit()
    finally:
        db.close()

    first = maintenance_service.run_maintenance(
        batch_size=2,
        now=now,
        session_factory=maintenance_db,
    )
    assert first["categories"]["analytics_events"]["affected"] == 2
    assert first["categories"]["analytics_events"]["more_remaining"] is True

    second = maintenance_service.run_maintenance(
        batch_size=2,
        now=now,
        session_factory=maintenance_db,
    )
    assert second["categories"]["analytics_events"]["affected"] == 1
    assert second["categories"]["analytics_events"]["more_remaining"] is False


def test_document_studio_retention_redacts_unpaid_drafts_and_deletes_objects(
    maintenance_db,
):
    now = datetime(2026, 8, 27, 12, 0, 0)
    old = now - timedelta(
        days=maintenance_service.DOCUMENT_STUDIO_DRAFT_TTL_DAYS + 1
    )
    vault = MemoryArtifactVault()
    content_hash = "a" * 64
    object_key = (
        "document-studio/DS-RETENTION01/1/"
        "final_pdf-aaaaaaaaaaaaaaaa.pdf"
    )
    vault.objects[object_key] = b"private final bytes"

    db = maintenance_db()
    try:
        user = User(
            whatsapp_id="919833333333",
            case_id="NS-DOC-RETENTION",
        )
        db.add(user)
        db.flush()
        unpaid = DocumentOrder(
            public_ref="DS-RETENTION00",
            user_id=user.id,
            product_code=(
                "mh_residential_leave_licence_11m_self_service"
            ),
            template_version="mh-ll-11m-self-service-2026-08-v1",
            state="DRAFTING",
            current_step="licensee_full_name",
            draft_answers_json='{"private":"must be redacted"}',
            output_classification="SELF_SERVICE_DRAFT",
            uat_only=False,
            payment_processed=False,
            created_at=old,
            updated_at=old,
        )
        paid = DocumentOrder(
            public_ref="DS-RETENTION01",
            user_id=user.id,
            product_code=(
                "mh_residential_leave_licence_11m_self_service"
            ),
            template_version="mh-ll-11m-self-service-2026-08-v1",
            state="FINAL_READY",
            current_step="complete",
            draft_answers_json='{"paid":"evidence retained"}',
            output_classification="SELF_SERVICE_DRAFT",
            uat_only=False,
            payment_processed=True,
            created_at=old,
            updated_at=old,
        )
        db.add_all([unpaid, paid])
        db.flush()
        reservation = DocumentCapacityReservation(
            document_order_id=unpaid.id,
            business_date=old.date(),
            capacity_limit=10,
            status="RESERVED",
            reserved_at=old,
            updated_at=old,
        )
        db.add(reservation)
        db.add(
            DocumentAnswerRevision(
                document_order_id=unpaid.id,
                revision_number=1,
                schema_version="questionnaire-2026-08-v1",
                answers_json='{"private":"must be deleted"}',
                content_hash="b" * 64,
                created_at=old,
            )
        )
        artifact = DocumentArtifact(
            public_ref="DA-RETENTION01",
            document_order_id=paid.id,
            revision_number=1,
            artifact_kind="FINAL_PDF",
            state="AVAILABLE",
            storage_provider="S3",
            bucket=vault.bucket,
            object_key=object_key,
            content_type="application/pdf",
            size_bytes=len(vault.objects[object_key]),
            content_hash=content_hash,
            manifest_hash="c" * 64,
            renderer_version="nyaysetu-renderer-2026-08-v1",
            expires_at=now - timedelta(seconds=1),
            created_at=old,
        )
        db.add(artifact)
        db.commit()
        unpaid_id = unpaid.id
        paid_id = paid.id
        artifact_id = artifact.id
        reservation_id = reservation.id
    finally:
        db.close()

    report = maintenance_service.run_maintenance(
        batch_size=25,
        now=now,
        session_factory=maintenance_db,
        artifact_vault_factory=lambda: vault,
    )

    assert report["categories"]["document_studio_unpaid_drafts"] == {
        "action": "expire_and_redact",
        "retention_source": "DOCUMENT_STUDIO_DRAFT_TTL_DAYS",
        "eligible_in_batch": 1,
        "more_remaining": False,
        "affected": 1,
        "would_affect": 0,
        "skipped": False,
        "skip_reason": None,
    }
    assert report["categories"]["document_studio_expired_artifacts"][
        "affected"
    ] == 1
    assert object_key not in vault.objects

    db = maintenance_db()
    try:
        expired_order = db.get(DocumentOrder, unpaid_id)
        assert expired_order.state == "EXPIRED"
        assert expired_order.draft_answers_json == "{}"
        assert expired_order.active_revision_number is None
        released_reservation = db.get(
            DocumentCapacityReservation,
            reservation_id,
        )
        assert released_reservation.status == "RELEASED"
        assert released_reservation.release_reason == (
            "DRAFT_RETENTION_EXPIRED"
        )
        assert (
            db.query(DocumentAnswerRevision)
            .filter(DocumentAnswerRevision.document_order_id == unpaid_id)
            .count()
            == 0
        )
        assert db.get(DocumentOrder, paid_id).state == "FINAL_READY"
        deleted_artifact = db.get(DocumentArtifact, artifact_id)
        assert deleted_artifact.state == "DELETED"
        assert deleted_artifact.deleted_at == now
        access = db.query(DocumentAccessEvent).one()
        assert access.action == "ARTIFACT_DELETE"
        assert access.reason_code == "RETENTION_EXPIRED"
    finally:
        db.close()


def test_legal_hold_preserves_expired_notice_artifacts_and_evidence(
    maintenance_db,
):
    now = datetime(2026, 9, 10, 12, 0, 0)
    vault = MemoryArtifactVault()
    artifact_key = "document-studio/DS-HOLD01/1/issued.pdf"
    evidence_key = "document-evidence/DS-HOLD01/DE-HOLD01/cheque.pdf"
    vault.objects[artifact_key] = b"synthetic issued notice"
    vault.objects[evidence_key] = b"synthetic cheque evidence"

    db = maintenance_db()
    try:
        user = User(
            whatsapp_id="phase-c-held-client",
            case_id="NS-PHASEC-HOLD",
        )
        admin = AdminOperator(
            operator_id="retention-admin@example.com",
            display_name="Retention Administrator",
            role="ADMIN",
            password_hash="test",
            totp_secret_ciphertext="test",
            active=True,
            mfa_enrolled_at=now,
        )
        db.add_all([user, admin])
        db.flush()
        order = DocumentOrder(
            public_ref="DS-HOLD01",
            user_id=user.id,
            product_code="synthetic_advocate_notice",
            template_version="synthetic-notice-v1",
            state="ISSUED",
            current_step="issued",
            output_classification="ADVOCATE_ISSUED_NOTICE",
            payment_processed=True,
            active_revision_number=1,
        )
        db.add(order)
        db.flush()
        artifact = DocumentArtifact(
            public_ref="DA-HOLD01",
            document_order_id=order.id,
            revision_number=1,
            artifact_kind="ISSUED_PDF",
            state="AVAILABLE",
            storage_provider="MEMORY",
            bucket=vault.bucket,
            object_key=artifact_key,
            content_type="application/pdf",
            size_bytes=len(vault.objects[artifact_key]),
            content_hash="a" * 64,
            manifest_hash="b" * 64,
            renderer_version="advocate-offline-upload-v1",
            expires_at=now - timedelta(seconds=1),
        )
        evidence = DocumentEvidenceArtifact(
            public_ref="DE-HOLD01",
            document_order_id=order.id,
            revision_number=1,
            evidence_kind="CHEQUE_FRONT",
            state="AVAILABLE",
            storage_provider="MEMORY",
            bucket=vault.bucket,
            object_key=evidence_key,
            content_type="application/pdf",
            size_bytes=len(vault.objects[evidence_key]),
            content_hash="c" * 64,
            scan_status="CLEAN",
            review_status="ACCEPTED",
            uploaded_by_type="CLIENT",
            uploaded_by_ref=str(user.id),
            expires_at=now - timedelta(seconds=1),
        )
        hold = DocumentLegalHold(
            document_order_id=order.id,
            status="ACTIVE",
            reason_code="SYNTHETIC_DISPUTE",
            authority_statement="Synthetic Phase C retention exercise.",
            opened_by_identity_id=admin.id,
        )
        db.add_all([artifact, evidence, hold])
        db.commit()
        artifact_id = artifact.id
        evidence_id = evidence.id
        hold_id = hold.id
    finally:
        db.close()


    held_report = maintenance_service.run_maintenance(
        batch_size=25,
        now=now,
        session_factory=maintenance_db,
        artifact_vault_factory=lambda: vault,
        evidence_vault_factory=lambda: vault,
    )

    assert held_report["categories"]["document_studio_expired_artifacts"][
        "affected"
    ] == 0
    assert held_report["categories"]["document_studio_expired_evidence"][
        "affected"
    ] == 0
    assert artifact_key in vault.objects
    assert evidence_key in vault.objects

    db = maintenance_db()
    try:
        hold = db.get(DocumentLegalHold, hold_id)
        hold.status = "CLOSED"
        hold.closed_by_identity_id = hold.opened_by_identity_id
        hold.closed_at = now
        hold.closure_reason = "Synthetic retention exercise completed."
        db.commit()
    finally:
        db.close()

    released_report = maintenance_service.run_maintenance(
        batch_size=25,
        now=now,
        session_factory=maintenance_db,
        artifact_vault_factory=lambda: vault,
        evidence_vault_factory=lambda: vault,
    )

    assert released_report["categories"][
        "document_studio_expired_artifacts"
    ]["affected"] == 1
    assert released_report["categories"]["document_studio_expired_evidence"][
        "affected"
    ] == 1
    assert artifact_key not in vault.objects
    assert evidence_key not in vault.objects
    db = maintenance_db()
    try:
        assert db.get(DocumentArtifact, artifact_id).state == "DELETED"
        assert db.get(DocumentEvidenceArtifact, evidence_id).state == "DELETED"
    finally:
        db.close()


def test_overdue_advocate_assignment_is_an_actionable_signal(maintenance_db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    db = maintenance_db()
    try:
        user = User(whatsapp_id="phase-c-sla", case_id="NS-PHASEC-SLA")
        operator = AdminOperator(
            operator_id="sla-operator@example.com",
            display_name="SLA Operator",
            role="OPERATOR",
            password_hash="test",
            totp_secret_ciphertext="test",
            active=True,
            mfa_enrolled_at=now,
        )
        advocate = Advocate(
            name="Synthetic SLA Advocate",
            email="sla-advocate@example.com",
            category="banking",
            district="Mumbai",
            active=True,
            verification_status="VERIFIED",
            verification_ref="synthetic-sla-verification",
            verified_at=now,
            authority_scope_json='{"version":"synthetic-v1"}',
        )
        db.add_all([user, operator, advocate])
        db.flush()
        identity = AdminOperator(
            operator_id="sla-advocate-identity@example.com",
            display_name=advocate.name,
            role="ADVOCATE",
            advocate_id=advocate.id,
            password_hash="test",
            totp_secret_ciphertext="test",
            active=True,
            mfa_enrolled_at=now,
        )
        order = DocumentOrder(
            public_ref="DS-PHASEC-SLA",
            user_id=user.id,
            product_code="synthetic_advocate_notice",
            template_version="synthetic-notice-v1",
            state="ADVOCATE_TRIAGE",
            current_step="advocate_review",
            output_classification="ADVOCATE_ISSUED_NOTICE",
        )
        db.add_all([identity, order])
        db.flush()
        assignment = DocumentAdvocateAssignment(
            document_order_id=order.id,
            advocate_id=advocate.id,
            advocate_identity_id=identity.id,
            assigned_by_operator_id=operator.id,
            status="ASSIGNED",
            conflict_status="PENDING",
            authority_scope_version="synthetic-v1",
            authority_scope_hash="a" * 64,
            authority_scope_json='{"version":"synthetic-v1"}',
            sla_due_at=now - timedelta(minutes=1),
        )
        db.add(assignment)
        db.commit()
        assignment_id = assignment.id
    finally:
        db.close()

    overdue = maintenance_service.run_maintenance(
        dry_run=True,
        now=now,
        session_factory=maintenance_db,
    )

    assert overdue["operational_risks"]["document_notice"] == {
        "overdue_assignments": {
            "count": 1,
            "oldest_at": "2026-09-10T11:59:00Z",
        }
    }
    assert overdue["operational_risks"]["summary"][
        "actionable_signals"
    ] == 1

    db = maintenance_db()
    try:
        db.get(DocumentAdvocateAssignment, assignment_id).status = "ISSUED"
        db.commit()
    finally:
        db.close()
    resolved = maintenance_service.run_maintenance(
        dry_run=True,
        now=now,
        session_factory=maintenance_db,
    )
    assert resolved["operational_risks"]["document_notice"][
        "overdue_assignments"
    ]["count"] == 0

def test_failed_commit_rolls_back_all_categories(maintenance_db):
    now = datetime(2026, 7, 29, 12, 0, 0)
    old = now - timedelta(
        days=maintenance_service.ANALYTICS_EVENT_TTL_DAYS + 1
    )
    seed = maintenance_db()
    try:
        seed.add(
            AnalyticsEvent(
                event_name="must_survive_rollback",
                properties_json="{}",
                created_at=old,
            )
        )
        seed.commit()
    finally:
        seed.close()

    failing_session = maintenance_db()

    def fail_commit():
        raise RuntimeError("database URL with secret must not escape")

    failing_session.commit = fail_commit

    with pytest.raises(maintenance_service.MaintenanceError):
        maintenance_service.run_maintenance(
            now=now,
            session_factory=lambda: failing_session,
        )

    verify = maintenance_db()
    try:
        assert db_event_count(verify, "must_survive_rollback") == 1
    finally:
        verify.close()


def db_event_count(db, event_name: str) -> int:
    return (
        db.query(AnalyticsEvent)
        .filter(AnalyticsEvent.event_name == event_name)
        .count()
    )


def test_command_returns_nonzero_and_redacts_execution_failure(
    monkeypatch,
    capsys,
):
    private_failure = "postgresql://user:private-password@example/db"

    def fail(**_kwargs):
        raise RuntimeError(private_failure)

    monkeypatch.setattr(maintenance_command, "run_maintenance", fail)

    assert maintenance_command.main(["--batch-size", "10"]) == 1
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload == {
        "error": "maintenance_failed",
        "error_type": "RuntimeError",
        "ok": False,
    }
    assert private_failure not in output


def test_command_can_signal_reported_operational_risk(monkeypatch, capsys):
    report = {
        "ok": True,
        "operational_risks": {
            "summary": {
                "alert_required": True,
            }
        },
    }
    monkeypatch.setattr(
        maintenance_command,
        "run_maintenance",
        lambda **_kwargs: report,
    )

    assert maintenance_command.main(["--fail-on-risk"]) == 2
    assert json.loads(capsys.readouterr().out) == report
