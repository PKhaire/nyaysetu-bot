"""Behavior tests for the advocate-issued notice workflow seam."""

from __future__ import annotations

import json
import hashlib
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    AdminOperator,
    Advocate,
    DocumentAccessEvent,
    DocumentAdvocateAssignment,
    DocumentEvidenceArtifact,
    DocumentLegalHold,
    DocumentOrder,
    DocumentQuote,
    OutboxJob,
    User,
    utc_now,
)
from services.advocate_issued_workflow import (
    AcceptQuote,
    ApproveIssuedArtifact,
    AssignAdvocate,
    CloseLegalHold,
    CreateQuote,
    ConfirmNoticeFacts,
    OpenLegalHold,
    RecordConflictCheck,
    RecordMatterDecision,
    RecordDispatch,
    RecordVerifiedPayment,
    RequestPayment,
    IssueEvidenceLink,
    IssueIssuedArtifactLink,
    StoreEvidence,
    SubmitDraftForFactCheck,
    WorkflowActor,
    execute_notice_command,
)
from services.document_evidence_vault import MemoryEvidenceVault
from services.document_artifact_vault import MemoryArtifactVault
from models import DocumentAnswerRevision


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _assigned_notice(db, suffix: str):
    now = utc_now()
    user = User(
        whatsapp_id=f"phase-c-negative-{suffix}",
        case_id=f"NS-PCNEG{suffix}",
    )
    operator = AdminOperator(
        operator_id=f"operator-{suffix}@example.com",
        display_name=f"Operator {suffix}",
        role="OPERATOR",
        password_hash="test",
        totp_secret_ciphertext="test",
        active=True,
        mfa_enrolled_at=now,
    )
    advocate = Advocate(
        name=f"Synthetic Advocate {suffix}",
        email=f"advocate-{suffix}@example.com",
        category="banking",
        district="Mumbai",
        active=True,
        verification_status="VERIFIED",
        verification_ref=f"synthetic-verification-{suffix}",
        verified_at=now,
        authority_scope_json=json.dumps(
            {
                "version": "synthetic-notice-authority-v1",
                "product_codes": ["synthetic_advocate_notice"],
            }
        ),
    )
    db.add_all([user, operator, advocate])
    db.flush()
    identity = AdminOperator(
        operator_id=f"advocate-identity-{suffix}@example.com",
        display_name=advocate.name,
        role="ADVOCATE",
        advocate_id=advocate.id,
        password_hash="test",
        totp_secret_ciphertext="test",
        active=True,
        mfa_enrolled_at=now,
    )
    order = DocumentOrder(
        public_ref=f"DS-PCNEG{suffix}",
        user_id=user.id,
        product_code="synthetic_advocate_notice",
        template_version="synthetic-notice-v1",
        state="ADVOCATE_TRIAGE",
        current_step="advocate_assignment",
        output_classification="ADVOCATE_ISSUED_NOTICE",
        active_revision_number=1,
    )
    db.add_all([identity, order])
    db.flush()
    db.add(
        DocumentAnswerRevision(
            document_order_id=order.id,
            revision_number=1,
            schema_version="synthetic-intake-v1",
            answers_json='{"synthetic":true}',
            content_hash="d" * 64,
        )
    )
    db.commit()
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("OPERATOR", operator.id),
        command=AssignAdvocate(
            advocate_id=advocate.id,
            sla_due_at=now + timedelta(hours=24),
        ),
    ).ok
    return now, user, operator, advocate, identity, order


def _accepted_notice(db, suffix: str):
    now, user, operator, advocate, identity, order = _assigned_notice(
        db, suffix
    )
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=RecordConflictCheck("CLEARED", "NO_CONFLICT_FOUND"),
    ).ok
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=RecordMatterDecision(
            "ACCEPTED",
            1,
            ("SYNTHETIC_SCOPE_CONFIRMED",),
        ),
    ).ok
    return now, user, operator, advocate, identity, order


