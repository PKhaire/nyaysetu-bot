"""Fail-closed publication gate for immutable Draft Studio packages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from models import DocumentTemplateApproval, utc_now
from services.document_catalogue import (
    PRODUCT_CODE,
    DocumentProduct,
    catalogue_configuration,
    resolve_product,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_DECISIONS = {"APPROVED", "CHANGES_REQUIRED", "REJECTED"}


@dataclass(frozen=True)
class ReleaseGate:
    allowed: bool
    reason_code: str
    approval_id: int | None = None


def release_manifest(product_code: str = PRODUCT_CODE) -> dict:
    """Return the exact non-secret package identity an advocate approves."""

    product = resolve_product(product_code)
    artifact_hashes = product.golden_artifact_hashes(product)
    manifest = {
        "product_code": product.code,
        "template_version": product.template_version,
        "template_aggregate_hash": product.aggregate_hash,
        "schema_hash": product.schema_hash,
        "template_hash": product.template_hash,
        "golden_artifact_hashes": artifact_hashes,
    }
    if set(artifact_hashes) == {"FINAL_PDF", "FINAL_DOCX"}:
        manifest.update(
            {
                "golden_pdf_hash": artifact_hashes["FINAL_PDF"],
                "golden_docx_hash": artifact_hashes["FINAL_DOCX"],
            }
        )
    return manifest


def _stored_artifact_hashes(
    approval: DocumentTemplateApproval,
) -> dict[str, str] | None:
    """Read new artifact evidence with a legacy self-service fallback."""

    if approval.golden_artifact_hashes_json:
        try:
            value = json.loads(approval.golden_artifact_hashes_json)
        except (TypeError, ValueError):
            return None
        if not isinstance(value, dict):
            return None
        normalized = {
            str(key): str(item).lower()
            for key, item in value.items()
            if isinstance(key, str) and isinstance(item, str)
        }
        return normalized if len(normalized) == len(value) else None
    if approval.golden_pdf_hash and approval.golden_docx_hash:
        return {
            "FINAL_PDF": approval.golden_pdf_hash,
            "FINAL_DOCX": approval.golden_docx_hash,
        }
    return None


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


def release_gate(
    db,
    product_code: str = PRODUCT_CODE,
) -> ReleaseGate:
    """Verify legal evidence and golden render hashes before monetisation."""

    try:
        product = resolve_product(product_code)
    except KeyError:
        return ReleaseGate(False, "UNKNOWN_DOCUMENT_PRODUCT")
    if product.price_model == "FIXED" and product.price_minor <= 0:
        return ReleaseGate(False, "PRICE_NOT_CONFIGURED")
    if product.price_model not in {"FIXED", "ADVOCATE_QUOTE"}:
        return ReleaseGate(False, "INVALID_PRICE_MODEL")
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
    expected_hashes = product.golden_artifact_hashes(product)
    stored_hashes = _stored_artifact_hashes(approval)
    if stored_hashes != expected_hashes:
        if set(expected_hashes) == {"FINAL_PDF", "FINAL_DOCX"}:
            if not stored_hashes or stored_hashes.get("FINAL_PDF") != expected_hashes["FINAL_PDF"]:
                return ReleaseGate(False, "GOLDEN_PDF_HASH_MISMATCH", approval.id)
            return ReleaseGate(False, "GOLDEN_DOCX_HASH_MISMATCH", approval.id)
        return ReleaseGate(
            False,
            "GOLDEN_ARTIFACT_HASH_MISMATCH",
            approval.id,
        )
    return ReleaseGate(True, "APPROVED", approval.id)


def release_readiness(db) -> dict[str, object]:
    """Return release evidence for every globally configured product."""

    configuration = catalogue_configuration()
    products: dict[str, dict[str, object]] = {}
    first_failure: str | None = None
    for product_code in configuration.enabled_product_codes:
        gate = release_gate(db, product_code)
        item: dict[str, object] = {
            "ok": gate.allowed,
            "reason_code": gate.reason_code,
        }
        try:
            product = resolve_product(product_code)
        except KeyError:
            pass
        else:
            item.update(
                {
                    "template_version": product.template_version,
                    "output_classification": product.output_classification,
                }
            )
        products[product_code] = item
        if not gate.allowed and first_failure is None:
            first_failure = gate.reason_code

    ok = bool(
        configuration.ok
        and configuration.reason_code in {"CONFIGURED", "DISABLED"}
        and all(item["ok"] for item in products.values())
    )
    reason_code = (
        configuration.reason_code
        if not configuration.ok
        else first_failure or configuration.reason_code
    )
    if ok and products:
        reason_code = "APPROVED"
    return {
        "ok": ok,
        "reason_code": reason_code,
        "products": products,
    }


def _validate_approval_payload(
    payload: dict,
    product: DocumentProduct,
) -> dict:
    """Normalize a privileged approval record without accepting ambiguity."""

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
    expected_keys = set(product.golden_artifact_hashes(product))
    supplied_artifacts = payload.get("golden_artifact_hashes")
    if supplied_artifacts is None:
        if expected_keys != {"FINAL_PDF", "FINAL_DOCX"}:
            raise ValueError("invalid_golden_artifact_hashes")
        pdf_hash = str(payload.get("golden_pdf_hash") or "").strip().lower()
        docx_hash = str(payload.get("golden_docx_hash") or "").strip().lower()
        if not _HASH.fullmatch(pdf_hash) or not _HASH.fullmatch(docx_hash):
            raise ValueError("invalid_golden_hash")
        artifact_hashes = {"FINAL_PDF": pdf_hash, "FINAL_DOCX": docx_hash}
    else:
        if not isinstance(supplied_artifacts, dict):
            raise ValueError("invalid_golden_artifact_hashes")
        artifact_hashes = {
            str(key).strip(): str(value).strip().lower()
            for key, value in supplied_artifacts.items()
        }
        if (
            set(artifact_hashes) != expected_keys
            or any(not _HASH.fullmatch(value) for value in artifact_hashes.values())
        ):
            raise ValueError("invalid_golden_artifact_hashes")
        pdf_hash = (
            artifact_hashes.get("FINAL_PDF")
            if expected_keys == {"FINAL_PDF", "FINAL_DOCX"}
            else None
        )
        docx_hash = (
            artifact_hashes.get("FINAL_DOCX")
            if expected_keys == {"FINAL_PDF", "FINAL_DOCX"}
            else None
        )
    return {
        **normalized,
        "decision": decision,
        "conditions": str(payload.get("conditions") or "").strip() or None,
        "authenticated_at": authenticated_at,
        "next_review_at": next_review_at,
        "template_aggregate_hash": supplied_aggregate,
        "golden_pdf_hash": pdf_hash,
        "golden_docx_hash": docx_hash,
        "golden_artifact_hashes_json": json.dumps(
            artifact_hashes,
            separators=(",", ":"),
            sort_keys=True,
        ),
    }


def validate_approval_payload(
    payload: dict,
    product_code: str = PRODUCT_CODE,
) -> dict:
    """Validate an approval against an explicitly selected product."""

    return _validate_approval_payload(payload, resolve_product(product_code))


def record_approval(
    db,
    payload: dict,
    *,
    recorded_by: str,
    product_code: str = PRODUCT_CODE,
) -> DocumentTemplateApproval:
    """Append authenticated evidence; never silently overwrite history."""

    product = resolve_product(product_code)
    values = _validate_approval_payload(payload, product)
    approval = DocumentTemplateApproval(
        product_code=product.code,
        template_version=product.template_version,
        recorded_by=recorded_by,
        **values,
    )
    db.add(approval)
    db.flush()
    return approval
