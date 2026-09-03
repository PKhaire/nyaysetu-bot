"""Immutable catalogue for the first Document Studio self-service product.

The module deliberately exposes a small product interface. Publication,
question ordering, price snapshots and content hashes are owned here rather
than spread across Flask/WhatsApp handlers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from config import (
    DOCUMENT_STUDIO_ENABLED,
    DOCUMENT_STUDIO_PRICE_INR,
    DOCUMENT_STUDIO_PRODUCT_ALLOWLIST,
)


PRODUCT_CODE = "mh_residential_leave_licence_11m_self_service"
TEMPLATE_VERSION = "mh-ll-en-2026-08-candidate-1"
OUTPUT_CLASSIFICATION = "SELF_SERVICE_DRAFT"
SCHEMA_VERSION = "mh-ll-questionnaire-2026-08-v1"
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
    template_version: str
    schema_version: str
    output_classification: str
    language: str
    jurisdiction: str
    price_minor: int
    currency: str
    template_hash: str
    schema_hash: str
    aggregate_hash: str


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _questionnaire_schema_bytes() -> bytes:
    # Import lazily so the catalogue remains usable by migrations and config
    # checks without creating a module cycle.
    from services.document_studio_rc9_service import QUESTION_DEFINITIONS

    serializable = [
        {
            key: value
            for key, value in question.items()
            if key not in {"validator"}
        }
        for question in QUESTION_DEFINITIONS
    ]
    return json.dumps(
        serializable,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def resolve_product(code: str = PRODUCT_CODE) -> DocumentProduct:
    if code != PRODUCT_CODE:
        raise KeyError("unknown_document_product")

    template_bytes = TEMPLATE_PATH.read_bytes()
    schema_bytes = _questionnaire_schema_bytes()
    template_hash = _sha256(template_bytes)
    schema_hash = _sha256(schema_bytes)
    aggregate_hash = _sha256(
        json.dumps(
            {
                "code": PRODUCT_CODE,
                "output_classification": OUTPUT_CLASSIFICATION,
                "renderer_version": RENDERER_VERSION,
                "schema_hash": schema_hash,
                "schema_version": SCHEMA_VERSION,
                "template_hash": template_hash,
                "template_version": TEMPLATE_VERSION,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    return DocumentProduct(
        code=PRODUCT_CODE,
        template_version=TEMPLATE_VERSION,
        schema_version=SCHEMA_VERSION,
        output_classification=OUTPUT_CLASSIFICATION,
        language="en",
        jurisdiction="Maharashtra, India",
        price_minor=DOCUMENT_STUDIO_PRICE_INR * 100,
        currency="INR",
        template_hash=template_hash,
        schema_hash=schema_hash,
        aggregate_hash=aggregate_hash,
    )


def customer_visible() -> bool:
    """Return global availability; never inspect an individual user."""

    return bool(
        DOCUMENT_STUDIO_ENABLED
        and PRODUCT_CODE in DOCUMENT_STUDIO_PRODUCT_ALLOWLIST
    )
