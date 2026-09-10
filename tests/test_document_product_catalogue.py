"""Characterization tests for the Draft Studio product seam."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    DocumentArtifact,
    DocumentOrder,
    DocumentTemplateApproval,
    User,
    utc_now,
)
from services import document_catalogue as catalogue
from services.document_payment_service import create_document_payment_link
from services.document_release_service import (
    release_manifest,
    release_readiness,
)
from services.document_renderer import golden_hashes
from services.document_studio_rc9_service import (
    parse_product_id,
    parse_product_number,
    parse_product_page_id,
    product_rows,
)
from services.document_workflow import build_preview, download_links_for_user


EXPECTED_PRODUCT_IDENTITY = {
    "code": "mh_residential_leave_licence_11m_self_service",
    "template_version": "mh-ll-en-2026-08-candidate-1",
    "schema_version": "mh-ll-questionnaire-2026-09-v3",
    "output_classification": "SELF_SERVICE_DRAFT",
    "template_hash": (
        "cb860be339805588afb352560ea66a32f91c1acabd6af47fc041e13650dc5535"
    ),
    "schema_hash": (
        "edd95798ee85f898a9de782599a3fd53ee15abdb3bf354a130cf1787f5a63021"
    ),
    "aggregate_hash": (
        "1b2004d5d3c64a4bd66e67417ffe260e48a164d01b2ad23f9556a92d7c1edc6e"
    ),
    "golden_pdf_hash": (
        "f37f573125c7d407a05814922c6a7091c4fe1a80e40502f42d6042c848029c42"
    ),
    "golden_docx_hash": (
        "6a2cfd9a59d19a3ebe8212bab116d5e63281b479f2b7c936c76fb5e4cb3a134d"
    ),
}


def _enable_current_product(monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_PRICE_INR", 299)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset({catalogue.PRODUCT_CODE}),
    )


def _enable_synthetic_product(monkeypatch) -> str:
    """Install a non-legal definition for this test process only."""

    code = "synthetic_non_legal_test_product"
    current = catalogue._PRODUCT_DEFINITIONS[catalogue.PRODUCT_CODE]
    synthetic = replace(
        current,
        code=code,
        display_name="Synthetic test form",
        display_name_key="synthetic_test_product_name",
        list_description="Test-only | INR {price_inr}",
        list_description_key="synthetic_test_product_description",
        template_version="synthetic-template-v1",
        schema_version="synthetic-schema-v1",
        output_classification="SYNTHETIC_TEST_ONLY",
        jurisdiction="Automated tests only",
        payment_description="Synthetic test payment",
        turnaround_label="Synthetic",
    )
    monkeypatch.setattr(
        catalogue,
        "_PRODUCT_DEFINITIONS",
        {
            catalogue.PRODUCT_CODE: current,
            code: synthetic,
        },
    )
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset({catalogue.PRODUCT_CODE, code}),
    )
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_PRICES_INR_CONFIGURED",
        True,
    )
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_PRICES_INR",
        {catalogue.PRODUCT_CODE: 299, code: 101},
    )
    return code


def test_existing_product_identity_and_artifacts_are_frozen(monkeypatch):
    _enable_current_product(monkeypatch)

    product = catalogue.resolve_product(catalogue.PRODUCT_CODE)
    manifest = release_manifest(catalogue.PRODUCT_CODE)

    for field in (
        "code",
        "template_version",
        "schema_version",
        "output_classification",
        "template_hash",
        "schema_hash",
        "aggregate_hash",
    ):
        assert getattr(product, field) == EXPECTED_PRODUCT_IDENTITY[field]
    assert manifest["golden_pdf_hash"] == EXPECTED_PRODUCT_IDENTITY[
        "golden_pdf_hash"
    ]
    assert manifest["golden_docx_hash"] == EXPECTED_PRODUCT_IDENTITY[
        "golden_docx_hash"
    ]


def test_registry_exposes_only_enabled_allowlisted_products(monkeypatch):
    _enable_current_product(monkeypatch)

    assert catalogue.registered_product_codes() == (catalogue.PRODUCT_CODE,)
    assert tuple(product.code for product in catalogue.visible_products()) == (
        catalogue.PRODUCT_CODE,
    )

    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset(),
    )
    assert catalogue.visible_products() == ()


def test_runtime_registry_membership_is_immutable():
    with pytest.raises(TypeError):
        catalogue._PRODUCT_DEFINITIONS["unexpected_product"] = (
            catalogue._PRODUCT_DEFINITIONS[catalogue.PRODUCT_CODE]
        )


@pytest.mark.parametrize(
    ("definitions", "reason_code"),
    (
        (
            lambda current: {
                current.code: current,
                "duplicate_product": current,
            },
            "DUPLICATE_DOCUMENT_PRODUCT",
        ),
        (
            lambda current: {
                current.code: replace(current, display_name=""),
            },
            "INVALID_PRODUCT_DEFINITION",
        ),
        (
            lambda current: {"wrong_registry_key": current},
            "INVALID_PRODUCT_DEFINITION",
        ),
    ),
)
def test_invalid_registry_entries_fail_global_configuration(
    monkeypatch,
    definitions,
    reason_code,
):
    current = catalogue._PRODUCT_DEFINITIONS[catalogue.PRODUCT_CODE]
    monkeypatch.setattr(
        catalogue,
        "_PRODUCT_DEFINITIONS",
        definitions(current),
    )

    configuration = catalogue.catalogue_configuration(
        enabled=True,
        allowlist=frozenset({catalogue.PRODUCT_CODE}),
        prices_inr={catalogue.PRODUCT_CODE: 299},
    )

    assert configuration.ok is False
    assert configuration.reason_code == reason_code
    assert configuration.enabled_product_codes == ()


def test_unknown_product_is_never_resolved_or_visible(monkeypatch):
    _enable_current_product(monkeypatch)

    with pytest.raises(KeyError, match="unknown_document_product"):
        catalogue.resolve_product("unknown_product")
    assert catalogue.customer_visible("unknown_product") is False


def test_synthetic_product_exercises_global_catalogue_routing_only_in_test(
    monkeypatch,
):
    synthetic_code = _enable_synthetic_product(monkeypatch)

    configuration = catalogue.catalogue_configuration()
    products = catalogue.visible_products()
    rows = product_rows(None, lambda _user, key: key)

    assert configuration.ok is True
    assert configuration.enabled_product_codes == (
        catalogue.PRODUCT_CODE,
        synthetic_code,
    )
    assert [product.code for product in products] == [
        catalogue.PRODUCT_CODE,
        synthetic_code,
    ]
    assert rows[1]["title"] == "2. Synthetic test form"
    assert parse_product_id(rows[1]["id"]) == synthetic_code
    assert product_rows(object(), lambda _user, key: key) == rows


def test_distinct_synthetic_package_cannot_reuse_current_product_snapshot(
    monkeypatch,
    tmp_path,
):
    synthetic_code = _enable_synthetic_product(monkeypatch)
    current_definition = catalogue._PRODUCT_DEFINITIONS[
        catalogue.PRODUCT_CODE
    ]
    synthetic_definition = catalogue._PRODUCT_DEFINITIONS[synthetic_code]
    synthetic_template = tmp_path / "synthetic-template.md"
    synthetic_template.write_bytes(
        current_definition.template_path.read_bytes()
        + b"\n\nSynthetic automated package marker.\n"
    )
    monkeypatch.setattr(
        catalogue,
        "_PRODUCT_DEFINITIONS",
        {
            catalogue.PRODUCT_CODE: current_definition,
            synthetic_code: replace(
                synthetic_definition,
                template_path=synthetic_template,
                schema_bytes=lambda: b'{"synthetic_schema":true}',
            ),
        },
    )
    current_product = catalogue.resolve_product(catalogue.PRODUCT_CODE)
    synthetic_product = catalogue.resolve_product(synthetic_code)
    order = DocumentOrder(
        public_ref="DS-CROSS-PRODUCT",
        user_id=1,
        product_code=synthetic_product.code,
        template_version=current_product.template_version,
        state="CONFIRMED",
        active_revision_number=1,
        schema_hash=current_product.schema_hash,
        template_hash=current_product.template_hash,
        output_classification=current_product.output_classification,
        price_minor=synthetic_product.price_minor,
        currency=synthetic_product.currency,
    )

    result = build_preview(None, order)

    assert synthetic_product.schema_hash != current_product.schema_hash
    assert synthetic_product.template_hash != current_product.template_hash
    assert synthetic_product.aggregate_hash != current_product.aggregate_hash
    assert result.ok is False
    assert result.reason_code == "DOCUMENT_PACKAGE_SNAPSHOT_MISMATCH"

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        user = User(whatsapp_id="919900006666", name="Synthetic Customer")
        db.add(user)
        db.flush()
        current_order = DocumentOrder(
            public_ref="DS-CURRENT-ARTIFACTS",
            user_id=user.id,
            product_code=current_product.code,
            template_version=current_product.template_version,
            state="FINAL_AVAILABLE",
            active_revision_number=1,
            schema_hash=current_product.schema_hash,
            template_hash=current_product.template_hash,
            output_classification=current_product.output_classification,
            price_minor=current_product.price_minor,
            currency=current_product.currency,
            final_available_until=utc_now() + timedelta(days=1),
        )
        synthetic_order = DocumentOrder(
            public_ref="DS-SYNTHETIC-NO-ARTIFACTS",
            user_id=user.id,
            product_code=synthetic_product.code,
            template_version=synthetic_product.template_version,
            state="FINAL_AVAILABLE",
            active_revision_number=1,
            schema_hash=synthetic_product.schema_hash,
            template_hash=synthetic_product.template_hash,
            output_classification=synthetic_product.output_classification,
            price_minor=synthetic_product.price_minor,
            currency=synthetic_product.currency,
            final_available_until=utc_now() + timedelta(days=1),
        )
        db.add_all((current_order, synthetic_order))
        db.flush()
        for artifact_kind in ("FINAL_PDF", "FINAL_DOCX"):
            db.add(
                DocumentArtifact(
                    public_ref=f"DA-{artifact_kind}",
                    document_order_id=current_order.id,
                    revision_number=1,
                    artifact_kind=artifact_kind,
                    state="AVAILABLE",
                    storage_provider="S3",
                    bucket="synthetic-private-bucket",
                    object_key=f"current/{artifact_kind.lower()}",
                    content_type="application/octet-stream",
                    size_bytes=10,
                    content_hash="a" * 64,
                    manifest_hash="b" * 64,
                    renderer_version=current_product.renderer_version,
                    expires_at=utc_now() + timedelta(days=1),
                )
            )
        db.flush()

        downloads = download_links_for_user(db, synthetic_order, user)

        assert downloads.ok is False
        assert downloads.reason_code == "FINAL_ARTIFACTS_INCOMPLETE"
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_product_pages_stay_within_provider_limit_and_accept_numbers(
    monkeypatch,
):
    current = catalogue._PRODUCT_DEFINITIONS[catalogue.PRODUCT_CODE]
    definitions = {catalogue.PRODUCT_CODE: current}
    for index in range(1, 18):
        code = f"synthetic_product_{index:02d}"
        definitions[code] = replace(
            current,
            code=code,
            display_name=f"Synthetic {index:02d}",
            display_name_key=f"synthetic_product_{index:02d}_name",
            list_description="Test only | INR {price_inr}",
            list_description_key=f"synthetic_product_{index:02d}_description",
            template_version=f"synthetic-template-{index:02d}",
            schema_version=f"synthetic-schema-{index:02d}",
            output_classification="SYNTHETIC_TEST_ONLY",
        )
    monkeypatch.setattr(catalogue, "_PRODUCT_DEFINITIONS", definitions)
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset(definitions),
    )
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_PRICES_INR_CONFIGURED",
        True,
    )
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_PRICES_INR",
        {code: 100 + index for index, code in enumerate(definitions)},
    )

    first = product_rows(None, lambda _user, key: key, page=0)
    middle = product_rows(None, lambda _user, key: key, page=1)
    last = product_rows(None, lambda _user, key: key, page=2)

    assert len(first) == 9
    assert len(middle) == 10
    assert len(last) == 3
    assert parse_product_page_id(first[-1]["id"]) == 1
    assert parse_product_page_id(middle[-1]["id"]) == 2
    assert parse_product_number("1", page=1) == "synthetic_product_08"
    assert parse_product_number("9", page=1) is None


@pytest.mark.parametrize(
    ("allowlist", "prices", "reason_code"),
    (
        (
            frozenset({catalogue.PRODUCT_CODE, "unknown_product"}),
            {catalogue.PRODUCT_CODE: 299, "unknown_product": 101},
            "UNKNOWN_DOCUMENT_PRODUCT",
        ),
        (
            frozenset(
                {
                    catalogue.PRODUCT_CODE,
                    "synthetic_non_legal_test_product",
                }
            ),
            {catalogue.PRODUCT_CODE: 299},
            "PRICE_NOT_CONFIGURED",
        ),
        (
            frozenset({catalogue.PRODUCT_CODE}),
            {
                catalogue.PRODUCT_CODE: 299,
                "synthetic_non_legal_test_product": 101,
            },
            "PRICE_CONFIGURED_FOR_DISABLED_PRODUCT",
        ),
        (
            frozenset({catalogue.PRODUCT_CODE}),
            {catalogue.PRODUCT_CODE: 100001},
            "PRICE_NOT_CONFIGURED",
        ),
    ),
)
def test_partial_catalogue_configuration_hides_every_product(
    monkeypatch,
    allowlist,
    prices,
    reason_code,
):
    _enable_synthetic_product(monkeypatch)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        allowlist,
    )
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_PRICES_INR",
        prices,
    )

    configuration = catalogue.catalogue_configuration()

    assert configuration.ok is False
    assert configuration.reason_code == reason_code
    assert catalogue.visible_products() == ()
    assert catalogue.customer_visible(catalogue.PRODUCT_CODE) is False


def test_release_readiness_reports_each_enabled_product(monkeypatch):
    synthetic_code = _enable_synthetic_product(monkeypatch)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    try:
        product = catalogue.resolve_product(catalogue.PRODUCT_CODE)
        pdf_hash, docx_hash = golden_hashes(product)
        db.add(
            DocumentTemplateApproval(
                product_code=product.code,
                template_version=product.template_version,
                reviewer_name="Synthetic Advocate",
                reviewer_enrolment_ref="TEST/0001",
                authority_statement="Synthetic automated test approval",
                decision="APPROVED",
                conditions=None,
                template_aggregate_hash=product.aggregate_hash,
                golden_pdf_hash=pdf_hash,
                golden_docx_hash=docx_hash,
                authenticated_method="synthetic_test",
                authenticated_at=utc_now() - timedelta(days=1),
                next_review_at=utc_now() + timedelta(days=30),
                recorded_by="automated-test",
            )
        )
        db.flush()

        readiness = release_readiness(db)

        assert readiness["ok"] is False
        assert readiness["reason_code"] == "ADVOCATE_APPROVAL_MISSING"
        assert readiness["products"][catalogue.PRODUCT_CODE]["ok"] is True
        assert readiness["products"][synthetic_code] == {
            "ok": False,
            "reason_code": "ADVOCATE_APPROVAL_MISSING",
            "template_version": "synthetic-template-v1",
            "output_classification": "SYNTHETIC_TEST_ONLY",
        }
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_disabled_product_cannot_create_preview_or_payment(monkeypatch):
    _enable_current_product(monkeypatch)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset(),
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        product = catalogue.resolve_product(catalogue.PRODUCT_CODE)
        order = DocumentOrder(
            public_ref="DS-DISABLED-PRODUCT",
            user_id=1,
            product_code=product.code,
            template_version=product.template_version,
            state="PREVIEW_READY",
            active_revision_number=1,
            preview_manifest_hash="a" * 64,
            schema_hash=product.schema_hash,
            template_hash=product.template_hash,
            output_classification=product.output_classification,
            price_minor=product.price_minor,
            currency=product.currency,
        )
        user = User(whatsapp_id="919900008888", name="Synthetic Customer")

        preview = build_preview(db, order)

        assert preview.ok is False
        assert preview.reason_code == "NO_PRODUCTS_ENABLED"
        with pytest.raises(ValueError, match="no_products_enabled"):
            create_document_payment_link(order, user, product=product)
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_order_workflow_fails_closed_for_unknown_product():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    try:
        user = User(whatsapp_id="919900001234", case_id="NS-PRODUCT-SEAM")
        db.add(user)
        db.flush()
        order = DocumentOrder(
            public_ref="DS-PRODUCT-SEAM",
            user_id=user.id,
            product_code="unknown_product",
            template_version="unknown-v1",
            state="CONFIRMED",
            current_step="review",
            draft_answers_json="{}",
            output_classification="SELF_SERVICE_DRAFT",
            active_revision_number=1,
            schema_hash="a" * 64,
            template_hash="b" * 64,
            price_minor=29_900,
            currency="INR",
        )
        db.add(order)
        db.flush()

        result = build_preview(db, order)

        assert result.ok is False
        assert result.reason_code == "UNKNOWN_DOCUMENT_PRODUCT"
        assert order.release_status == "BLOCKED"
        assert order.exception_code == "UNKNOWN_DOCUMENT_PRODUCT"
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_payment_adapter_rejects_order_product_mismatch(monkeypatch):
    _enable_current_product(monkeypatch)
    product = catalogue.resolve_product(catalogue.PRODUCT_CODE)
    user = User(whatsapp_id="919900009999", name="Synthetic Customer")
    order = DocumentOrder(
        public_ref="DS-PRODUCT-MISMATCH",
        user_id=1,
        product_code="another_product",
        template_version=product.template_version,
        state="PREVIEW_READY",
        active_revision_number=1,
        preview_manifest_hash="a" * 64,
        price_minor=product.price_minor,
        currency=product.currency,
    )

    with pytest.raises(ValueError, match="document_product_mismatch"):
        create_document_payment_link(order, user, product=product)


@pytest.mark.parametrize(
    "missing_field",
    (
        "template_version",
        "schema_hash",
        "template_hash",
        "output_classification",
    ),
)
def test_preview_and_payment_reject_incomplete_package_snapshot(
    monkeypatch,
    missing_field,
):
    _enable_current_product(monkeypatch)
    product = catalogue.resolve_product(catalogue.PRODUCT_CODE)
    values = {
        "template_version": product.template_version,
        "schema_hash": product.schema_hash,
        "template_hash": product.template_hash,
        "output_classification": product.output_classification,
    }
    values[missing_field] = None
    order = DocumentOrder(
        public_ref=f"DS-INCOMPLETE-{missing_field.upper()}",
        user_id=1,
        product_code=product.code,
        state="CONFIRMED",
        active_revision_number=1,
        preview_manifest_hash="a" * 64,
        price_minor=product.price_minor,
        currency=product.currency,
        **values,
    )
    user = User(whatsapp_id="919900007777", name="Synthetic Customer")

    preview = build_preview(None, order)

    assert preview.ok is False
    assert preview.reason_code == "DOCUMENT_PACKAGE_SNAPSHOT_MISMATCH"
    order.state = "PREVIEW_READY"
    with pytest.raises(ValueError, match="document_product_snapshot_mismatch"):
        create_document_payment_link(order, user, product=product)
