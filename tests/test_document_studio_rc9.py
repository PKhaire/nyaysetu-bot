"""Focused safety and lifecycle tests for Document Studio RC9."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import DocumentAnswerRevision, DocumentOrder, User, utc_now
from services import document_artifact_vault as artifact_vault
from services import document_catalogue as catalogue
from services.document_artifact_vault import MemoryArtifactVault
from services.document_payment_service import validate_current_document_capture
from services.document_release_service import (
    record_approval,
    release_gate,
    release_manifest,
)
from services.document_renderer import render
from services.document_studio_rc9_service import (
    QUESTION_DEFINITIONS,
    confirm_answers,
    create_or_resume_order,
    current_question,
    document_studio_available,
    save_answer,
    validate_answer,
)
from services.document_workflow import (
    apply_verified_payment,
    build_preview,
    download_links_for_user,
    preview_link_for_user,
    request_payment,
)


@pytest.fixture
def studio_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_s3_vault_forces_virtual_host_addressing(monkeypatch):
    captured = {}

    def fake_client(service_name, **kwargs):
        captured["service_name"] = service_name
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(artifact_vault.boto3, "client", fake_client)
    monkeypatch.setattr(
        artifact_vault,
        "DOCUMENT_STUDIO_S3_BUCKET",
        "nyaysetu-ds-staging-123456789012-ap-south-1-an",
    )
    monkeypatch.setattr(
        artifact_vault,
        "DOCUMENT_STUDIO_S3_ENDPOINT_URL",
        "",
    )

    artifact_vault.S3ArtifactVault()

    assert captured["service_name"] == "s3"
    assert captured["kwargs"]["config"].signature_version == "s3v4"
    assert captured["kwargs"]["config"].s3 == {
        "addressing_style": "virtual"
    }


def _enable_product(monkeypatch, *, price_inr: int = 299) -> None:
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_PRICE_INR", price_inr)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset({catalogue.PRODUCT_CODE}),
    )


def _answer_for(question: dict) -> str:
    if question.get("expected") is not None:
        return str(question["expected"])
    key = str(question["key"])
    fixed = {
        "licensor_full_name": "Asha Patil",
        "licensor_age_years": "44",
        "licensor_notice_address": "12 Safe Road, Pune, Maharashtra",
        "licensee_full_name": "Rohan Joshi",
        "licensee_age_years": "35",
        "licensee_notice_address": "45 Sample Lane, Pune, Maharashtra",
        "premises_unit": "A-101",
        "premises_building": "Sample Residency",
        "premises_floor": "First",
        "premises_street_locality": "Model Colony",
        "premises_city": "Pune",
        "premises_taluka": "Haveli",
        "premises_district": "Pune",
        "premises_pin": "411001",
        "premises_property_reference": "CTS 123",
        "included_areas": "Parking P-1",
        "commencement_date": (
            date.today() + timedelta(days=30)
        ).strftime("%d-%m-%Y"),
        "monthly_licence_fee_inr": "25000",
        "fee_due_day": "5",
        "fee_payment_mode": "BANK_TRANSFER",
        "refundable_deposit_inr": "75000",
        "occupant_count": "2",
        "permitted_occupant_names": "Meera Joshi",
        "furnishing": "SEMI_FURNISHED",
        "inventory_items": "Fan, Bed, Wardrobe",
    }
    return fixed[key]


def _confirmed_order(db, user: User) -> DocumentOrder:
    order = create_or_resume_order(db, user.id)
    for definition in QUESTION_DEFINITIONS:
        assert current_question(order)["key"] == definition["key"]
        answer = validate_answer(
            str(definition["key"]),
            _answer_for(definition),
        )
        assert answer is not None
        save_answer(order, answer)
    confirm_answers(db, order)
    db.flush()
    return order


def _approval_payload(*, decision: str = "APPROVED") -> dict:
    manifest = release_manifest()
    return {
        **manifest,
        "reviewer_name": "Advocate Review User",
        "reviewer_enrolment_ref": "BAR-TEST-001",
        "authority_statement": (
            "Authenticated reviewer decision for this exact package."
        ),
        "authenticated_method": "admin-session-and-recorded-evidence",
        "authenticated_at": (utc_now() - timedelta(minutes=1)).isoformat()
        + "Z",
        "next_review_at": (utc_now() + timedelta(days=180)).isoformat()
        + "Z",
        "decision": decision,
    }


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "id": "plink_document_test_1",
            "short_url": "https://rzp.io/i/document-test",
        }


class _PaymentClient:
    def __init__(self):
        self.payload = None

    def post(self, path, *, json):
        assert path == "/v1/payment_links"
        self.payload = json
        return _Response()


def test_visibility_is_global_and_not_tester_sampled(monkeypatch):
    _enable_product(monkeypatch)

    assert document_studio_available(User(whatsapp_id="919900001111"))
    assert document_studio_available(User(whatsapp_id="919900002222"))
    assert document_studio_available()


def test_questionnaire_confirmation_creates_immutable_revision(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    try:
        user = User(
            whatsapp_id="919900001111",
            case_id="NS-DOCUMENT-RC9",
            name="Synthetic User",
        )
        db.add(user)
        db.flush()

        order = _confirmed_order(db, user)
        db.commit()

        revision = db.query(DocumentAnswerRevision).one()
        assert order.state == "CONFIRMED"
        assert order.uat_only is False
        assert order.output_classification == "SELF_SERVICE_DRAFT"
        assert order.active_revision_number == 1
        assert len(revision.content_hash) == 64
        assert json.loads(revision.answers_json)["expiry_date"]
    finally:
        db.close()


def test_ineligible_answer_routes_out_without_payment(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    try:
        user = User(whatsapp_id="919900003333", case_id="NS-ROUTE-OUT")
        db.add(user)
        db.flush()
        order = create_or_resume_order(db, user.id)

        answer = validate_answer("property_state", "OTHER")
        assert answer == "OTHER"
        assert save_answer(order, answer) is True
        assert order.state == "ROUTED_OUT"
        assert order.razorpay_payment_link_id is None
    finally:
        db.close()


def test_latest_advocate_decision_overrides_older_approval(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    try:
        record_approval(db, _approval_payload(), recorded_by="test-admin")
        db.flush()
        assert release_gate(db).allowed is True

        record_approval(
            db,
            _approval_payload(decision="CHANGES_REQUIRED"),
            recorded_by="test-admin",
        )
        db.flush()

        gate = release_gate(db)
        assert gate.allowed is False
        assert gate.reason_code == "ADVOCATE_DECISION_CHANGES_REQUIRED"
    finally:
        db.close()


def test_confirmed_revision_is_visible_to_immediate_preview(
    monkeypatch,
    studio_db,
):
    """The webhook previews immediately with autoflush explicitly disabled."""

    _enable_product(monkeypatch)
    db = studio_db()
    vault = MemoryArtifactVault()
    try:
        user = User(
            whatsapp_id="919900004443",
            case_id="NS-IMMEDIATE-PREVIEW",
            name="Synthetic Customer",
        )
        db.add(user)
        db.flush()
        order = create_or_resume_order(db, user.id)
        for definition in QUESTION_DEFINITIONS:
            answer = validate_answer(
                str(definition["key"]),
                _answer_for(definition),
            )
            assert answer is not None
            save_answer(order, answer)

        record_approval(db, _approval_payload(), recorded_by="test-admin")
        db.flush()
        confirm_answers(db, order)

        preview = build_preview(db, order, vault=vault)

        assert preview.ok is True
        assert preview.reason_code == "PREVIEW_READY"
        assert db.query(DocumentAnswerRevision).count() == 1
    finally:
        db.close()


def test_preview_payment_and_final_downloads_are_release_gated(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    vault = MemoryArtifactVault()
    try:
        user = User(
            whatsapp_id="919900004444",
            case_id="NS-DOCUMENT-LIFECYCLE",
            name="Synthetic Customer",
        )
        db.add(user)
        db.flush()
        order = _confirmed_order(db, user)

        blocked = build_preview(db, order, vault=vault)
        assert blocked.ok is False
        assert blocked.reason_code == "ADVOCATE_APPROVAL_MISSING"

        record_approval(db, _approval_payload(), recorded_by="test-admin")
        preview = build_preview(db, order, vault=vault)
        assert preview.ok is True
        assert preview_link_for_user(db, order, user, vault=vault).ok

        client = _PaymentClient()
        payment = request_payment(db, order, user, payment_client=client)
        assert payment.ok is True
        assert order.state == "PAYMENT_PENDING"
        assert client.payload["amount"] == order.price_minor
        assert preview_link_for_user(db, order, user, vault=vault).ok

        final = apply_verified_payment(
            db,
            order,
            payment_id="pay_document_test_1",
            payment_amount=order.price_minor,
            payment_currency="INR",
            vault=vault,
        )
        assert final.ok is True
        links = download_links_for_user(db, order, user, vault=vault)
        assert links.ok is True
        assert set(links.value) == {"FINAL_PDF", "FINAL_DOCX"}
    finally:
        db.close()


def test_payment_validation_accepts_exact_capture_and_rejects_refund():
    order = DocumentOrder(
        public_ref="DS-ABCDEF123456",
        user_id=1,
        product_code=catalogue.PRODUCT_CODE,
        template_version=catalogue.TEMPLATE_VERSION,
        active_revision_number=1,
        preview_manifest_hash="a" * 64,
        price_minor=29900,
        currency="INR",
        payment_token="token-123",
        razorpay_payment_link_id="plink_123",
    )
    link = {
        "id": "plink_123",
        "entity": "payment_link",
        "status": "paid",
        "amount": 29900,
        "amount_paid": 29900,
        "currency": "INR",
        "reference_id": "token-123",
        "notes": {
            "document_order_ref": order.public_ref,
            "revision_number": "1",
            "preview_manifest_hash": "a" * 64,
            "product_code": catalogue.PRODUCT_CODE,
        },
        "payments": [
            {
                "payment_id": "pay_123",
                "status": "captured",
                "amount": 29900,
            }
        ],
    }
    payment = {
        "id": "pay_123",
        "entity": "payment",
        "status": "captured",
        "captured": True,
        "amount": 29900,
        "currency": "INR",
        "amount_refunded": 0,
        "refund_status": None,
    }

    assert validate_current_document_capture(order, "pay_123", link, payment) is None
    payment["amount_refunded"] = 100
    assert (
        validate_current_document_capture(order, "pay_123", link, payment)
        == "DOCUMENT_PAYMENT_ALREADY_REFUNDED"
    )


def test_renderer_is_deterministic_and_preview_differs_from_final(monkeypatch):
    _enable_product(monkeypatch)
    product = catalogue.resolve_product()
    answers = {
        str(question["key"]): _answer_for(question)
        for question in QUESTION_DEFINITIONS
    }
    answers["commencement_date"] = (
        date.today() + timedelta(days=30)
    ).isoformat()
    answers["expiry_date"] = (
        date.today() + timedelta(days=364)
    ).isoformat()
    answers.update(
        {
            "non_refundable_consideration_inr": "0",
            "maintenance_payer": "LICENSOR",
            "utilities_payer": "LICENSEE",
            "deposit_refund_business_days": "7",
            "ordinary_notice_days": "30",
            "inspection_notice_hours": "24",
        }
    )

    first = render(product, answers, "FINAL_PDF")
    second = render(product, answers, "FINAL_PDF")
    preview = render(product, answers, "PREVIEW_PDF")
    docx = render(product, answers, "FINAL_DOCX")

    assert first.content_hash == second.content_hash
    assert first.content == second.content
    assert preview.content_hash != first.content_hash
    assert first.content.startswith(b"%PDF")
    assert docx.content.startswith(b"PK")
