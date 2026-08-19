"""Tests for the deliberately non-legal Document Studio UAT harness."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    Booking,
    DocumentAnswerRevision,
    DocumentAuditEvent,
    DocumentOrder,
    User,
)
from services import document_studio_service as studio
from services.document_studio_service import (
    UAT_OUTPUT_CLASSIFICATION,
    confirm_answers,
    create_or_resume_uat_order,
    current_question,
    save_answer,
    validate_answer,
)


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


def test_uat_availability_is_restricted_to_explicit_testers(monkeypatch):
    allowed = User(whatsapp_id="919900001111")
    denied = User(whatsapp_id="919900002222")
    monkeypatch.setattr(studio, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(studio, "DOCUMENT_STUDIO_UAT_ONLY", True)
    monkeypatch.setattr(studio, "ENV", "staging")
    monkeypatch.setattr(
        studio,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset({studio.UAT_PRODUCT_CODE}),
    )
    monkeypatch.setattr(
        studio,
        "DOCUMENT_STUDIO_TESTER_WA_IDS",
        frozenset({allowed.whatsapp_id}),
    )

    assert studio.document_studio_available(allowed) is True
    assert studio.document_studio_available(denied) is False
    assert studio.document_studio_available() is False


def test_uat_answers_are_resumable_and_confirmed_as_immutable_revision():
    engine, session_factory = _session_factory()
    db = session_factory()
    try:
        user = User(
            whatsapp_id="919900001111",
            case_id="NS-DOC-UAT",
            name="Synthetic User",
        )
        db.add(user)
        db.flush()

        order = create_or_resume_uat_order(db, user.id)
        assert create_or_resume_uat_order(db, user.id).id == order.id

        inputs = (
            "Synthetic Party A",
            "Synthetic Party B",
            "Pune Test City",
            "11",
        )
        review_ready = False
        for raw_value in inputs:
            question = current_question(order)
            answer = validate_answer(question["key"], raw_value)
            assert answer is not None
            review_ready = save_answer(order, answer)

        assert review_ready is True
        revision = confirm_answers(db, order)
        db.commit()

        assert order.state == "ANSWERS_CONFIRMED"
        assert order.uat_only is True
        assert order.output_classification == UAT_OUTPUT_CLASSIFICATION
        assert order.consent_version
        assert revision.revision_number == 1
        assert len(revision.content_hash) == 64
        assert db.query(DocumentAnswerRevision).count() == 1
        assert {
            event.event_type
            for event in db.query(DocumentAuditEvent).all()
        } == {"UAT_ORDER_CREATED", "UAT_ANSWERS_CONFIRMED"}
        assert db.query(Booking).count() == 0
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_uat_validation_rejects_markup_multiline_and_invalid_terms():
    for question_key in (
        "party_a_label",
        "party_b_label",
        "premises_city",
    ):
        assert validate_answer(question_key, "<unsafe>") is None
        assert validate_answer(question_key, "line one\nline two") is None
        assert validate_answer(question_key, "x") is None

    for invalid_term in ("0", "61", "twelve", "12.5", ""):
        assert validate_answer("term_months", invalid_term) is None

    assert validate_answer("term_months", "12") == "12"


def test_confirmed_uat_order_contains_no_generated_artifact_fields():
    columns = {column.name for column in DocumentOrder.__table__.columns}

    assert "download_url" not in columns
    assert "storage_key" not in columns
    assert "signature" not in columns
    assert "payment_id" not in columns
    assert "generated_document" not in columns
