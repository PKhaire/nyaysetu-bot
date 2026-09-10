"""Focused safety and lifecycle tests for Draft Studio RC9."""

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
from services.document_payment_service import (
    create_document_payment_link,
    validate_current_document_capture,
)
from services.document_release_service import (
    record_approval,
    release_gate,
    release_manifest,
)
from services.document_renderer import render
from services.document_studio_rc9_service import (
    QUESTION_DEFINITIONS,
    confirm_answers,
    confirmed_snapshot,
    create_or_resume_order,
    current_question,
    document_studio_available,
    edit_section_rows,
    reset_section_for_edit,
    review_message,
    save_answer,
    validate_answer,
)
from services.postal_reference_service import postal_reference_manifest
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
        "licensee_address_same_as_premises": "NO",
        "licensee_notice_address": "45 Sample Lane, Pune, Maharashtra",
        "premises_pin": "411001",
        "premises_address_lines": (
            "Flat A-101, Sample Residency, First Floor, "
            "Model Colony, Pune, Haveli, Pune district"
        ),
        "premises_address_confirmed": "CONFIRM",
        "premises_property_reference": "CTS 123",
        "included_areas": "Parking P-1",
        "commencement_date": (
            date.today() + timedelta(days=30)
        ).strftime("%d-%m-%Y"),
        "monthly_licence_fee_inr": "25000",
        "fee_due_day": "5",
        "fee_payment_mode": "BANK_TRANSFER",
        "refundable_deposit_inr": "75000",
        "optional_details_mode": "ADD",
        "property_reference_present": "YES",
        "included_areas_present": "YES",
        "other_occupants_present": "YES",
        "inventory_present": "YES",
        "permitted_occupant_names": "Meera Joshi",
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


