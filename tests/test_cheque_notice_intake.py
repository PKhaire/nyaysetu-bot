"""Behavior tests for the resumable Phase E cheque-notice intake."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    DocumentAnswerRevision,
    DocumentEvidenceArtifact,
    DocumentOrder,
    DocumentQuote,
    User,
    utc_now,
)
from services import cheque_notice_intake_service as intake
from services import document_catalogue as catalogue
from services.cheque_notice_product import golden_answers
from services.document_release_service import record_approval, release_manifest


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


@pytest.fixture
def published_cheque_intake(monkeypatch, db):
    monkeypatch.setattr(intake, "ENV", "staging")
    monkeypatch.setattr(intake, "CHEQUE_NOTICE_STAGING_UAT_ENABLED", True)
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_PRICE_INR", 299)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset(
            {
                catalogue.PRODUCT_CODE,
                catalogue.CHEQUE_NOTICE_PRODUCT_CODE,
            }
        ),
    )
    monkeypatch.setattr(intake, "SECRET_KEY", "s" * 64)
    manifest = release_manifest(catalogue.CHEQUE_NOTICE_PRODUCT_CODE)
    now = utc_now()
    record_approval(
        db,
        {
            "reviewer_name": "Synthetic Verified Advocate",
            "reviewer_enrolment_ref": "SYNTHETIC-REVIEW-REF",
            "authority_statement": "Approved exact synthetic intake package",
            "authenticated_method": "NAMED_MFA_AND_SIGNED_RECORD",
            "authenticated_at": (now - timedelta(minutes=1)).isoformat(),
            "next_review_at": (now + timedelta(days=30)).isoformat(),
            "decision": "APPROVED",
            "template_aggregate_hash": manifest["template_aggregate_hash"],
            "golden_artifact_hashes": manifest["golden_artifact_hashes"],
        },
        recorded_by="phase-e-test-operator",
        product_code=catalogue.CHEQUE_NOTICE_PRODUCT_CODE,
    )
    user = User(
        whatsapp_id="919900001111",
        case_id="NS-PHASEE01",
        language="en",
    )
    db.add(user)
    db.flush()
    return user


def _exchange(db, token, screen, answers):
    return intake.handle_notice_flow_request(
        db,
        {
            "action": "data_exchange",
            "flow_token": token,
            "screen": screen,
            "data": {
                field: answers[field]
                for field in intake.SCREEN_FIELDS[screen]
                if field in answers
            },
        },
    )


def test_customer_can_complete_six_sections_without_payment_or_notice(
    db,
    published_cheque_intake,
):
    user = published_cheque_intake
    order = intake.create_or_resume_notice_order(db, user.id)
    token = intake.issue_notice_flow_token(order)

    opened = intake.handle_notice_flow_request(
        db,
        {"action": "INIT", "flow_token": token},
    )
    assert opened["screen"] == "SUITABILITY"

    answers = golden_answers()
    for index, screen in enumerate(intake.FLOW_SCREENS):
        result = _exchange(db, token, screen, answers)
        if index < len(intake.FLOW_SCREENS) - 1:
            assert result["screen"] == intake.FLOW_SCREENS[index + 1]

    params = result["data"]["extension_message_response"]["params"]
    assert result["screen"] == "SUCCESS"
    assert params == {
        "flow_token": token,
        "order_ref": order.public_ref,
        "status": "EVIDENCE_PENDING",
    }
    completed = intake.completion_for_user(db, params, user_id=user.id)
    assert completed.id == order.id
    assert order.state == "EVIDENCE_PENDING"
    assert order.payment_processed is False
    assert order.price_minor is None
    assert order.razorpay_payment_link_id is None
    assert db.query(DocumentQuote).count() == 0
    assert db.query(DocumentEvidenceArtifact).count() == 0
    revisions = db.query(DocumentAnswerRevision).all()
    assert len(revisions) == 1
    assert revisions[0].revision_number == 1
    assert order.active_revision_number == 1


def test_saved_sections_resume_at_the_next_section(
    db,
    published_cheque_intake,
):
    user = published_cheque_intake
    order = intake.create_or_resume_notice_order(db, user.id)
    first_token = intake.issue_notice_flow_token(order)
    result = _exchange(
        db,
        first_token,
        "SUITABILITY",
        golden_answers(),
    )
    assert result["screen"] == "PEOPLE_ADDRESSES"

    resumed = intake.create_or_resume_notice_order(db, user.id)
    second_token = intake.issue_notice_flow_token(resumed)
    reopened = intake.handle_notice_flow_request(
        db,
        {"action": "INIT", "flow_token": second_token},
    )

    assert resumed.id == order.id
    assert reopened["screen"] == "PEOPLE_ADDRESSES"
    assert "claimant_scope" not in reopened["data"]


def test_out_of_sequence_or_cross_user_completion_fails_closed(
    db,
    published_cheque_intake,
):
    user = published_cheque_intake
    order = intake.create_or_resume_notice_order(db, user.id)
    token = intake.issue_notice_flow_token(order)

    with pytest.raises(
        intake.ChequeNoticeFlowError,
        match="flow_screen_out_of_sequence",
    ):
        _exchange(db, token, "DISHONOUR", golden_answers())

    with pytest.raises(
        intake.ChequeNoticeFlowError,
        match="invalid_flow_completion",
    ):
        intake.completion_for_user(
            db,
            {
                "flow_token": token,
                "order_ref": order.public_ref,
                "status": "EVIDENCE_PENDING",
            },
            user_id=user.id + 1,
        )


def test_unsupported_answers_stop_before_evidence_and_payment(
    db,
    published_cheque_intake,
):
    user = published_cheque_intake
    order = intake.create_or_resume_notice_order(db, user.id)
    token = intake.issue_notice_flow_token(order)
    answers = {**golden_answers(), "claimant_scope": "NO"}

    for screen in intake.FLOW_SCREENS:
        result = _exchange(db, token, screen, answers)

    params = result["data"]["extension_message_response"]["params"]
    assert params["status"] == "ROUTED_OUT"
    assert order.state == "ROUTED_OUT"
    assert order.payment_processed is False
    assert order.price_minor is None
    assert db.query(DocumentQuote).count() == 0
    assert db.query(DocumentEvidenceArtifact).count() == 0


def test_hidden_cheque_product_cannot_create_an_intake(monkeypatch, db):
    monkeypatch.setattr(intake, "ENV", "staging")
    monkeypatch.setattr(intake, "CHEQUE_NOTICE_STAGING_UAT_ENABLED", True)
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset({catalogue.PRODUCT_CODE}),
    )
    user = User(whatsapp_id="919900002222", case_id="NS-PHASEE02")
    db.add(user)
    db.flush()

    with pytest.raises(
        intake.ChequeNoticeFlowError,
        match="document_product_not_enabled",
    ):
        intake.create_or_resume_notice_order(db, user.id)

    assert db.query(DocumentOrder).count() == 0


def test_cheque_intake_cannot_create_outside_the_staging_switch(
    monkeypatch,
    db,
):
    monkeypatch.setattr(intake, "ENV", "production")
    monkeypatch.setattr(intake, "CHEQUE_NOTICE_STAGING_UAT_ENABLED", True)
    user = User(whatsapp_id="919900003333", case_id="NS-PHASEE03")
    db.add(user)
    db.flush()

    with pytest.raises(
        intake.ChequeNoticeFlowError,
        match="cheque_notice_uat_not_configured",
    ):
        intake.create_or_resume_notice_order(db, user.id)

    assert db.query(DocumentOrder).count() == 0
