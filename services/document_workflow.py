"""Draft Studio orchestration behind a small stateful module interface."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import timedelta

from config import (
    DOCUMENT_STUDIO_DRAFT_TTL_DAYS,
    DOCUMENT_STUDIO_FINAL_TTL_DAYS,
)
from models import (
    DocumentAccessEvent,
    DocumentAnswerRevision,
    DocumentArtifact,
    DocumentAuditEvent,
    DocumentOrder,
    User,
    utc_now,
)
from services.document_artifact_vault import S3ArtifactVault
from services.document_catalogue import (
    DocumentProduct,
    product_availability,
    resolve_product,
)
from services.document_payment_service import create_document_payment_link
from services.document_release_service import release_gate
from services.document_renderer import render


@dataclass(frozen=True)
class WorkflowResult:
    ok: bool
    reason_code: str
    value: object | None = None


def _resolve_order_product(
    order: DocumentOrder,
    *,
    require_current_package: bool = True,
) -> tuple[DocumentProduct | None, str | None]:
    """Resolve by immutable order identity and fail closed on package drift."""

    try:
        product = resolve_product(order.product_code)
    except KeyError:
        return None, "UNKNOWN_DOCUMENT_PRODUCT"
    if require_current_package and not product.matches_package_snapshot(
        template_version=order.template_version,
        schema_hash=order.schema_hash,
        template_hash=order.template_hash,
        output_classification=order.output_classification,
    ):
        return None, "DOCUMENT_PACKAGE_SNAPSHOT_MISMATCH"
    return product, None


def _canonical(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _audit(
    db,
    order: DocumentOrder,
    event_type: str,
    *,
    actor_type: str,
    from_state: str | None = None,
    to_state: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type=actor_type,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            details_json=_canonical(details or {}),
        )
    )


def _revision(db, order: DocumentOrder) -> DocumentAnswerRevision:
    if not order.active_revision_number:
        raise ValueError("document_revision_missing")
    revision = (
        db.query(DocumentAnswerRevision)
        .filter(
            DocumentAnswerRevision.document_order_id == order.id,
            DocumentAnswerRevision.revision_number
            == order.active_revision_number,
        )
        .one_or_none()
    )
    if revision is None:
        raise ValueError("document_revision_missing")
    return revision


def _artifact(
    db,
    order: DocumentOrder,
    artifact_kind: str,
) -> DocumentArtifact | None:
    return (
        db.query(DocumentArtifact)
        .filter(
            DocumentArtifact.document_order_id == order.id,
            DocumentArtifact.revision_number
            == order.active_revision_number,
            DocumentArtifact.artifact_kind == artifact_kind,
            DocumentArtifact.state == "AVAILABLE",
        )
        .one_or_none()
    )


def _store_rendered(db, order, vault, rendered, *, expires_at):
    existing = _artifact(db, order, rendered.kind)
    if existing is not None:
        if (
            existing.content_hash != rendered.content_hash
            or existing.manifest_hash != rendered.manifest_hash
        ):
            raise RuntimeError("immutable_document_artifact_conflict")
        return existing
    stored = vault.put(
        order_ref=order.public_ref,
        revision_number=order.active_revision_number,
        artifact_kind=rendered.kind,
        content=rendered.content,
        content_type=rendered.content_type,
        content_hash=rendered.content_hash,
        manifest_hash=rendered.manifest_hash,
    )
    artifact = DocumentArtifact(
        public_ref=f"DA-{secrets.token_hex(6).upper()}",
        document_order_id=order.id,
        revision_number=order.active_revision_number,
        artifact_kind=rendered.kind,
        state="AVAILABLE",
        storage_provider="S3",
        bucket=stored.bucket,
        object_key=stored.object_key,
        content_type=rendered.content_type,
        size_bytes=stored.size_bytes,
        content_hash=rendered.content_hash,
        manifest_hash=rendered.manifest_hash,
        renderer_version=rendered.renderer_version,
        expires_at=expires_at,
    )
    db.add(artifact)
    db.flush()
    return artifact


def build_preview(db, order: DocumentOrder, *, vault=None) -> WorkflowResult:
    """Render/store a watermarked preview only for an approved exact package."""

    if order.state not in {"CONFIRMED", "PREVIEW_READY"}:
        return WorkflowResult(False, "DOCUMENT_NOT_CONFIRMED")
    product, product_error = _resolve_order_product(order)
    if product_error:
        order.release_status = "BLOCKED"
        order.exception_code = product_error
        return WorkflowResult(False, product_error)
    availability = product_availability(product.code)
    if not availability.ok:
        order.release_status = "BLOCKED"
        order.exception_code = availability.reason_code
        return WorkflowResult(False, availability.reason_code)
    gate = release_gate(db, product.code)
    if not gate.allowed:
        order.release_status = "BLOCKED"
        order.exception_code = gate.reason_code
        return WorkflowResult(False, gate.reason_code)
    revision = _revision(db, order)
    answers = json.loads(revision.answers_json)
    rendered = render(product, answers, "PREVIEW_PDF")
    vault = vault or S3ArtifactVault()
    expires_at = utc_now() + timedelta(days=DOCUMENT_STUDIO_DRAFT_TTL_DAYS)
    artifact = _store_rendered(
        db, order, vault, rendered, expires_at=expires_at
    )
    previous = order.state
    order.state = "PREVIEW_READY"
    order.release_status = "APPROVED"
    order.exception_code = None
    order.preview_manifest_hash = rendered.manifest_hash
    _audit(
        db,
        order,
        "DOCUMENT_PREVIEW_READY",
        actor_type="SYSTEM",
        from_state=previous,
        to_state=order.state,
        details={
            "artifact_ref": artifact.public_ref,
            "manifest_hash": rendered.manifest_hash,
            "approval_id": gate.approval_id,
        },
    )
    return WorkflowResult(True, "PREVIEW_READY", artifact)


def request_payment(
    db,
    order: DocumentOrder,
    user: User,
    *,
    payment_client=None,
) -> WorkflowResult:
    """Create a payment entitlement only after release/storage evidence."""

    product, product_error = _resolve_order_product(order)
    if product_error:
        order.release_status = "BLOCKED"
        order.exception_code = product_error
        return WorkflowResult(False, product_error)
    availability = product_availability(product.code)
    if not availability.ok:
        order.release_status = "BLOCKED"
        order.exception_code = availability.reason_code
        return WorkflowResult(False, availability.reason_code)
    gate = release_gate(db, product.code)
    if not gate.allowed:
        return WorkflowResult(False, gate.reason_code)
    if _artifact(db, order, "PREVIEW_PDF") is None:
        return WorkflowResult(False, "PREVIEW_ARTIFACT_MISSING")
    try:
        url = create_document_payment_link(
            order,
            user,
            product=product,
            client=payment_client,
        )
    except Exception:
        order.state = "NEEDS_ATTENTION"
        order.exception_code = "PAYMENT_LINK_CREATE_FAILED"
        return WorkflowResult(False, "PAYMENT_LINK_CREATE_FAILED")
    _audit(
        db,
        order,
        "DOCUMENT_PAYMENT_LINK_CREATED",
        actor_type="SYSTEM",
        from_state="PREVIEW_READY",
        to_state="PAYMENT_PENDING",
        details={"approval_id": gate.approval_id},
    )
    return WorkflowResult(True, "PAYMENT_PENDING", url)


def preview_link_for_user(
    db,
    order: DocumentOrder,
    user: User,
    *,
    vault=None,
) -> WorkflowResult:
    """Issue an owner-authorized, short-lived watermarked preview URL."""

    if order.user_id != user.id or order.state not in {
        "PREVIEW_READY",
        "PAYMENT_PENDING",
    }:
        return WorkflowResult(False, "PREVIEW_NOT_AVAILABLE")
    _, product_error = _resolve_order_product(
        order,
        require_current_package=False,
    )
    if product_error:
        return WorkflowResult(False, product_error)
    artifact = _artifact(db, order, "PREVIEW_PDF")
    if artifact is None or artifact.expires_at <= utc_now():
        return WorkflowResult(False, "PREVIEW_NOT_AVAILABLE")
    vault = vault or S3ArtifactVault()
    url = vault.download_url(artifact.object_key)
    db.add(
        DocumentAccessEvent(
            document_order_id=order.id,
            document_artifact_id=artifact.id,
            actor_type="CLIENT",
            actor_ref=str(user.id),
            action="PREVIEW_URL_ISSUED",
            decision="ALLOWED",
            reason_code="OWNER_CONFIRMED_REVISION",
        )
    )
    return WorkflowResult(True, "PREVIEW_LINK_READY", url)


def _apply_verified_payment(
    db,
    order: DocumentOrder,
    *,
    payment_id: str,
    payment_amount: int,
    payment_currency: str,
    permitted_states: frozenset[str],
    actor_type: str,
    event_type: str,
    vault=None,
) -> WorkflowResult:
    """Grant final artifacts after the caller verifies current payment evidence."""

    if order.payment_processed:
        if order.razorpay_payment_id == payment_id:
            return WorkflowResult(True, "ALREADY_PROCESSED", order)
        return WorkflowResult(False, "PAYMENT_CONFLICT")
    if order.state not in permitted_states:
        return WorkflowResult(False, "PAYMENT_ORDER_STATE_INVALID")
    if payment_amount != order.price_minor or payment_currency != order.currency:
        order.state = "NEEDS_ATTENTION"
        order.exception_code = "PAYMENT_AMOUNT_MISMATCH"
        return WorkflowResult(False, "PAYMENT_AMOUNT_MISMATCH")
    product, product_error = _resolve_order_product(order)
    if product_error:
        order.state = "NEEDS_ATTENTION"
        order.exception_code = product_error
        return WorkflowResult(False, product_error)
    gate = release_gate(db, product.code)
    if not gate.allowed:
        order.state = "NEEDS_ATTENTION"
        order.exception_code = gate.reason_code
        return WorkflowResult(False, gate.reason_code)
    revision = _revision(db, order)
    answers = json.loads(revision.answers_json)
    vault = vault or S3ArtifactVault()
    expires_at = utc_now() + timedelta(days=DOCUMENT_STUDIO_FINAL_TTL_DAYS)
    pdf = render(product, answers, "FINAL_PDF")
    docx = render(product, answers, "FINAL_DOCX")
    pdf_artifact = _store_rendered(
        db, order, vault, pdf, expires_at=expires_at
    )
    docx_artifact = _store_rendered(
        db, order, vault, docx, expires_at=expires_at
    )
    previous = order.state
    order.state = "FINAL_AVAILABLE"
    order.payment_processed = True
    order.razorpay_payment_id = payment_id
    order.paid_at = utc_now()
    order.final_available_until = expires_at
    order.exception_code = None
    _audit(
        db,
        order,
        event_type,
        actor_type=actor_type,
        from_state=previous,
        to_state=order.state,
        details={
            "payment_id_hash": __import__("hashlib").sha256(
                payment_id.encode("utf-8")
            ).hexdigest(),
            "pdf_artifact_ref": pdf_artifact.public_ref,
            "docx_artifact_ref": docx_artifact.public_ref,
            "approval_id": gate.approval_id,
        },
    )
    return WorkflowResult(
        True, "FINAL_AVAILABLE", (pdf_artifact, docx_artifact)
    )


def apply_verified_payment(
    db,
    order: DocumentOrder,
    *,
    payment_id: str,
    payment_amount: int,
    payment_currency: str,
    vault=None,
) -> WorkflowResult:
    """Idempotently grant final artifacts for a provider-verified webhook."""

    return _apply_verified_payment(
        db,
        order,
        payment_id=payment_id,
        payment_amount=payment_amount,
        payment_currency=payment_currency,
        permitted_states=frozenset({"PAYMENT_PENDING"}),
        actor_type="PROVIDER",
        event_type="DOCUMENT_FINAL_AVAILABLE",
        vault=vault,
    )


def recover_verified_payment(
    db,
    order: DocumentOrder,
    *,
    payment_id: str,
    payment_amount: int,
    payment_currency: str,
    actor_type: str = "SYSTEM",
    vault=None,
) -> WorkflowResult:
    """Recover an exact current capture after a missed or reviewed webhook."""

    return _apply_verified_payment(
        db,
        order,
        payment_id=payment_id,
        payment_amount=payment_amount,
        payment_currency=payment_currency,
        permitted_states=frozenset({"PAYMENT_PENDING", "NEEDS_ATTENTION"}),
        actor_type=actor_type,
        event_type="DOCUMENT_FINAL_RECOVERED",
        vault=vault,
    )


def download_links_for_user(
    db,
    order: DocumentOrder,
    user: User,
    *,
    vault=None,
) -> WorkflowResult:
    """Authorize the owning user and issue bounded URLs without persisting them."""

    if order.user_id != user.id:
        db.add(
            DocumentAccessEvent(
                document_order_id=order.id,
                actor_type="CLIENT",
                actor_ref=str(user.id),
                action="DOWNLOAD",
                decision="DENIED",
                reason_code="NOT_OWNER",
            )
        )
        return WorkflowResult(False, "NOT_OWNER")
    _, product_error = _resolve_order_product(
        order,
        require_current_package=False,
    )
    if product_error:
        return WorkflowResult(False, product_error)
    if (
        order.state != "FINAL_AVAILABLE"
        or not order.final_available_until
        or order.final_available_until <= utc_now()
    ):
        return WorkflowResult(False, "FINAL_NOT_AVAILABLE")
    artifacts = (
        db.query(DocumentArtifact)
        .filter(
            DocumentArtifact.document_order_id == order.id,
            DocumentArtifact.revision_number
            == order.active_revision_number,
            DocumentArtifact.artifact_kind.in_(("FINAL_PDF", "FINAL_DOCX")),
            DocumentArtifact.state == "AVAILABLE",
            DocumentArtifact.expires_at > utc_now(),
        )
        .order_by(DocumentArtifact.artifact_kind)
        .all()
    )
    if len(artifacts) != 2:
        return WorkflowResult(False, "FINAL_ARTIFACTS_INCOMPLETE")
    vault = vault or S3ArtifactVault()
    links = {}
    for artifact in artifacts:
        links[artifact.artifact_kind] = vault.download_url(
            artifact.object_key
        )
        db.add(
            DocumentAccessEvent(
                document_order_id=order.id,
                document_artifact_id=artifact.id,
                actor_type="CLIENT",
                actor_ref=str(user.id),
                action="DOWNLOAD_URL_ISSUED",
                decision="ALLOWED",
                reason_code="OWNER_ENTITLED",
            )
        )
    return WorkflowResult(True, "DOWNLOADS_READY", links)