def test_operator_assigns_only_verified_advocate_with_mfa_identity(db):
    now = utc_now()
    user = User(whatsapp_id="phase-c-client", case_id="NS-PHASEC01")
    operator = AdminOperator(
        operator_id="operations@example.com",
        display_name="Operations User",
        role="OPERATOR",
        password_hash="not-used-by-workflow-test",
        totp_secret_ciphertext="not-used-by-workflow-test",
        active=True,
        mfa_enrolled_at=now,
    )
    advocate = Advocate(
        name="Synthetic Advocate",
        email="advocate@example.com",
        category="banking",
        district="Mumbai",
        active=True,
        verification_status="VERIFIED",
        verification_ref="synthetic-verification-record",
        verified_at=now,
        authority_scope_json=json.dumps(
            {
                "version": "ni138-individual-v1",
                "product_codes": ["synthetic_advocate_notice"],
                "jurisdiction": "India",
            }
        ),
    )
    db.add_all([user, operator, advocate])
    db.flush()
    identity = AdminOperator(
        operator_id="advocate@example.com",
        display_name="Synthetic Advocate",
        role="ADVOCATE",
        advocate_id=advocate.id,
        password_hash="not-used-by-workflow-test",
        totp_secret_ciphertext="not-used-by-workflow-test",
        active=True,
        mfa_enrolled_at=now,
    )
    order = DocumentOrder(
        public_ref="DS-PHASEC01",
        user_id=user.id,
        product_code="synthetic_advocate_notice",
        template_version="synthetic-notice-v1",
        state="ADVOCATE_TRIAGE",
        current_step="advocate_assignment",
        output_classification="ADVOCATE_ISSUED_NOTICE",
    )
    db.add_all([identity, order])
    db.commit()

    result = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("OPERATOR", operator.id),
        command=AssignAdvocate(
            advocate_id=advocate.id,
            sla_due_at=now + timedelta(hours=24),
        ),
    )

    assert result.ok is True
    assert result.code == "ADVOCATE_ASSIGNED"
    assert result.snapshot == {
        "order_ref": "DS-PHASEC01",
        "state": "ADVOCATE_TRIAGE",
        "assignment": {
            "advocate_id": advocate.id,
            "status": "ASSIGNED",
            "conflict_status": "PENDING",
            "authority_scope_version": "ni138-individual-v1",
        },
    }


def test_assigned_advocate_accepts_exact_intake_after_conflict_clearance(db):
    now = utc_now()
    user = User(whatsapp_id="phase-c-client-2", case_id="NS-PHASEC02")
    operator = AdminOperator(
        operator_id="operations-2@example.com",
        display_name="Operations User",
        role="OPERATOR",
        password_hash="test",
        totp_secret_ciphertext="test",
        active=True,
        mfa_enrolled_at=now,
    )
    advocate = Advocate(
        name="Synthetic Advocate Two",
        email="advocate-2@example.com",
        category="banking",
        district="Mumbai",
        active=True,
        verification_status="VERIFIED",
        verification_ref="synthetic-verification-record-2",
        verified_at=now,
        authority_scope_json=json.dumps(
            {
                "version": "ni138-individual-v1",
                "product_codes": ["synthetic_advocate_notice"],
            }
        ),
    )
    db.add_all([user, operator, advocate])
    db.flush()
    identity = AdminOperator(
        operator_id="advocate-2@example.com",
        display_name="Synthetic Advocate Two",
        role="ADVOCATE",
        advocate_id=advocate.id,
        password_hash="test",
        totp_secret_ciphertext="test",
        active=True,
        mfa_enrolled_at=now,
    )
    order = DocumentOrder(
        public_ref="DS-PHASEC02",
        user_id=user.id,
        product_code="synthetic_advocate_notice",
        template_version="synthetic-notice-v1",
        state="ADVOCATE_TRIAGE",
        current_step="advocate_assignment",
        output_classification="ADVOCATE_ISSUED_NOTICE",
        active_revision_number=1,
    )
    db.add_all([identity, order])
    db.flush()
    revision = DocumentAnswerRevision(
        document_order_id=order.id,
        revision_number=1,
        schema_version="synthetic-intake-v1",
        answers_json='{"cheque_amount":"10000"}',
        content_hash="a" * 64,
    )
    db.add(revision)
    db.commit()
    assigned = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("OPERATOR", operator.id),
        command=AssignAdvocate(
            advocate_id=advocate.id,
            sla_due_at=now + timedelta(hours=24),
        ),
    )
    assert assigned.ok is True

    conflict = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=RecordConflictCheck("CLEARED", "NO_CONFLICT_FOUND"),
    )
    accepted = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=RecordMatterDecision(
            decision="ACCEPTED",
            intake_revision_number=1,
            reason_codes=("SYNTHETIC_SCOPE_CONFIRMED",),
            conditions="Synthetic test only",
        ),
    )

    assert conflict.ok is True
    assert conflict.code == "CONFLICT_CLEARED"
    assert accepted.ok is True
    assert accepted.code == "MATTER_ACCEPTED"
    assert accepted.snapshot == {
        "order_ref": "DS-PHASEC02",
        "state": "ADVOCATE_TRIAGE",
        "current_step": "advocate_quote",
        "review": {
            "decision": "ACCEPTED",
            "intake_revision_number": 1,
            "advocate_id": advocate.id,
        },
    }


