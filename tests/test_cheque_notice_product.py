"""Behavior tests for the private cheque-notice legal package."""

from __future__ import annotations

import json
import hashlib
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    DocumentAnswerRevision,
    DocumentAuditEvent,
    DocumentEvidenceArtifact,
    DocumentOrder,
    User,
    utc_now,
)
from services.advocate_issued_workflow import (
    EvaluateChequeNoticeIntake,
    WorkflowActor,
    execute_notice_command,
)
from services import document_catalogue as catalogue
from services import cheque_notice_product as cheque_notice
from services import document_renderer
from services.cheque_notice_renderer import (
    render_factual_summary,
    render_notice_for_advocate,
)
from services.document_release_service import (
    record_approval,
    release_gate,
    release_manifest,
)


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


def test_cheque_notice_is_registered_but_not_customer_visible(monkeypatch):
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_PRICE_INR", 299)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset({catalogue.PRODUCT_CODE}),
    )

    product = catalogue.resolve_product(catalogue.CHEQUE_NOTICE_PRODUCT_CODE)

    assert catalogue.registered_product_codes() == (
        catalogue.PRODUCT_CODE,
        catalogue.CHEQUE_NOTICE_PRODUCT_CODE,
    )
    assert product.output_classification == "ADVOCATE_ISSUED_NOTICE"
    assert product.price_model == "ADVOCATE_QUOTE"
    assert product.price_minor == 0
    assert catalogue.customer_visible(product.code) is False
    assert tuple(item.code for item in catalogue.visible_products()) == (
        catalogue.PRODUCT_CODE,
    )


def test_advocate_quote_product_requires_no_fixed_catalogue_price():
    enabled = frozenset(
        {catalogue.PRODUCT_CODE, catalogue.CHEQUE_NOTICE_PRODUCT_CODE}
    )

    configured = catalogue.catalogue_configuration(
        enabled=True,
        allowlist=enabled,
        prices_inr={catalogue.PRODUCT_CODE: 299},
    )
    wrongly_priced = catalogue.catalogue_configuration(
        enabled=True,
        allowlist=enabled,
        prices_inr={
            catalogue.PRODUCT_CODE: 299,
            catalogue.CHEQUE_NOTICE_PRODUCT_CODE: 499,
        },
    )

    assert configured.ok is True
    assert wrongly_priced.ok is False
    assert wrongly_priced.reason_code == "PRICE_CONFIGURED_FOR_QUOTE_PRODUCT"


def test_supported_intake_reaches_advocate_triage_without_legal_conclusion():
    answers = cheque_notice.golden_answers()

    result = cheque_notice.validate_intake(
        answers,
        evidence_scan_statuses={
            "CHEQUE_FRONT": "CLEAN",
            "RETURN_MEMO": "CLEAN",
            "LIABILITY_SUPPORT": "CLEAN",
        },
    )

    shortest_path = tuple(
        question
        for question in cheque_notice.QUESTION_DEFINITIONS
        if question.conditional_on is None
    )
    assert len(shortest_path) == 18
    assert result.status == "READY_FOR_ADVOCATE_TRIAGE"
    assert result.reason_codes == ()
    assert result.normalized_answers["cheque_amount_inr"] == "250000.00"
    assert result.warnings == ("ADVOCATE_TIMING_CONFIRMATION_REQUIRED",)


def test_missing_evidence_pauses_before_quote_or_payment():
    result = cheque_notice.validate_intake(
        cheque_notice.golden_answers(),
        evidence_scan_statuses={"CHEQUE_FRONT": "CLEAN"},
    )

    assert result.status == "EVIDENCE_PENDING"
    assert result.reason_codes == (
        "EVIDENCE_MISSING_LIABILITY_SUPPORT",
        "EVIDENCE_MISSING_RETURN_MEMO",
    )


