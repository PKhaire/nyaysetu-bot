"""Immutable, fail-closed catalogue for Draft Studio products.

The module deliberately exposes a small product interface. Publication,
question ordering, price snapshots and content hashes are owned here rather
than spread across Flask/WhatsApp handlers.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable

from config import (
    DOCUMENT_STUDIO_ENABLED,
    DOCUMENT_STUDIO_PRICE_INR,
    DOCUMENT_STUDIO_PRODUCT_ALLOWLIST,
    DOCUMENT_STUDIO_PRODUCT_PRICES_INR,
    DOCUMENT_STUDIO_PRODUCT_PRICES_INR_CONFIGURED,
)


PRODUCT_CODE = "mh_residential_leave_licence_11m_self_service"
TEMPLATE_VERSION = "mh-ll-en-2026-08-candidate-1"
OUTPUT_CLASSIFICATION = "SELF_SERVICE_DRAFT"
SCHEMA_VERSION = "mh-ll-questionnaire-2026-09-v3"
RENDERER_VERSION = "nyaysetu-deterministic-renderer-1"

_REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = (
    _REPO_ROOT
    / "docs"
    / "document-studio"
    / "16-residential-leave-license-candidate-template.md"
)


@dataclass(frozen=True)
class DocumentProduct:
    code: str
    display_name: str
    display_name_key: str
    list_description: str
    list_description_key: str
    selection_overview: str
    selection_overview_key: str
    start_label: str
    start_label_key: str
    template_version: str
    schema_version: str
    output_classification: str
    language: str
    jurisdiction: str
    price_model: str
    price_minor: int
    currency: str
    payment_description: str
    turnaround_label: str
    template_hash: str
    schema_hash: str
    aggregate_hash: str
    renderer_version: str
    template_path: Path
    golden_answers: Callable[[], dict[str, object]]

    def matches_package_snapshot(
        self,
        *,
        template_version: str | None,
        schema_hash: str | None,
        template_hash: str | None,
        output_classification: str | None,
    ) -> bool:
        """Require every immutable package field to match exactly."""

        return (
            template_version == self.template_version
            and schema_hash == self.schema_hash
            and template_hash == self.template_hash
            and output_classification == self.output_classification
        )


@dataclass(frozen=True)
class _DocumentProductDefinition:
    """Private product inputs resolved through the catalogue interface."""

    code: str
    display_name: str
    display_name_key: str
    list_description: str
    list_description_key: str
    selection_overview: str
    selection_overview_key: str
    start_label: str
    start_label_key: str
    template_version: str
    schema_version: str
    output_classification: str
    language: str
    jurisdiction: str
    price_model: str
    currency: str
    payment_description: str
    turnaround_label: str
    renderer_version: str
    template_path: Path
    schema_bytes: Callable[[], bytes]
    golden_answers: Callable[[], dict[str, object]]


@dataclass(frozen=True)
class CatalogueConfiguration:
    """Non-secret validation result for the global product catalogue."""

    ok: bool
    reason_code: str
    enabled_product_codes: tuple[str, ...]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_template_bytes(value: bytes) -> bytes:
    """Make text-template identity independent of checkout line endings."""

    return value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _questionnaire_schema_bytes() -> bytes:
    # Import lazily so the catalogue remains usable by migrations and config
    # checks without creating a module cycle.
    from services.document_studio_rc9_service import QUESTION_DEFINITIONS
    from services.postal_reference_service import postal_reference_manifest

    serializable = [
        {
            key: value
            for key, value in question.items()
            if key not in {"validator"}
        }
        for question in QUESTION_DEFINITIONS
    ]
    return json.dumps(
        {
            "questions": serializable,
            "postal_reference": postal_reference_manifest(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _golden_answers() -> dict[str, object]:
    return {
        "licensor_full_name": "Asha Test Licensor",
        "licensor_age_years": "45",
        "licensor_notice_address": (
            "1 Synthetic Road, Pune, Maharashtra 411001"
        ),
        "licensee_full_name": "Ravi Test Licensee",
        "licensee_age_years": "32",
        "licensee_notice_address": (
            "2 Example Lane, Pune, Maharashtra 411002"
        ),
        "premises_address_lines": (
            "Flat 101, Sample Residency, First Floor, Test Road, "
            "Shivajinagar, Pune, Haveli, Pune district"
        ),
        "premises_pin": "411003",
        "premises_property_reference": "NONE",
        "included_areas": "Parking P-1",
        "commencement_date": "2026-09-01",
        "expiry_date": "2027-07-31",
        "monthly_licence_fee_inr": "25000",
        "fee_due_day": "5",
        "fee_payment_mode": "UPI",
        "refundable_deposit_inr": "75000",
        "permitted_occupant_names": "NONE",
        "inventory_items": (
            "Ceiling fan - working, Wardrobe - good condition"
        ),
    }


_PRODUCT_DEFINITIONS: Mapping[str, _DocumentProductDefinition] = (
    MappingProxyType({
    PRODUCT_CODE: _DocumentProductDefinition(
        code=PRODUCT_CODE,
        display_name="Residential agreement",
        display_name_key="document_uat_product",
        list_description=(
            "Self-service | Maharashtra | English | INR {price_inr} | instant"
        ),
        list_description_key="document_mh_ll_product_desc",
        selection_overview=(
            "Prepare an English self-service draft for one 11-month "
            "residential leave-and-licence arrangement in Maharashtra. "
            "NyaySetu does not verify identity, title or authority. "
            "Ineligible or disputed matters are routed to consultation "
            "before payment."
        ),
        selection_overview_key="document_uat_overview",
        start_label="Check eligibility",
        start_label_key="document_product_start",
        template_version=TEMPLATE_VERSION,
        schema_version=SCHEMA_VERSION,
        output_classification=OUTPUT_CLASSIFICATION,
        language="en",
        jurisdiction="Maharashtra, India",
        price_model="FIXED",
        currency="INR",
        payment_description="NyaySetu Draft Studio final PDF and DOCX",
        turnaround_label="Instant after payment",
        renderer_version=RENDERER_VERSION,
        template_path=TEMPLATE_PATH,
        schema_bytes=_questionnaire_schema_bytes,
        golden_answers=_golden_answers,
    )
    })
)

_PRODUCT_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{2,79}$")


def _registry_validation_error() -> str | None:
    """Reject malformed internal entries before any product becomes visible."""

    if not isinstance(_PRODUCT_DEFINITIONS, Mapping) or not _PRODUCT_DEFINITIONS:
        return "INVALID_PRODUCT_REGISTRY"
    seen_codes: set[str] = set()
    for key, definition in _PRODUCT_DEFINITIONS.items():
        if not isinstance(definition, _DocumentProductDefinition):
            return "INVALID_PRODUCT_DEFINITION"
        if definition.code in seen_codes:
            return "DUPLICATE_DOCUMENT_PRODUCT"
        seen_codes.add(definition.code)
        if key != definition.code or not _PRODUCT_CODE_PATTERN.fullmatch(key):
            return "INVALID_PRODUCT_DEFINITION"
        required_text = (
            definition.display_name,
            definition.display_name_key,
            definition.list_description,
            definition.list_description_key,
            definition.selection_overview,
            definition.selection_overview_key,
            definition.start_label,
            definition.start_label_key,
            definition.template_version,
            definition.schema_version,
            definition.output_classification,
            definition.language,
            definition.jurisdiction,
            definition.price_model,
            definition.currency,
            definition.payment_description,
            definition.turnaround_label,
            definition.renderer_version,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required_text):
            return "INVALID_PRODUCT_DEFINITION"
        if (
            not isinstance(definition.template_path, Path)
            or not definition.template_path.is_file()
            or not callable(definition.schema_bytes)
            or not callable(definition.golden_answers)
        ):
            return "INVALID_PRODUCT_DEFINITION"
    return None


def registered_product_codes() -> tuple[str, ...]:
    """Return stable registered codes without exposing registry internals."""

    return tuple(_PRODUCT_DEFINITIONS)


def _runtime_prices_inr() -> dict[str, int]:
    """Return effective prices while preserving the RC14 environment key."""

    if DOCUMENT_STUDIO_PRODUCT_PRICES_INR_CONFIGURED:
        return dict(DOCUMENT_STUDIO_PRODUCT_PRICES_INR)
    return {PRODUCT_CODE: DOCUMENT_STUDIO_PRICE_INR}


def catalogue_configuration(
    *,
    enabled: bool | None = None,
    allowlist: frozenset[str] | None = None,
    prices_inr: Mapping[str, int] | None = None,
) -> CatalogueConfiguration:
    """Validate global publication settings against the runtime registry.

    Price keys must match the allowlist exactly. This makes a partially
    configured product disable the entire customer catalogue instead of
    exposing an offer whose payment or release path is incomplete.
    """

    globally_enabled = (
        DOCUMENT_STUDIO_ENABLED if enabled is None else bool(enabled)
    )
    registry_error = _registry_validation_error()
    if registry_error:
        return CatalogueConfiguration(False, registry_error, ())
    if not globally_enabled:
        return CatalogueConfiguration(True, "DISABLED", ())

    enabled_codes = frozenset(
        DOCUMENT_STUDIO_PRODUCT_ALLOWLIST
        if allowlist is None
        else allowlist
    )
    registered_enabled = tuple(
        code for code in registered_product_codes() if code in enabled_codes
    )
    ordered_codes = registered_enabled + tuple(
        sorted(enabled_codes - set(_PRODUCT_DEFINITIONS))
    )
    if not enabled_codes:
        return CatalogueConfiguration(False, "NO_PRODUCTS_ENABLED", ())
    if enabled_codes - set(_PRODUCT_DEFINITIONS):
        return CatalogueConfiguration(
            False,
            "UNKNOWN_DOCUMENT_PRODUCT",
            ordered_codes,
        )

    effective_prices = dict(
        _runtime_prices_inr() if prices_inr is None else prices_inr
    )
    if set(effective_prices) - enabled_codes:
        return CatalogueConfiguration(
            False,
            "PRICE_CONFIGURED_FOR_DISABLED_PRODUCT",
            ordered_codes,
        )
    if enabled_codes - set(effective_prices):
        return CatalogueConfiguration(
            False,
            "PRICE_NOT_CONFIGURED",
            ordered_codes,
        )
    if any(
        not isinstance(price, int)
        or isinstance(price, bool)
        or price <= 0
        or price > 100000
        for price in effective_prices.values()
    ):
        return CatalogueConfiguration(
            False,
            "PRICE_NOT_CONFIGURED",
            ordered_codes,
        )
    return CatalogueConfiguration(True, "CONFIGURED", ordered_codes)


def product_availability(code: str) -> CatalogueConfiguration:
    """Return the global, user-independent publication decision for a code."""

    if code not in _PRODUCT_DEFINITIONS:
        return CatalogueConfiguration(False, "UNKNOWN_DOCUMENT_PRODUCT", ())
    configuration = catalogue_configuration()
    if not configuration.ok:
        return configuration
    if configuration.reason_code == "DISABLED":
        return CatalogueConfiguration(False, "PRODUCT_NOT_ENABLED", ())
    if code not in configuration.enabled_product_codes:
        return CatalogueConfiguration(
            False,
            "PRODUCT_NOT_ENABLED",
            configuration.enabled_product_codes,
        )
    return CatalogueConfiguration(
        True,
        "AVAILABLE",
        configuration.enabled_product_codes,
    )


def resolve_product(code: str = PRODUCT_CODE) -> DocumentProduct:
    try:
        definition = _PRODUCT_DEFINITIONS[code]
    except (KeyError, TypeError) as exc:
        raise KeyError("unknown_document_product") from exc

    template_bytes = _canonical_template_bytes(
        definition.template_path.read_bytes()
    )
    schema_bytes = definition.schema_bytes()
    template_hash = _sha256(template_bytes)
    schema_hash = _sha256(schema_bytes)
    aggregate_hash = _sha256(
        json.dumps(
            {
                "code": definition.code,
                "output_classification": definition.output_classification,
                "renderer_version": definition.renderer_version,
                "schema_hash": schema_hash,
                "schema_version": definition.schema_version,
                "template_hash": template_hash,
                "template_version": definition.template_version,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    price_inr = _runtime_prices_inr().get(code, 0)
    return DocumentProduct(
        code=definition.code,
        display_name=definition.display_name,
        display_name_key=definition.display_name_key,
        list_description=definition.list_description.format(
            price_inr=price_inr,
        ),
        list_description_key=definition.list_description_key,
        selection_overview=definition.selection_overview,
        selection_overview_key=definition.selection_overview_key,
        start_label=definition.start_label,
        start_label_key=definition.start_label_key,
        template_version=definition.template_version,
        schema_version=definition.schema_version,
        output_classification=definition.output_classification,
        language=definition.language,
        jurisdiction=definition.jurisdiction,
        price_model=definition.price_model,
        price_minor=price_inr * 100,
        currency=definition.currency,
        payment_description=definition.payment_description,
        turnaround_label=definition.turnaround_label,
        template_hash=template_hash,
        schema_hash=schema_hash,
        aggregate_hash=aggregate_hash,
        renderer_version=definition.renderer_version,
        template_path=definition.template_path,
        golden_answers=definition.golden_answers,
    )


def customer_visible(code: str = PRODUCT_CODE) -> bool:
    """Return global availability; never inspect an individual user."""

    return product_availability(code).ok


def visible_products() -> tuple[DocumentProduct, ...]:
    """Resolve the globally visible catalogue in stable registry order."""

    configuration = catalogue_configuration()
    if not configuration.ok or configuration.reason_code == "DISABLED":
        return ()
    return tuple(
        resolve_product(code)
        for code in configuration.enabled_product_codes
    )