def test_advocate_quote_requires_customer_acceptance_before_payment(db):
    now = utc_now()
    user = User(whatsapp_id="phase-c-client-3", case_id="NS-PHASEC03")
    operator = AdminOperator(
        operator_id="operations-3@example.com",
        display_name="Operations User",
        role="OPERATOR",
        password_hash="test",
        totp_secret_ciphertext="test",
        active=True,
        mfa_enrolled_at=now,
    )
    advocate = Advocate(
        name="Synthetic Advocate Three",
        email="advocate-3@example.com",
        category="banking",
        district="Mumbai",
        active=True,
        verification_status="VERIFIED",
        verification_ref="synthetic-verification-record-3",
        verified_at=now,
        authority_scope_json=json.dumps(
            {
                "version": "ni138-individual-v1",
                "product_codes": ["synthetic_advocate_notice"],
            }
        ),
    )
    db.add_all([user, operator, advocate])
    db.flush()
    identity = AdminOperator(
        operator_id="advocate-3@example.com",
        display_name="Synthetic Advocate Three",
        role="ADVOCATE",
        advocate_id=advocate.id,
        password_hash="test",
        totp_secret_ciphertext="test",
        active=True,
        mfa_enrolled_at=now,
    )
    order = DocumentOrder(
        public_ref="DS-PHASEC03",
        user_id=user.id,
        product_code="synthetic_advocate_notice",
        template_version="synthetic-notice-v1",
        state="ADVOCATE_TRIAGE",
        current_step="advocate_assignment",
        output_classification="ADVOCATE_ISSUED_NOTICE",
        active_revision_number=1,
    )
    db.add_all([identity, order])
    db.flush()
    db.add(
        DocumentAnswerRevision(
            document_order_id=order.id,
            revision_number=1,
            schema_version="synthetic-intake-v1",
            answers_json='{"cheque_amount":"10000"}',
            content_hash="b" * 64,
        )
    )
    db.commit()
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("OPERATOR", operator.id),
        command=AssignAdvocate(
            advocate_id=advocate.id,
            sla_due_at=now + timedelta(hours=24),
        ),
    ).ok
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=RecordConflictCheck("CLEARED", "NO_CONFLICT_FOUND"),
    ).ok
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=RecordMatterDecision(
            "ACCEPTED",
            1,
            ("SYNTHETIC_SCOPE_CONFIRMED",),
        ),
    ).ok

    quoted = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=CreateQuote(
            amount_minor=150000,
            currency="INR",
            scope_version="notice-scope-v1",
            scope={
                "included_corrections": 1,
                "dispatch_included": False,
                "synthetic": True,
            },
            expires_at=now + timedelta(days=2),
        ),
    )
    payment_client = MagicMock()
    blocked_payment = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=RequestPayment(),
        payment_client=payment_client,
    )
    accepted = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=AcceptQuote(quote_id=quoted.snapshot["quote"]["id"]),
    )
    response = MagicMock()
    response.json.return_value = {
        "id": "plink_phase_c_synthetic",
        "short_url": "https://payments.example/phase-c",
    }
    payment_client.post.return_value = response
    payment = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=RequestPayment(),
        payment_client=payment_client,
    )
    paid = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("PROVIDER", 0),
        command=RecordVerifiedPayment(
            payment_id="pay_phase_c_synthetic",
            amount_minor=150000,
            currency="INR",
        ),
    )
    replayed = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("PROVIDER", 0),
        command=RecordVerifiedPayment(
            payment_id="pay_phase_c_synthetic",
            amount_minor=150000,
            currency="INR",
        ),
    )
    artifact_vault = MemoryArtifactVault()
    artifact_scanner = MagicMock(return_value="CLEAN")
    draft = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=SubmitDraftForFactCheck(
            content=b"%PDF-1.4 synthetic advocate draft",
            expires_at=now + timedelta(days=30),
        ),
        artifact_vault=artifact_vault,
        file_scanner=artifact_scanner,
    )
    confirmed = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=ConfirmNoticeFacts(
            candidate_artifact_ref=draft.snapshot["artifact"]["reference"]
        ),
    )
    issued = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=ApproveIssuedArtifact(
            candidate_artifact_ref=draft.snapshot["artifact"]["reference"],
            signed_content=b"%PDF-1.4 synthetic advocate signed notice",
            signing_method="ADVOCATE_OFFLINE_SIGNED_UPLOAD",
            conditions=None,
            expires_at=now + timedelta(days=30),
        ),
        artifact_vault=artifact_vault,
        file_scanner=artifact_scanner,
    )
    denied_issued_link = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id + 999),
        command=IssueIssuedArtifactLink(),
        artifact_vault=artifact_vault,
    )
    issued_link = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=IssueIssuedArtifactLink(),
        artifact_vault=artifact_vault,
    )
    evidence_vault = MemoryEvidenceVault()
    proof = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=StoreEvidence(
            kind="DISPATCH_PROOF",
            content=b"%PDF-1.4 synthetic speed-post receipt",
            content_type="application/pdf",
            expires_at=now + timedelta(days=30),
        ),
        evidence_vault=evidence_vault,
        file_scanner=artifact_scanner,
    )
    dispatched = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("OPERATOR", operator.id),
        command=RecordDispatch(
            method="SPEED_POST_REGISTERED",
            tracking_reference="SYNTHETIC-TRACK-001",
            address_snapshot_hash="c" * 64,
            proof_evidence_ref=proof.snapshot["evidence"]["reference"],
            occurred_at=now,
        ),
    )
    order.active_revision_number = 2
    superseded_link = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=IssueIssuedArtifactLink(),
        artifact_vault=artifact_vault,
    )

    assert quoted.ok is True
    assert quoted.code == "QUOTE_CREATED"
    assert quoted.snapshot["state"] == "ACCEPTED_AND_QUOTED"
    assert quoted.snapshot["quote"]["amount_minor"] == 150000
    assert accepted.ok is True
    assert accepted.code == "QUOTE_ACCEPTED"
    assert accepted.snapshot["state"] == "QUOTE_ACCEPTED"
    assert accepted.snapshot["price_minor"] == 150000
    assert order.price_minor == 150000
    assert order.currency == "INR"
    assert blocked_payment.ok is False
    assert blocked_payment.code == "QUOTE_ACCEPTANCE_REQUIRED"
    assert payment.ok is True
    assert payment.code == "PAYMENT_PENDING"
    assert payment.snapshot == {
        "order_ref": "DS-PHASEC03",
        "state": "PAYMENT_PENDING",
        "payment_url": "https://payments.example/phase-c",
        "amount_minor": 150000,
        "currency": "INR",
        "quote_id": quoted.snapshot["quote"]["id"],
    }
    assert paid.ok is True
    assert paid.code == "ADVOCATE_DRAFTING"
    assert paid.snapshot == {
        "order_ref": "DS-PHASEC03",
        "state": "ADVOCATE_DRAFTING",
        "payment_processed": True,
        "amount_minor": 150000,
        "currency": "INR",
    }
    assert replayed.ok is True
    assert replayed.code == "ALREADY_PROCESSED"
    assert draft.ok is True
    assert draft.code == "CUSTOMER_FACT_CHECK"
    assert confirmed.ok is True
    assert confirmed.code == "ADVOCATE_FINAL_APPROVAL"
    assert issued.ok is True
    assert issued.code == "ISSUED"
    assert issued.snapshot["state"] == "ISSUED"
    assert db.query(DocumentAdvocateAssignment).one().status == "ISSUED"
    assert issued.snapshot["approval"]["advocate_id"] == advocate.id
    assert issued.snapshot["approval"]["revision_number"] == 1
    assert issued.snapshot["approval"]["artifact_hash"] == hashlib.sha256(
        b"%PDF-1.4 synthetic advocate signed notice"
    ).hexdigest()
    assert issued_link.ok is True
    assert issued_link.code == "ISSUED_ARTIFACT_LINK_READY"
    assert issued_link.snapshot["artifact_kind"] == "ISSUED_PDF"
    assert issued_link.snapshot["download_url"].startswith("memory://")
    assert denied_issued_link.code == "ISSUED_ARTIFACT_ACCESS_DENIED"
    assert superseded_link.ok is False
    assert superseded_link.code == "ISSUED_ARTIFACT_NOT_AVAILABLE"
    assert (
        db.query(DocumentAccessEvent)
        .filter(
            DocumentAccessEvent.action == "DOWNLOAD",
            DocumentAccessEvent.decision == "DENIED",
        )
        .count()
        == 2
    )
    queued = db.query(OutboxJob).one()
    assert queued.kind == "document_final_delivery"
    assert json.loads(queued.payload_json) == {"document_order_id": order.id}
    assert proof.ok is True
    assert dispatched.ok is True
    assert dispatched.code == "DISPATCH_RECORDED"
    assert dispatched.snapshot == {
        "order_ref": "DS-PHASEC03",
        "state": "DISPATCH_RECORDED",
        "dispatch": {
            "method": "SPEED_POST_REGISTERED",
            "status": "DISPATCHED",
            "tracking_reference_hash": hashlib.sha256(
                b"SYNTHETIC-TRACK-001"
            ).hexdigest(),
            "proof_evidence_ref": proof.snapshot["evidence"]["reference"],
        },
    }