@pytest.mark.parametrize(
    ("changes", "reason_code"),
    (
        ({"claimant_scope": "NO"}, "CLAIMANT_SCOPE_UNSUPPORTED"),
        ({"instrument_scope": "UNSURE"}, "INSTRUMENT_SCOPE_UNSUPPORTED"),
        ({"liability_category": "GOODS"}, "LIABILITY_CATEGORY_UNSUPPORTED"),
        ({"return_reason_exact": "ACCOUNT CLOSED"}, "RETURN_REASON_REQUIRES_REVIEW"),
        ({"post_issue_change": "YES"}, "POST_ISSUE_CHANGE_REQUIRES_REVIEW"),
        ({"prior_demand_or_notice": "YES"}, "PRIOR_NOTICE_REQUIRES_REVIEW"),
        ({"existing_proceeding": "YES"}, "EXISTING_PROCEEDING_REQUIRES_REVIEW"),
    ),
)
def test_unsupported_or_uncertain_answers_route_before_payment(
    changes,
    reason_code,
):
    answers = {**cheque_notice.golden_answers(), **changes}

    result = cheque_notice.validate_intake(
        answers,
        evidence_scan_statuses={
            kind: "CLEAN" for kind in cheque_notice.MANDATORY_EVIDENCE_KINDS
        },
    )

    assert result.status == "ROUTED_OUT"
    assert reason_code in result.reason_codes


def test_amount_mismatch_and_customer_accusation_fail_closed():
    mismatch = {
        **cheque_notice.golden_answers(),
        "cheque_amount_confirmation_inr": "250001",
    }
    accusation = {
        **cheque_notice.golden_answers(),
        "liability_summary": (
            "The customer calls the drawer a fraud and demands punishment."
        ),
    }
    evidence = {
        kind: "CLEAN" for kind in cheque_notice.MANDATORY_EVIDENCE_KINDS
    }

    mismatch_result = cheque_notice.validate_intake(
        mismatch,
        evidence_scan_statuses=evidence,
    )
    accusation_result = cheque_notice.validate_intake(
        accusation,
        evidence_scan_statuses=evidence,
    )

    assert mismatch_result.status == "INVALID"
    assert mismatch_result.reason_codes == (
        "CHEQUE_AMOUNT_CONFIRMATION_MISMATCH",
    )
    assert accusation_result.status == "ROUTED_OUT"
    assert accusation_result.reason_codes == (
        "ACCUSATION_REQUIRES_ADVOCATE_REVIEW",
    )


def test_unexpected_sensitive_fields_are_not_accepted_into_normalized_intake():
    answers = {
        **cheque_notice.golden_answers(),
        "bank_account_number": "synthetic-value-that-must-not-be-collected",
    }

    result = cheque_notice.validate_intake(
        answers,
        evidence_scan_statuses={
            kind: "CLEAN" for kind in cheque_notice.MANDATORY_EVIDENCE_KINDS
        },
    )

    assert result.status == "INVALID"
    assert result.reason_codes == ("UNEXPECTED_INTAKE_FIELD",)
    assert "bank_account_number" not in result.normalized_answers


def test_release_manifest_binds_two_pdf_artifacts_and_no_editable_final():
    product = catalogue.resolve_product(catalogue.CHEQUE_NOTICE_PRODUCT_CODE)

    first = release_manifest(product.code)
    second = release_manifest(product.code)

    assert first == second
    assert first["golden_artifact_hashes"].keys() == {
        "FACTUAL_SUMMARY_PDF",
        "NOTICE_REVIEW_PDF",
    }
    assert all(
        len(value) == 64
        for value in first["golden_artifact_hashes"].values()
    )
    assert "golden_docx_hash" not in first


def test_exact_two_pdf_package_approval_opens_only_cheque_release_gate(db):
    manifest = release_manifest(catalogue.CHEQUE_NOTICE_PRODUCT_CODE)
    now = utc_now()
    approval = record_approval(
        db,
        {
            "reviewer_name": "Synthetic Verified Advocate",
            "reviewer_enrolment_ref": "SYNTHETIC-REVIEW-REF",
            "authority_statement": "Authorized to review the exact package",
            "authenticated_method": "NAMED_MFA_AND_SIGNED_RECORD",
            "authenticated_at": (now - timedelta(minutes=1)).isoformat(),
            "next_review_at": (now + timedelta(days=30)).isoformat(),
            "decision": "APPROVED",
            "template_aggregate_hash": manifest["template_aggregate_hash"],
            "golden_artifact_hashes": manifest["golden_artifact_hashes"],
        },
        recorded_by="phase-d-test-operator",
        product_code=catalogue.CHEQUE_NOTICE_PRODUCT_CODE,
    )
    db.commit()

    assert approval.golden_pdf_hash is None
    assert approval.golden_docx_hash is None
    assert json.loads(approval.golden_artifact_hashes_json) == manifest[
        "golden_artifact_hashes"
    ]
    gate = release_gate(db, catalogue.CHEQUE_NOTICE_PRODUCT_CODE)
    assert gate.allowed is True
    assert gate.reason_code == "APPROVED"