def test_incompatible_active_test_draft_is_superseded_not_resumed(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    try:
        user = User(
            whatsapp_id="919900001111",
            case_id="NS-SCHEMA-REPLACE",
        )
        db.add(user)
        db.flush()
        old_order = create_or_resume_order(db, user.id)
        old_order.schema_hash = "0" * 64
        old_order.template_version = "test-only-v1"
        old_order.state = "DRAFTING"
        old_order.current_step = "premises_unit"
        old_order.draft_answers_json = json.dumps(
            {"premises_unit": "Old synthetic answer"}
        )
        db.flush()

        replacement = create_or_resume_order(db, user.id)

        assert replacement.id != old_order.id
        assert old_order.state == "ABANDONED"
        assert old_order.current_step == "superseded"
        assert old_order.exception_code == "SCHEMA_SUPERSEDED"
        assert replacement.schema_hash == catalogue.resolve_product().schema_hash
        assert replacement.draft_answers_json == "{}"
        assert current_question(replacement)["key"] == "property_eligibility"
    finally:
        db.close()


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


def test_payment_link_replaces_legacy_oversized_reference(monkeypatch):
    _enable_product(monkeypatch)
    user = User(whatsapp_id="919900009999", name="Synthetic Customer")
    product = catalogue.resolve_product()
    order = DocumentOrder(
        public_ref="DS-LEGACY123456",
        user_id=1,
        product_code=catalogue.PRODUCT_CODE,
        template_version=catalogue.TEMPLATE_VERSION,
        state="PREVIEW_READY",
        active_revision_number=1,
        preview_manifest_hash="a" * 64,
        schema_hash=product.schema_hash,
        template_hash=product.template_hash,
        output_classification=product.output_classification,
        price_minor=29_900,
        currency="INR",
        payment_token="x" * 43,
    )
    client = _PaymentClient()

    create_document_payment_link(order, user, client=client)

    assert client.payload["reference_id"] == order.payment_token
    assert len(order.payment_token) <= 40
    assert order.payment_token != "x" * 43


def test_visibility_is_global_and_not_tester_sampled(monkeypatch):
    _enable_product(monkeypatch)

    assert document_studio_available(User(whatsapp_id="919900001111"))
    assert document_studio_available(User(whatsapp_id="919900002222"))
    assert document_studio_available()


def test_grouped_eligibility_reaches_party_details_in_four_answers(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    try:
        user = User(
            whatsapp_id="919900001110",
            case_id="NS-GROUPED-ELIGIBILITY",
        )
        db.add(user)
        db.flush()
        order = create_or_resume_order(db, user.id)

        grouped_keys = (
            "property_eligibility",
            "party_eligibility",
            "authority_dispute_eligibility",
            "standard_product_terms",
        )
        for key in grouped_keys:
            question = current_question(order)
            assert question["key"] == key
            answer = validate_answer(key, "YES")
            assert answer == "YES"
            assert save_answer(order, answer) is False

        assert current_question(order)["key"] == "licensor_full_name"
        keys = {str(question["key"]) for question in QUESTION_DEFINITIONS}
        assert keys.isdisjoint(
            {
                "property_state",
                "premises_use",
                "completed_premises",
                "party_structure",
                "parties_adult_competent",
                "self_represented_parties",
                "licensor_authority_confirmed",
                "existing_dispute",
                "conflicting_occupant",
                "term_months",
                "standard_terms_accepted",
                "non_refundable_zero",
                "external_steps_understood",
                "facts_uncontested",
            }
        )
    finally:
        db.close()


def test_single_schema_does_not_collect_unused_or_repeated_answers():
    keys = {str(question["key"]) for question in QUESTION_DEFINITIONS}

    assert keys.isdisjoint(
        {
            "furnishing",
            "no_lock_in_ack",
            "possession_process_ack",
            "no_transfer_ack",
            "lawful_use_ack",
        }
    )


def test_negative_optional_choices_skip_detail_questions(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    try:
        user = User(
            whatsapp_id="919900001109",
            case_id="NS-CONDITIONAL-QUESTIONS",
        )
        db.add(user)
        db.flush()
        order = create_or_resume_order(db, user.id)

        order.current_step = "optional_details_mode"
        assert validate_answer(order.current_step, "ADD") == "ADD"
        save_answer(order, "ADD")
        assert current_question(order)["key"] == "property_reference_present"

        assert validate_answer(order.current_step, "NO") == "NO"
        save_answer(order, "NO")
        assert current_question(order)["key"] == "included_areas_present"

        save_answer(order, "NO")
        assert current_question(order)["key"] == "other_occupants_present"

        save_answer(order, "NO")
        assert current_question(order)["key"] == "inventory_present"

        assert save_answer(order, "NO") is True
        assert order.current_step == "review"
    finally:
        db.close()


def test_complete_premises_address_can_be_reused_for_licensee_notice():
    keys = {str(question["key"]) for question in QUESTION_DEFINITIONS}
    assert {
        "premises_pin",
        "premises_address_lines",
        "premises_address_confirmed",
        "licensee_address_same_as_premises",
    }.issubset(keys)
    assert keys.isdisjoint(
        {
            "premises_unit",
            "premises_building",
            "premises_floor",
            "premises_street_locality",
            "premises_city",
            "premises_taluka",
            "premises_district",
        }
    )

    order = DocumentOrder(
        public_ref="DS-ADDRESS-V2",
        draft_answers_json=json.dumps(
            {
                "premises_address_lines": (
                    "Flat A-101, Sample Residency, First Floor, "
                    "Model Colony, Pune, Haveli, Pune district"
                ),
                "premises_pin": "411001",
                "licensee_address_same_as_premises": "YES",
            }
        ),
    )

    snapshot = confirmed_snapshot(order)
    expected = (
        "Flat A-101, Sample Residency, First Floor, Model Colony, Pune, "
        "Haveli, Pune district, Maharashtra - 411001"
    )
    assert snapshot["rendered_premises_address"] == expected
    assert snapshot["licensee_notice_address"] == expected
    assert expected in review_message(order)


def test_pin_assistance_and_address_confirmation_remain_customer_controlled():
    order = DocumentOrder(
        public_ref="DS-PIN-ASSISTANCE",
        current_step="premises_address_lines",
        draft_answers_json=json.dumps({"premises_pin": "411001"}),
    )

    address_question = current_question(order)
    assert address_question["key"] == "premises_address_lines"
    assert "Pune" in address_question["prompt"]
    assert "Pune City" in address_question["prompt"]
    assert "type the complete address" in address_question["prompt"].lower()

    order.draft_answers_json = json.dumps(
        {
            "premises_pin": "411001",
            "premises_address_lines": (
                "Flat A-101, Sample Residency, Model Colony, Pune"
            ),
        }
    )
    order.current_step = "premises_address_confirmed"

    confirmation_question = current_question(order)
    assert confirmation_question["key"] == "premises_address_confirmed"
    assert (
        "Flat A-101, Sample Residency, Model Colony, Pune, "
        "Maharashtra - 411001"
    ) in confirmation_question["prompt"]
    assert confirmation_question["options"] == (
        ("CONFIRM", "Confirm"),
        ("EDIT", "Edit address"),
    )


def test_unknown_maharashtra_pin_does_not_block_manual_address_entry():
    order = DocumentOrder(
        public_ref="DS-PIN-MANUAL",
        current_step="premises_address_lines",
        draft_answers_json=json.dumps({"premises_pin": "999999"}),
    )

    question = current_question(order)

    assert question["key"] == "premises_address_lines"
    assert "could not suggest" in question["prompt"].lower()
    assert "type the complete address" in question["prompt"].lower()


def test_packaged_postal_reference_is_versioned_in_release_inputs():
    manifest = postal_reference_manifest()

    assert manifest["available"] is True
    assert manifest["record_count"] == 1666
    assert len(manifest["content_hash"]) == 64
    assert manifest["source"]["repository"] == (
        "https://github.com/IndiaPost/pin"
    )
    assert manifest["source"]["revision"] == (
        "9903190eb2073826f869f0c384bb83a34a21ebd5"
    )


def test_typical_path_reaches_review_without_irrelevant_detail_questions(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    try:
        user = User(
            whatsapp_id="919900001108",
            case_id="NS-TYPICAL-PATH",
        )
        db.add(user)
        db.flush()
        order = create_or_resume_order(db, user.id)
        answered_keys = []
        simple_choices = {
            "licensee_address_same_as_premises": "YES",
            "optional_details_mode": "SKIP",
        }

        while order.current_step != "review":
            question = current_question(order)
            key = str(question["key"])
            raw_answer = simple_choices.get(key, _answer_for(question))
            answer = validate_answer(key, raw_answer)
            assert answer is not None
            answered_keys.append(key)
            save_answer(order, answer)

        assert len(answered_keys) == 19
        assert set(answered_keys).isdisjoint(
            {
                "licensee_notice_address",
                "property_reference_present",
                "premises_property_reference",
                "included_areas_present",
                "included_areas",
                "other_occupants_present",
                "permitted_occupant_names",
                "inventory_present",
                "inventory_items",
            }
        )
        snapshot = confirmed_snapshot(order)
        assert snapshot["occupant_count"] == "1"
        assert snapshot["inventory_items"] == "NONE"
        assert snapshot["licensee_notice_address"] == snapshot[
            "rendered_premises_address"
        ]
    finally:
        db.close()


def test_questions_expose_five_section_progress_labels(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    try:
        user = User(
            whatsapp_id="919900001107",
            case_id="NS-SECTION-PROGRESS",
        )
        db.add(user)
        db.flush()
        order = create_or_resume_order(db, user.id)

        first = current_question(order)
        assert first["section"] == "eligibility"
        assert first["section_title"] == "Eligibility"
        assert first["section_number"] == 1
        assert first["section_total"] == 5

        for key in (
            "property_eligibility",
            "party_eligibility",
            "authority_dispute_eligibility",
            "standard_product_terms",
        ):
            assert current_question(order)["key"] == key
            save_answer(order, "YES")

        parties = current_question(order)
        assert parties["section"] == "parties"
        assert parties["section_title"] == "Parties"
        assert parties["section_number"] == 2
    finally:
        db.close()


def test_section_edit_preserves_answers_from_other_sections(
    monkeypatch,
    studio_db,
):
    _enable_product(monkeypatch)
    db = studio_db()
    try:
        user = User(
            whatsapp_id="919900001106",
            case_id="NS-SECTION-EDIT",
        )
        db.add(user)
        db.flush()
        order = create_or_resume_order(db, user.id)
        choices = {
            "licensee_address_same_as_premises": "YES",
            "optional_details_mode": "SKIP",
        }
        while order.current_step != "review":
            question = current_question(order)
            answer = validate_answer(
                str(question["key"]),
                choices.get(str(question["key"]), _answer_for(question)),
            )
            assert answer is not None
            save_answer(order, answer)

        before = json.loads(order.draft_answers_json)
        rows = edit_section_rows()
        assert [row["id"] for row in rows] == [
            "doc_edit_section::eligibility",
            "doc_edit_section::parties",
            "doc_edit_section::premises",
            "doc_edit_section::agreement",
            "doc_edit_section::optional",
        ]

        assert reset_section_for_edit(db, order, "parties") is True

        after = json.loads(order.draft_answers_json)
        assert "licensor_full_name" not in after
        assert "licensee_age_years" not in after
        assert after["premises_pin"] == before["premises_pin"]
        assert after["monthly_licence_fee_inr"] == before[
            "monthly_licence_fee_inr"
        ]
        assert order.current_step == "licensor_full_name"
        assert order.state == "DRAFTING"

        order.draft_answers_json = json.dumps(before)
        order.current_step = "review"
        assert reset_section_for_edit(db, order, "eligibility") is True
        for key in (
            "property_eligibility",
            "party_eligibility",
            "authority_dispute_eligibility",
            "standard_product_terms",
        ):
            assert current_question(order)["key"] == key
            review_ready = save_answer(order, "YES")
        assert review_ready is True
        assert order.current_step == "review"
        assert order.state == "DRAFTING"
    finally:
        db.close()


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

        answer = validate_answer("property_eligibility", "NO")
        assert answer == "NO"
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
        assert client.payload["reference_id"] == order.payment_token
        assert len(order.payment_token) <= 40
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
        "status": "paid",
        "accept_partial": False,
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
    link["entity"] = "order"
    assert (
        validate_current_document_capture(order, "pay_123", link, payment)
        == "DOCUMENT_PAYMENT_LINK_ENTITY_MISMATCH"
    )
    link.pop("entity")
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
