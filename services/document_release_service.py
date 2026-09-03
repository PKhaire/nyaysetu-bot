"""Fail-closed publication gate for immutable Document Studio packages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from models import DocumentTemplateApproval, utc_now
from services.document_catalogue import DocumentProduct, resolve_product
from services.document_renderer import golden_hashes


_HASH = re.compile(r"^[0-9a-f]{64}$")
_DECISIONS = {"APPROVED", "CHANGES_REQUIRED", "REJECTED"}


@dataclass(frozen=True)
class ReleaseGate:
    allowed: bool
    reason_code: str
    approval_id: int | None = None


def release_manifest(product: DocumentProduct | None = None) -> dict:
    """Return the exact non-secret package identity an advocate approves."""

    product = product or resolve_product()
    pdf_hash, docx_hash = golden_hashes(product)
    return {
        "product_code": product.code,
        "template_version": product.template_version,
        "template_aggregate_hash": product.aggregate_hash,
        "schema_hash": product.schema_hash,
        "template_hash": product.template_hash,
        "golden_pdf_hash": pdf_hash,
        "golden_docx_hash": docx_hash,
    }


def approval_for_product(db, product: DocumentProduct) -> DocumentTemplateApproval | None:
    """Return the latest decision for the exact deployed package.

    A newer rejection, changes-required decision, or revocation must override
    an older approval. Filtering to approved rows before ordering would allow
    stale evidence to keep the product open after an advocate withdrew it.
    """

    return (
        db.query(DocumentTemplateApproval)
        .filter(
            DocumentTemplateApproval.product_code == product.code,
            DocumentTemplateApproval.template_version
            == product.template_version,
            DocumentTemplateApproval.template_aggregate_hash
            == product.aggregate_hash,
        )
        .order_by(
            DocumentTemplateApproval.authenticated_at.desc(),
            DocumentTemplateApproval.id.desc(),
        )
        .first()
    )


def release_gate(db, product: DocumentProduct | None = None) -> ReleaseGate:
    """Verify legal evidence and golden render hashes before monetisation."""

    product = product or resolve_product()
    if product.price_minor <= 0:
        return ReleaseGate(False, "PRICE_NOT_CONFIGURED")
    approval = approval_for_product(db, product)
    if approval is None:
        return ReleaseGate(False, "ADVOCATE_APPROVAL_MISSING")
    if approval.revoked_at is not None:
        return ReleaseGate(False, "ADVOCATE_APPROVAL_REVOKED", approval.id)
    if approval.decision != "APPROVED":
        return ReleaseGate(
            False,
            f"ADVOCATE_DECISION_{approval.decision}",
            approval.id,
        )
    if approval.next_review_at <= utc_now():
        return ReleaseGate(False, "ADVOCATE_APPROVAL_EXPIRED", approval.id)
    pdf_hash, docx_hash = golden_hashes(product)
    if approval.golden_pdf_hash != pdf_hash:
        return ReleaseGate(False, "GOLDEN_PDF_HASH_MISMATCH", approval.id)
    if approval.golden_docx_hash != docx_hash:
        return ReleaseGate(False, "GOLDEN_DOCX_HASH_MISMATCH", approval.id)
    return ReleaseGate(True, "APPROVED", approval.id)


def validate_approval_payload(payload: dict) -> dict:
    """Normalize a privileged approval record without accepting ambiguity."""

    product = resolve_product()
    required_text = (
        "reviewer_name",
        "reviewer_enrolment_ref",
        "authority_statement",
        "authenticated_method",
    )
    normalized = {
        key: str(payload.get(key) or "").strip()
        for key in required_text
    }
    if any(len(value) < 3 for value in normalized.values()):
        raise ValueError("approval_identity_fields_required")
    decision = str(payload.get("decision") or "").strip().upper()
    if decision not in _DECISIONS:
        raise ValueError("invalid_approval_decision")
    try:
        authenticated_at = datetime.fromisoformat(
            str(payload.get("authenticated_at") or "").replace("Z", "+00:00")
        )
        next_review_at = datetime.fromisoformat(
            str(payload.get("next_review_at") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("invalid_approval_timestamp") from exc
    if authenticated_at.tzinfo is not None:
        authenticated_at = authenticated_at.astimezone(
            timezone.utc
        ).replace(tzinfo=None)
    if next_review_at.tzinfo is not None:
        next_review_at = next_review_at.astimezone(
            timezone.utc
        ).replace(tzinfo=None)
    if authenticated_at > utc_now():
        raise ValueError("approval_authentication_date_cannot_be_future")
    if next_review_at <= authenticated_at or next_review_at <= utc_now():
        raise ValueError("approval_review_date_must_be_future")
    supplied_aggregate = str(
        payload.get("template_aggregate_hash") or ""
    ).strip().lower()
    if supplied_aggregate != product.aggregate_hash:
        raise ValueError("template_aggregate_hash_mismatch")
    pdf_hash = str(payload.get("golden_pdf_hash") or "").strip().lower()
    docx_hash = str(payload.get("golden_docx_hash") or "").strip().lower()
    if not _HASH.fullmatch(pdf_hash) or not _HASH.fullmatch(docx_hash):
        raise ValueError("invalid_golden_hash")
    return {
        **normalized,
        "decision": decision,
        "conditions": str(payload.get("conditions") or "").strip() or None,
        "authenticated_at": authenticated_at,
        "next_review_at": next_review_at,
        "template_aggregate_hash": supplied_aggregate,
        "golden_pdf_hash": pdf_hash,
        "golden_docx_hash": docx_hash,
    }


def record_approval(db, payload: dict, *, recorded_by: str) -> DocumentTemplateApproval:
    """Append authenticated evidence; never silently overwrite history."""

    product = resolve_product()
    values = validate_approval_payload(payload)
    approval = DocumentTemplateApproval(
        product_code=product.code,
        template_version=product.template_version,
        recorded_by=recorded_by,
        **values,
    )
    db.add(approval)
    db.flush()
    return approval