def test_cheque_package_rejects_legacy_pdf_docx_approval_contract(db):
    manifest = release_manifest(catalogue.CHEQUE_NOTICE_PRODUCT_CODE)
    now = utc_now()

    with pytest.raises(ValueError, match="invalid_golden_artifact_hashes"):
        record_approval(
            db,
            {
                "reviewer_name": "Synthetic Verified Advocate",
                "reviewer_enrolment_ref": "SYNTHETIC-REVIEW-REF",
                "authority_statement": "Authorized to review the exact package",
                "authenticated_method": "NAMED_MFA_AND_SIGNED_RECORD",
                "authenticated_at": (now - timedelta(minutes=1)).isoformat(),
                "next_review_at": (now + timedelta(days=30)).isoformat(),
                "decision": "APPROVED",
                "template_aggregate_hash": manifest[
                    "template_aggregate_hash"
                ],
                "golden_pdf_hash": "1" * 64,
                "golden_docx_hash": "2" * 64,
            },
            recorded_by="phase-d-test-operator",
            product_code=catalogue.CHEQUE_NOTICE_PRODUCT_CODE,
        )


def test_cheque_release_gate_rejects_mutated_artifact_hash(db):
    manifest = release_manifest(catalogue.CHEQUE_NOTICE_PRODUCT_CODE)
    now = utc_now()
    hashes = dict(manifest["golden_artifact_hashes"])
    hashes["NOTICE_REVIEW_PDF"] = "0" * 64
    record_approval(
        db,
        {
            "reviewer_name": "Synthetic Verified Advocate",
            "reviewer_enrolment_ref": "SYNTHETIC-REVIEW-REF",
            "authority_statement": "Authorized to review the exact package",
            "authenticated_method": "NAMED_MFA_AND_SIGNED_RECORD",
            "authenticated_at": (now - timedelta(minutes=1)).isoformat(),
            "next_review_at": (now + timedelta(days=30)).isoformat(),
            "decision": "APPROVED",
            "template_aggregate_hash": manifest["template_aggregate_hash"],
            "golden_artifact_hashes": hashes,
        },
        recorded_by="phase-d-test-operator",
        product_code=catalogue.CHEQUE_NOTICE_PRODUCT_CODE,
    )
    db.commit()

    gate = release_gate(db, catalogue.CHEQUE_NOTICE_PRODUCT_CODE)
    assert gate.allowed is False
    assert gate.reason_code == "GOLDEN_ARTIFACT_HASH_MISMATCH"


def test_notice_package_has_internal_pdf_pair_but_no_self_service_docx():
    product = catalogue.resolve_product(catalogue.CHEQUE_NOTICE_PRODUCT_CODE)
    answers = cheque_notice.golden_answers()
    advocate_context = {
        "notice_date": "2026-09-11",
        "advocate_practice_name": "Synthetic Review Practice",
        "advocate_full_name": "Synthetic Review Advocate",
        "advocate_enrolment_ref": "SYNTHETIC-NOT-AN-ENROLMENT",
        "advocate_service_address": (
            "3 Review Street, Mumbai, Maharashtra 400001"
        ),
    }

    summary = render_factual_summary(product, answers)
    notice = render_notice_for_advocate(product, answers, advocate_context)

    assert summary.kind == "FACTUAL_SUMMARY_PDF"
    assert notice.kind == "NOTICE_REVIEW_PDF"
    assert summary.content.startswith(b"%PDF-")
    assert notice.content.startswith(b"%PDF-")
    assert summary.content_hash != notice.content_hash
    with pytest.raises(
        ValueError,
        match="self_service_renderer_classification_required",
    ):
        document_renderer.render(product, answers, "FINAL_DOCX")