def test_private_evidence_requires_clean_scan_and_owner_access(db):
    now = utc_now()
    user = User(whatsapp_id="phase-c-client-4", case_id="NS-PHASEC04")
    order = DocumentOrder(
        public_ref="DS-PHASEC04",
        user_id=1,
        product_code="synthetic_advocate_notice",
        template_version="synthetic-notice-v1",
        state="EVIDENCE_PENDING",
        current_step="evidence",
        output_classification="ADVOCATE_ISSUED_NOTICE",
        active_revision_number=1,
    )
    db.add(user)
    db.flush()
    order.user_id = user.id
    db.add(order)
    db.commit()
    content = b"%PDF-1.4 synthetic evidence only"
    scanner = MagicMock(return_value="CLEAN")
    vault = MemoryEvidenceVault()

    stored = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=StoreEvidence(
            kind="CHEQUE_FRONT",
            content=content,
            content_type="application/pdf",
            expires_at=now + timedelta(days=30),
        ),
        evidence_vault=vault,
        file_scanner=scanner,
    )
    evidence_ref = stored.snapshot["evidence"]["reference"]
    denied = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id + 999),
        command=IssueEvidenceLink(evidence_ref),
        evidence_vault=vault,
    )
    allowed = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=IssueEvidenceLink(evidence_ref),
        evidence_vault=vault,
    )
    evidence = db.query(DocumentEvidenceArtifact).one()
    evidence.expires_at = now - timedelta(seconds=1)
    expired = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=IssueEvidenceLink(evidence_ref),
        evidence_vault=vault,
    )

    assert stored.ok is True
    assert stored.code == "EVIDENCE_STORED"
    assert stored.snapshot["evidence"] == {
        "reference": evidence_ref,
        "kind": "CHEQUE_FRONT",
        "content_type": "application/pdf",
        "size_bytes": len(content),
        "content_hash": hashlib.sha256(content).hexdigest(),
        "scan_status": "CLEAN",
        "review_status": "PENDING",
    }
    assert denied.ok is False
    assert denied.code == "EVIDENCE_ACCESS_DENIED"
    assert allowed.ok is True
    assert allowed.code == "EVIDENCE_LINK_READY"
    assert allowed.snapshot == {
        "evidence_ref": evidence_ref,
        "download_url": f"memory://{vault.object_key_for(evidence_ref)}",
    }
    assert expired.ok is False
    assert expired.code == "EVIDENCE_NOT_AVAILABLE"
    assert (
        db.query(DocumentAccessEvent)
        .filter(
            DocumentAccessEvent.action == "EVIDENCE_DOWNLOAD",
            DocumentAccessEvent.decision == "DENIED",
            DocumentAccessEvent.reason_code == "EVIDENCE_NOT_AVAILABLE",
        )
        .count()
        == 1
    )


def test_conflict_is_audited_terminal_path_and_never_becomes_payable(db):
    _, user, _, _, identity, order = _assigned_notice(db, "CONFLICT")

    conflicted = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=RecordConflictCheck("CONFLICT", "SYNTHETIC_RELATED_PARTY"),
    )
    payment_client = MagicMock()
    payment = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=RequestPayment(),
        payment_client=payment_client,
    )

    assert conflicted.ok is True
    assert conflicted.code == "CONFLICT_RECORDED"
    assert order.state == "CONFLICTED"
    assert order.exception_code == "ADVOCATE_CONFLICT"
    assert payment.code == "QUOTE_ACCEPTANCE_REQUIRED"
    payment_client.post.assert_not_called()


@pytest.mark.parametrize(
    ("decision", "expected_state"),
    (("DECLINED", "DECLINED"), ("UNSUPPORTED", "UNSUPPORTED")),
)
def test_advocate_decline_paths_never_create_quote_or_payment(
    db,
    decision,
    expected_state,
):
    _, user, _, _, identity, order = _assigned_notice(db, decision)
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=RecordConflictCheck("CLEARED", "NO_CONFLICT_FOUND"),
    ).ok

    result = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=RecordMatterDecision(
            decision,
            1,
            (f"SYNTHETIC_{decision}_REASON",),
        ),
    )
    payment_client = MagicMock()
    payment = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=RequestPayment(),
        payment_client=payment_client,
    )

    assert result.code == f"MATTER_{decision}"
    assert order.state == expected_state
    assert db.query(DocumentQuote).count() == 0
    assert payment.code == "QUOTE_ACCEPTANCE_REQUIRED"
    payment_client.post.assert_not_called()