def test_golden_supported_boundary_and_decline_scenarios_are_executable():
    scenarios = {
        scenario.code: scenario
        for scenario in cheque_notice.golden_scenarios()
    }

    assert set(scenarios) == {"SUPPORTED", "TIMING_BOUNDARY", "DECLINE"}
    for scenario in scenarios.values():
        result = cheque_notice.validate_intake(
            scenario.answers,
            evidence_scan_statuses=scenario.evidence_scan_statuses,
            as_of=scenario.as_of,
        )
        assert result.status == scenario.expected_status
        assert result.reason_codes == scenario.expected_reason_codes
    assert scenarios["TIMING_BOUNDARY"].expected_status == (
        "READY_FOR_ADVOCATE_TRIAGE"
    )


def test_confirmed_clean_intake_needs_package_approval_then_enters_triage(db):
    product = catalogue.resolve_product(catalogue.CHEQUE_NOTICE_PRODUCT_CODE)
    answers = cheque_notice.golden_answers()
    answer_bytes = json.dumps(
        answers,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    user = User(whatsapp_id="phase-d-intake", case_id="NS-PHASED01")
    db.add(user)
    db.flush()
    order = DocumentOrder(
        public_ref="DS-PHASED01",
        user_id=user.id,
        product_code=product.code,
        template_version=product.template_version,
        state="EVIDENCE_PENDING",
        current_step="evidence_validation",
        output_classification=product.output_classification,
        active_revision_number=1,
        schema_hash=product.schema_hash,
        template_hash=product.template_hash,
        currency=product.currency,
    )
    db.add(order)
    db.flush()
    db.add(
        DocumentAnswerRevision(
            document_order_id=order.id,
            revision_number=1,
            schema_version=product.schema_version,
            answers_json=answer_bytes.decode("utf-8"),
            content_hash=hashlib.sha256(answer_bytes).hexdigest(),
        )
    )
    for index, kind in enumerate(cheque_notice.MANDATORY_EVIDENCE_KINDS, 1):
        db.add(
            DocumentEvidenceArtifact(
                public_ref=f"EVD-PHASED0{index}",
                document_order_id=order.id,
                revision_number=1,
                evidence_kind=kind,
                state="AVAILABLE",
                storage_provider="MEMORY_TEST_ONLY",
                bucket="memory-test",
                object_key=f"phase-d/{kind.lower()}",
                content_type="application/pdf",
                size_bytes=20,
                content_hash=str(index) * 64,
                scan_status="CLEAN",
                review_status="PENDING",
                uploaded_by_type="CLIENT",
                uploaded_by_ref=str(user.id),
                expires_at=utc_now() + timedelta(days=30),
            )
        )
    db.flush()

    blocked = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("SYSTEM", 0),
        command=EvaluateChequeNoticeIntake(),
    )
    assert blocked.ok is False
    assert blocked.code == "ADVOCATE_APPROVAL_MISSING"
    assert order.state == "EVIDENCE_PENDING"

    manifest = release_manifest(product.code)
    now = utc_now()
    record_approval(
        db,
        {
            "reviewer_name": "Synthetic Verified Advocate",
            "reviewer_enrolment_ref": "SYNTHETIC-REVIEW-REF",
            "authority_statement": "Authorized to review the exact package",
            "authenticated_method": "NAMED_MFA_AND_SIGNED_RECORD",
            "authenticated_at": (now - timedelta(minutes=1)).isoformat(),
            "next_review_at": (now + timedelta(days=30)).isoformat(),
            "decision": "APPROVED",
            "template_aggregate_hash": manifest["template_aggregate_hash"],
            "golden_artifact_hashes": manifest["golden_artifact_hashes"],
        },
        recorded_by="phase-d-test-operator",
        product_code=product.code,
    )
    ready = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("SYSTEM", 0),
        command=EvaluateChequeNoticeIntake(),
    )

    assert ready.ok is True
    assert ready.code == "ADVOCATE_TRIAGE"
    assert order.state == "ADVOCATE_TRIAGE"
    assert order.current_step == "advocate_assignment"
    event = (
        db.query(DocumentAuditEvent)
        .filter(DocumentAuditEvent.document_order_id == order.id)
        .order_by(DocumentAuditEvent.id.desc())
        .first()
    )
    assert json.loads(event.details_json) == {
        "reason_codes": [],
        "revision_number": 1,
        "warnings": ["ADVOCATE_TIMING_CONFIRMATION_REQUIRED"],
    }