def test_expired_quote_returns_to_advocate_for_a_new_immutable_quote(db):
    now, user, _, _, identity, order = _accepted_notice(db, "QUOTEEXP")
    quoted = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=CreateQuote(
            amount_minor=125000,
            currency="INR",
            scope_version="synthetic-scope-v1",
            scope={"synthetic": True},
            expires_at=now + timedelta(hours=1),
        ),
    )
    quote = db.get(DocumentQuote, quoted.snapshot["quote"]["id"])
    quote.expires_at = utc_now() - timedelta(seconds=1)

    expired = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=AcceptQuote(quote_id=quote.id),
    )

    assert expired.code == "QUOTE_EXPIRED"
    assert quote.status == "EXPIRED"
    assert order.state == "ADVOCATE_TRIAGE"
    assert order.current_step == "advocate_quote"
    assert order.price_minor is None


def test_payment_provider_failure_is_explicit_and_does_not_mark_paid(db):
    now, user, _, _, identity, order = _accepted_notice(db, "PAYERROR")
    quoted = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=CreateQuote(
            amount_minor=125000,
            currency="INR",
            scope_version="synthetic-scope-v1",
            scope={"synthetic": True},
            expires_at=now + timedelta(hours=1),
        ),
    )
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=AcceptQuote(quoted.snapshot["quote"]["id"]),
    ).ok
    payment_client = MagicMock()
    payment_client.post.side_effect = RuntimeError("synthetic provider failure")

    result = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=RequestPayment(),
        payment_client=payment_client,
    )

    assert result.code == "PAYMENT_LINK_CREATE_FAILED"
    assert order.state == "NEEDS_ATTENTION"
    assert order.exception_code == "PAYMENT_LINK_CREATE_FAILED"
    assert order.payment_processed is False
    assert order.razorpay_payment_link_id is None


def test_verified_payment_mismatch_fails_closed(db):
    now, user, _, _, identity, order = _accepted_notice(db, "PAYMISMATCH")
    quoted = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADVOCATE", identity.id),
        command=CreateQuote(
            amount_minor=125000,
            currency="INR",
            scope_version="synthetic-scope-v1",
            scope={"synthetic": True},
            expires_at=now + timedelta(hours=1),
        ),
    )
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=AcceptQuote(quoted.snapshot["quote"]["id"]),
    ).ok
    response = MagicMock()
    response.json.return_value = {
        "id": "plink_phase_c_mismatch",
        "short_url": "https://payments.example/mismatch",
    }
    payment_client = MagicMock()
    payment_client.post.return_value = response
    assert execute_notice_command(
        db,
        order,
        actor=WorkflowActor("CLIENT", user.id),
        command=RequestPayment(),
        payment_client=payment_client,
    ).ok

    mismatch = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("PROVIDER", 0),
        command=RecordVerifiedPayment(
            payment_id="pay_phase_c_mismatch",
            amount_minor=124999,
            currency="INR",
        ),
    )

    assert mismatch.code == "PAYMENT_EVIDENCE_MISMATCH"
    assert order.state == "PAYMENT_PENDING"
    assert order.payment_processed is False
    assert order.razorpay_payment_id is None


def test_only_mfa_admin_can_open_and_close_legal_hold(db):
    now = utc_now()
    user = User(whatsapp_id="phase-c-hold-client", case_id="NS-PHASEC05")
    admin = AdminOperator(
        operator_id="admin@example.com",
        display_name="Administration User",
        role="ADMIN",
        password_hash="test",
        totp_secret_ciphertext="test",
        active=True,
        mfa_enrolled_at=now,
    )
    operator = AdminOperator(
        operator_id="operator@example.com",
        display_name="Operations User",
        role="OPERATOR",
        password_hash="test",
        totp_secret_ciphertext="test",
        active=True,
        mfa_enrolled_at=now,
    )
    db.add_all([user, admin, operator])
    db.flush()
    order = DocumentOrder(
        public_ref="DS-PHASEC05",
        user_id=user.id,
        product_code="synthetic_advocate_notice",
        template_version="synthetic-notice-v1",
        state="ISSUED",
        current_step="issued",
        output_classification="ADVOCATE_ISSUED_NOTICE",
        payment_processed=True,
    )
    db.add(order)
    db.commit()

    denied = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("OPERATOR", operator.id),
        command=OpenLegalHold(
            reason_code="SYNTHETIC_DISPUTE",
            authority_statement="Synthetic Phase C retention exercise.",
        ),
    )
    opened = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADMIN", admin.id),
        command=OpenLegalHold(
            reason_code="SYNTHETIC_DISPUTE",
            authority_statement="Synthetic Phase C retention exercise.",
        ),
    )
    hold = db.get(DocumentLegalHold, opened.snapshot["hold_id"])
    denied_close = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("OPERATOR", operator.id),
        command=CloseLegalHold(
            hold_id=hold.id,
            closure_reason="Not authorized to release retained records.",
        ),
    )
    closed = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("ADMIN", admin.id),
        command=CloseLegalHold(
            hold_id=hold.id,
            closure_reason="Synthetic retention exercise completed.",
        ),
    )

    assert denied.code == "LEGAL_HOLD_ADMIN_REQUIRED"
    assert opened.snapshot == {
        "order_ref": "DS-PHASEC05",
        "hold_id": hold.id,
        "hold_status": "ACTIVE",
        "reason_code": "SYNTHETIC_DISPUTE",
    }
    assert hold.opened_by_identity_id == admin.id
    assert denied_close.code == "LEGAL_HOLD_ADMIN_REQUIRED"
    assert closed.snapshot == {
        "order_ref": "DS-PHASEC05",
        "hold_id": hold.id,
        "hold_status": "CLOSED",
    }
    assert hold.closed_by_identity_id == admin.id
    assert hold.closed_at is not None
    assert hold.closure_reason == "Synthetic retention exercise completed."
