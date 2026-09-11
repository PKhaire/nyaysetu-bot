"""Advocate-issued document workflow behind one command interface."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from models import (
    AdminOperator,
    Advocate,
    DocumentAccessEvent,
    DocumentAdvocateAssignment,
    DocumentAnswerRevision,
    DocumentArtifact,
    DocumentAuditEvent,
    DocumentEvidenceArtifact,
    DocumentDispatchEvent,
    DocumentMatterReview,
    DocumentOrder,
    DocumentIssueApproval,
    DocumentLegalHold,
    DocumentQuote,
    User,
    utc_now,
)
from services.document_evidence_vault import S3EvidenceVault
from services.document_artifact_vault import S3ArtifactVault
from services.document_payment_service import create_advocate_quote_payment_link


_EVIDENCE_KINDS = frozenset(
    {
        "CHEQUE_FRONT",
        "RETURN_MEMO",
        "LIABILITY_SUPPORT",
        "ADDRESS_SUPPORT",
        "OTHER_SUPPORT",
        "DISPATCH_PROOF",
    }
)
_EVIDENCE_CONTENT_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png"}
)
_MAX_EVIDENCE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class WorkflowActor:
    actor_type: str
    identity_id: int


@dataclass(frozen=True)
class EvaluateChequeNoticeIntake:
    """Evaluate one immutable intake revision after evidence upload."""

    pass


@dataclass(frozen=True)
class AssignAdvocate:
    advocate_id: int
    sla_due_at: datetime


@dataclass(frozen=True)
class RecordConflictCheck:
    outcome: str
    reason_code: str


@dataclass(frozen=True)
class RecordMatterDecision:
    decision: str
    intake_revision_number: int
    reason_codes: tuple[str, ...]
    conditions: str | None = None


@dataclass(frozen=True)
class CreateQuote:
    amount_minor: int
    currency: str
    scope_version: str
    scope: dict[str, Any]
    expires_at: datetime


@dataclass(frozen=True)
class AcceptQuote:
    quote_id: int


@dataclass(frozen=True)
class RequestPayment:
    pass


@dataclass(frozen=True)
class StoreEvidence:
    kind: str
    content: bytes
    content_type: str
    expires_at: datetime


@dataclass(frozen=True)
class IssueEvidenceLink:
    evidence_ref: str


@dataclass(frozen=True)
class IssueIssuedArtifactLink:
    pass


@dataclass(frozen=True)
class RecordVerifiedPayment:
    payment_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class SubmitDraftForFactCheck:
    content: bytes
    expires_at: datetime


@dataclass(frozen=True)
class ConfirmNoticeFacts:
    candidate_artifact_ref: str


@dataclass(frozen=True)
class ApproveIssuedArtifact:
    candidate_artifact_ref: str
    signed_content: bytes
    signing_method: str
    conditions: str | None
    expires_at: datetime


@dataclass(frozen=True)
class RecordDispatch:
    method: str
    tracking_reference: str
    address_snapshot_hash: str
    proof_evidence_ref: str
    occurred_at: datetime


@dataclass(frozen=True)
class OpenLegalHold:
    reason_code: str
    authority_statement: str


@dataclass(frozen=True)
class CloseLegalHold:
    hold_id: int
    closure_reason: str


@dataclass(frozen=True)
class NoticeWorkflowResult:
    ok: bool
    code: str
    snapshot: dict[str, Any] | None = None


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _assignment_snapshot(
    order: DocumentOrder,
    assignment: DocumentAdvocateAssignment,
) -> dict[str, Any]:
    return {
        "order_ref": order.public_ref,
        "state": order.state,
        "assignment": {
            "advocate_id": assignment.advocate_id,
            "status": assignment.status,
            "conflict_status": assignment.conflict_status,
            "authority_scope_version": assignment.authority_scope_version,
        },
    }


def _evaluate_cheque_notice_intake(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
) -> NoticeWorkflowResult:
    """Move a validated package into triage without making a legal decision."""

    if actor.actor_type != "SYSTEM":
        return NoticeWorkflowResult(False, "SYSTEM_INTAKE_EVALUATION_REQUIRED")
    from services.cheque_notice_product import (
        PRODUCT_CODE as CHEQUE_NOTICE_PRODUCT_CODE,
        validate_intake,
    )
    from services.document_catalogue import resolve_product
    from services.document_release_service import release_gate

    if (
        order.product_code != CHEQUE_NOTICE_PRODUCT_CODE
        or order.output_classification != "ADVOCATE_ISSUED_NOTICE"
        or order.state not in {"INTAKE", "EVIDENCE_PENDING"}
        or not order.active_revision_number
    ):
        return NoticeWorkflowResult(False, "CHEQUE_NOTICE_INTAKE_STATE_INVALID")
    try:
        product = resolve_product(order.product_code)
    except KeyError:
        return NoticeWorkflowResult(False, "UNKNOWN_DOCUMENT_PRODUCT")
    if not product.matches_package_snapshot(
        template_version=order.template_version,
        schema_hash=order.schema_hash,
        template_hash=order.template_hash,
        output_classification=order.output_classification,
    ):
        return NoticeWorkflowResult(False, "DOCUMENT_PACKAGE_SNAPSHOT_MISMATCH")
    gate = release_gate(db, product.code)
    if not gate.allowed:
        return NoticeWorkflowResult(False, gate.reason_code)
    revision = (
        db.query(DocumentAnswerRevision)
        .filter(
            DocumentAnswerRevision.document_order_id == order.id,
            DocumentAnswerRevision.revision_number
            == order.active_revision_number,
            DocumentAnswerRevision.schema_version == product.schema_version,
        )
        .first()
    )
    if revision is None:
        return NoticeWorkflowResult(False, "INTAKE_REVISION_MISSING")
    try:
        answers = json.loads(revision.answers_json)
    except (TypeError, ValueError):
        return NoticeWorkflowResult(False, "INTAKE_REVISION_INVALID")
    if not isinstance(answers, dict):
        return NoticeWorkflowResult(False, "INTAKE_REVISION_INVALID")
    evidence_statuses: dict[str, str] = {}
    for evidence in (
        db.query(DocumentEvidenceArtifact)
        .filter(
            DocumentEvidenceArtifact.document_order_id == order.id,
            DocumentEvidenceArtifact.revision_number
            == order.active_revision_number,
            DocumentEvidenceArtifact.state == "AVAILABLE",
        )
        .all()
    ):
        evidence_statuses[evidence.evidence_kind] = (
            evidence.scan_status
            if evidence.expires_at > utc_now()
            else "EXPIRED"
        )
    result = validate_intake(
        answers,
        evidence_scan_statuses=evidence_statuses,
    )
    if result.status == "INVALID":
        return NoticeWorkflowResult(
            False,
            "INTAKE_INVALID",
            {"reason_codes": list(result.reason_codes)},
        )

    previous = order.state
    if result.status == "EVIDENCE_PENDING":
        order.state = "EVIDENCE_PENDING"
        order.current_step = "evidence_validation"
        order.exception_code = result.reason_codes[0]
        result_code = "EVIDENCE_PENDING"
    elif result.status == "ROUTED_OUT":
        order.state = "ROUTED_OUT"
        order.current_step = "manual_consultation"
        order.exception_code = result.reason_codes[0]
        result_code = "ROUTED_OUT"
    else:
        order.state = "ADVOCATE_TRIAGE"
        order.current_step = "advocate_assignment"
        order.exception_code = None
        result_code = "ADVOCATE_TRIAGE"
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="SYSTEM",
            event_type="DOCUMENT_CHEQUE_INTAKE_EVALUATED",
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "reason_codes": result.reason_codes,
                    "revision_number": revision.revision_number,
                    "warnings": result.warnings,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        result_code,
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "reason_codes": list(result.reason_codes),
            "warnings": list(result.warnings),
        },
    )


def _assign_advocate(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: AssignAdvocate,
) -> NoticeWorkflowResult:
    operator = db.get(AdminOperator, actor.identity_id)
    if (
        actor.actor_type != "OPERATOR"
        or operator is None
        or not operator.active
        or operator.mfa_enrolled_at is None
        or operator.role not in {"ADMIN", "OPERATOR"}
    ):
        return NoticeWorkflowResult(False, "OPERATOR_NOT_AUTHORIZED")
    if (
        order.output_classification != "ADVOCATE_ISSUED_NOTICE"
        or order.state != "ADVOCATE_TRIAGE"
    ):
        return NoticeWorkflowResult(False, "NOTICE_ORDER_STATE_INVALID")
    existing = (
        db.query(DocumentAdvocateAssignment)
        .filter(DocumentAdvocateAssignment.document_order_id == order.id)
        .first()
    )
    if existing is not None:
        return NoticeWorkflowResult(False, "ADVOCATE_ALREADY_ASSIGNED")
    advocate = db.get(Advocate, command.advocate_id)
    if (
        advocate is None
        or not advocate.active
        or advocate.verification_status != "VERIFIED"
        or not advocate.verification_ref
        or advocate.verified_at is None
    ):
        return NoticeWorkflowResult(False, "ADVOCATE_NOT_VERIFIED")
    try:
        authority_scope = json.loads(advocate.authority_scope_json)
    except (TypeError, ValueError):
        return NoticeWorkflowResult(False, "ADVOCATE_AUTHORITY_INVALID")
    if not isinstance(authority_scope, dict):
        return NoticeWorkflowResult(False, "ADVOCATE_AUTHORITY_INVALID")
    scope_version = str(authority_scope.get("version") or "").strip()
    product_codes = authority_scope.get("product_codes")
    if (
        not scope_version
        or not isinstance(product_codes, list)
        or order.product_code not in product_codes
    ):
        return NoticeWorkflowResult(False, "ADVOCATE_OUT_OF_SCOPE")
    advocate_identity = (
        db.query(AdminOperator)
        .filter(
            AdminOperator.advocate_id == advocate.id,
            AdminOperator.role == "ADVOCATE",
            AdminOperator.active.is_(True),
            AdminOperator.mfa_enrolled_at.isnot(None),
        )
        .first()
    )
    if advocate_identity is None:
        return NoticeWorkflowResult(False, "ADVOCATE_IDENTITY_NOT_ACTIVE")
    canonical_scope = _canonical(authority_scope)
    assignment = DocumentAdvocateAssignment(
        document_order_id=order.id,
        advocate_id=advocate.id,
        advocate_identity_id=advocate_identity.id,
        assigned_by_operator_id=operator.id,
        status="ASSIGNED",
        conflict_status="PENDING",
        authority_scope_version=scope_version,
        authority_scope_hash=hashlib.sha256(
            canonical_scope.encode("utf-8")
        ).hexdigest(),
        authority_scope_json=canonical_scope,
        sla_due_at=command.sla_due_at,
    )
    db.add(assignment)
    db.flush()
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="OPERATOR",
            event_type="DOCUMENT_ADVOCATE_ASSIGNED",
            from_state=order.state,
            to_state=order.state,
            details_json=_canonical(
                {
                    "assignment_id": assignment.id,
                    "advocate_id": advocate.id,
                    "authority_scope_hash": assignment.authority_scope_hash,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "ADVOCATE_ASSIGNED",
        _assignment_snapshot(order, assignment),
    )


def _advocate_assignment(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
) -> tuple[DocumentAdvocateAssignment | None, AdminOperator | None]:
    identity = db.get(AdminOperator, actor.identity_id)
    if (
        actor.actor_type != "ADVOCATE"
        or identity is None
        or identity.role != "ADVOCATE"
        or not identity.active
        or identity.mfa_enrolled_at is None
        or identity.advocate_id is None
    ):
        return None, None
    assignment = (
        db.query(DocumentAdvocateAssignment)
        .filter(
            DocumentAdvocateAssignment.document_order_id == order.id,
            DocumentAdvocateAssignment.advocate_id == identity.advocate_id,
            DocumentAdvocateAssignment.advocate_identity_id == identity.id,
            DocumentAdvocateAssignment.status.in_(
                ("ASSIGNED", "ACCEPTED", "ISSUED")
            ),
        )
        .first()
    )
    return assignment, identity


def _record_conflict_check(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: RecordConflictCheck,
) -> NoticeWorkflowResult:
    assignment, _ = _advocate_assignment(db, order, actor)
    if assignment is None:
        return NoticeWorkflowResult(False, "ASSIGNED_ADVOCATE_REQUIRED")
    outcome = command.outcome.strip().upper()
    reason_code = command.reason_code.strip().upper()
    if outcome not in {"CLEARED", "CONFLICT"} or not reason_code:
        return NoticeWorkflowResult(False, "CONFLICT_DECISION_INVALID")
    if assignment.conflict_status != "PENDING":
        return NoticeWorkflowResult(False, "CONFLICT_ALREADY_DECIDED")
    previous = order.state
    assignment.conflict_status = outcome
    if outcome == "CONFLICT":
        assignment.status = "DECLINED"
        assignment.declined_at = utc_now()
        order.state = "CONFLICTED"
        order.current_step = "closed"
        order.exception_code = "ADVOCATE_CONFLICT"
        result_code = "CONFLICT_RECORDED"
    else:
        order.current_step = "advocate_review"
        result_code = "CONFLICT_CLEARED"
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="ADVOCATE",
            event_type="DOCUMENT_CONFLICT_" + outcome,
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "assignment_id": assignment.id,
                    "reason_code": reason_code,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        result_code,
        _assignment_snapshot(order, assignment),
    )


def _record_matter_decision(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: RecordMatterDecision,
) -> NoticeWorkflowResult:
    assignment, identity = _advocate_assignment(db, order, actor)
    if assignment is None or identity is None:
        return NoticeWorkflowResult(False, "ASSIGNED_ADVOCATE_REQUIRED")
    decision = command.decision.strip().upper()
    reason_codes = tuple(
        code.strip().upper() for code in command.reason_codes if code.strip()
    )
    if decision not in {"ACCEPTED", "DECLINED", "UNSUPPORTED"} or not reason_codes:
        return NoticeWorkflowResult(False, "MATTER_DECISION_INVALID")
    if assignment.conflict_status != "CLEARED":
        return NoticeWorkflowResult(False, "CONFLICT_CLEARANCE_REQUIRED")
    if assignment.status != "ASSIGNED" or order.state != "ADVOCATE_TRIAGE":
        return NoticeWorkflowResult(False, "MATTER_REVIEW_STATE_INVALID")
    revision = (
        db.query(DocumentAnswerRevision)
        .filter(
            DocumentAnswerRevision.document_order_id == order.id,
            DocumentAnswerRevision.revision_number
            == command.intake_revision_number,
        )
        .first()
    )
    if (
        revision is None
        or order.active_revision_number != command.intake_revision_number
    ):
        return NoticeWorkflowResult(False, "INTAKE_REVISION_MISMATCH")
    review = DocumentMatterReview(
        document_order_id=order.id,
        assignment_id=assignment.id,
        intake_revision_number=revision.revision_number,
        intake_content_hash=revision.content_hash,
        decision=decision,
        reason_codes_json=_canonical(reason_codes),
        conditions=command.conditions,
        reviewer_advocate_id=assignment.advocate_id,
        reviewer_identity_id=identity.id,
    )
    db.add(review)
    previous = order.state
    if decision == "ACCEPTED":
        assignment.status = "ACCEPTED"
        assignment.accepted_at = utc_now()
        order.current_step = "advocate_quote"
        result_code = "MATTER_ACCEPTED"
    else:
        assignment.status = "DECLINED"
        assignment.declined_at = utc_now()
        order.state = decision
        order.current_step = "closed"
        order.exception_code = "MATTER_" + decision
        result_code = "MATTER_" + decision
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="ADVOCATE",
            event_type="DOCUMENT_MATTER_" + decision,
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "intake_revision_number": revision.revision_number,
                    "intake_content_hash": revision.content_hash,
                    "reason_codes": reason_codes,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        result_code,
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "current_step": order.current_step,
            "review": {
                "decision": decision,
                "intake_revision_number": revision.revision_number,
                "advocate_id": assignment.advocate_id,
            },
        },
    )


def _create_quote(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: CreateQuote,
) -> NoticeWorkflowResult:
    assignment, identity = _advocate_assignment(db, order, actor)
    if assignment is None or identity is None:
        return NoticeWorkflowResult(False, "ASSIGNED_ADVOCATE_REQUIRED")
    if (
        assignment.status != "ACCEPTED"
        or assignment.conflict_status != "CLEARED"
        or order.state != "ADVOCATE_TRIAGE"
        or order.current_step != "advocate_quote"
    ):
        return NoticeWorkflowResult(False, "QUOTE_STATE_INVALID")
    currency = command.currency.strip().upper()
    scope_version = command.scope_version.strip()
    if (
        isinstance(command.amount_minor, bool)
        or not isinstance(command.amount_minor, int)
        or not 100 <= command.amount_minor <= 10_000_000
        or currency != "INR"
        or not scope_version
        or not isinstance(command.scope, dict)
        or not command.scope
        or command.expires_at <= utc_now()
    ):
        return NoticeWorkflowResult(False, "QUOTE_INVALID")
    existing = (
        db.query(DocumentQuote)
        .filter(
            DocumentQuote.document_order_id == order.id,
            DocumentQuote.status.in_(("OFFERED", "ACCEPTED")),
        )
        .first()
    )
    if existing is not None:
        return NoticeWorkflowResult(False, "ACTIVE_QUOTE_EXISTS")
    review = (
        db.query(DocumentMatterReview)
        .filter(
            DocumentMatterReview.document_order_id == order.id,
            DocumentMatterReview.intake_revision_number
            == order.active_revision_number,
            DocumentMatterReview.decision == "ACCEPTED",
        )
        .first()
    )
    if review is None:
        return NoticeWorkflowResult(False, "ACCEPTED_REVIEW_MISSING")
    latest_version = (
        db.query(DocumentQuote.quote_version)
        .filter(DocumentQuote.document_order_id == order.id)
        .order_by(DocumentQuote.quote_version.desc())
        .first()
    )
    quote_version = (latest_version[0] if latest_version else 0) + 1
    canonical_scope = _canonical(command.scope)
    quote = DocumentQuote(
        document_order_id=order.id,
        matter_review_id=review.id,
        quote_version=quote_version,
        amount_minor=command.amount_minor,
        currency=currency,
        scope_version=scope_version,
        scope_hash=hashlib.sha256(canonical_scope.encode("utf-8")).hexdigest(),
        scope_json=canonical_scope,
        status="OFFERED",
        expires_at=command.expires_at,
        created_by_advocate_id=assignment.advocate_id,
        created_by_identity_id=identity.id,
    )
    db.add(quote)
    db.flush()
    previous = order.state
    order.state = "ACCEPTED_AND_QUOTED"
    order.current_step = "customer_quote_acceptance"
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="ADVOCATE",
            event_type="DOCUMENT_QUOTE_CREATED",
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "quote_id": quote.id,
                    "quote_version": quote.quote_version,
                    "amount_minor": quote.amount_minor,
                    "currency": quote.currency,
                    "scope_hash": quote.scope_hash,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "QUOTE_CREATED",
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "quote": {
                "id": quote.id,
                "version": quote.quote_version,
                "amount_minor": quote.amount_minor,
                "currency": quote.currency,
                "scope_version": quote.scope_version,
                "expires_at": quote.expires_at.isoformat(),
            },
        },
    )


def _accept_quote(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: AcceptQuote,
) -> NoticeWorkflowResult:
    if actor.actor_type != "CLIENT" or actor.identity_id != order.user_id:
        return NoticeWorkflowResult(False, "ORDER_OWNER_REQUIRED")
    if order.state != "ACCEPTED_AND_QUOTED":
        return NoticeWorkflowResult(False, "QUOTE_ACCEPTANCE_STATE_INVALID")
    quote = db.get(DocumentQuote, command.quote_id)
    if (
        quote is None
        or quote.document_order_id != order.id
        or quote.status != "OFFERED"
    ):
        return NoticeWorkflowResult(False, "QUOTE_NOT_AVAILABLE")
    if quote.expires_at <= utc_now():
        previous = order.state
        quote.status = "EXPIRED"
        order.state = "ADVOCATE_TRIAGE"
        order.current_step = "advocate_quote"
        order.price_minor = None
        order.exception_code = "QUOTE_EXPIRED"
        db.add(
            DocumentAuditEvent(
                document_order_id=order.id,
                actor_type="CLIENT",
                event_type="DOCUMENT_QUOTE_EXPIRED",
                from_state=previous,
                to_state=order.state,
                details_json=_canonical(
                    {
                        "quote_id": quote.id,
                        "quote_version": quote.quote_version,
                        "scope_hash": quote.scope_hash,
                    }
                ),
            )
        )
        return NoticeWorkflowResult(False, "QUOTE_EXPIRED")
    quote.status = "ACCEPTED"
    quote.accepted_at = utc_now()
    previous = order.state
    order.state = "QUOTE_ACCEPTED"
    order.current_step = "payment"
    order.price_minor = quote.amount_minor
    order.currency = quote.currency
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="CLIENT",
            event_type="DOCUMENT_QUOTE_ACCEPTED",
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "quote_id": quote.id,
                    "quote_version": quote.quote_version,
                    "amount_minor": quote.amount_minor,
                    "currency": quote.currency,
                    "scope_hash": quote.scope_hash,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "QUOTE_ACCEPTED",
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "price_minor": order.price_minor,
            "currency": order.currency,
            "quote_id": quote.id,
        },
    )


def _request_payment(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    *,
    payment_client=None,
) -> NoticeWorkflowResult:
    if actor.actor_type != "CLIENT" or actor.identity_id != order.user_id:
        return NoticeWorkflowResult(False, "ORDER_OWNER_REQUIRED")
    if order.state != "QUOTE_ACCEPTED":
        return NoticeWorkflowResult(False, "QUOTE_ACCEPTANCE_REQUIRED")
    quote = (
        db.query(DocumentQuote)
        .filter(
            DocumentQuote.document_order_id == order.id,
            DocumentQuote.status == "ACCEPTED",
        )
        .order_by(DocumentQuote.quote_version.desc())
        .first()
    )
    if quote is None:
        return NoticeWorkflowResult(False, "ACCEPTED_QUOTE_MISSING")
    user = db.get(User, order.user_id)
    if user is None:
        return NoticeWorkflowResult(False, "ORDER_OWNER_MISSING")
    previous = order.state
    try:
        payment_url = create_advocate_quote_payment_link(
            order,
            quote,
            user,
            client=payment_client,
        )
    except Exception:
        order.state = "NEEDS_ATTENTION"
        order.exception_code = "PAYMENT_LINK_CREATE_FAILED"
        return NoticeWorkflowResult(False, "PAYMENT_LINK_CREATE_FAILED")
    order.exception_code = None
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="CLIENT",
            event_type="DOCUMENT_PAYMENT_LINK_CREATED",
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "quote_id": quote.id,
                    "quote_scope_hash": quote.scope_hash,
                    "amount_minor": quote.amount_minor,
                    "currency": quote.currency,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "PAYMENT_PENDING",
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "payment_url": payment_url,
            "amount_minor": quote.amount_minor,
            "currency": quote.currency,
            "quote_id": quote.id,
        },
    )


def _store_evidence(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: StoreEvidence,
    *,
    evidence_vault=None,
    file_scanner=None,
) -> NoticeWorkflowResult:
    kind = command.kind.strip().upper()
    owner_allowed = (
        actor.actor_type == "CLIENT" and actor.identity_id == order.user_id
    )
    advocate_assignment, _ = _advocate_assignment(db, order, actor)
    advocate_allowed = advocate_assignment is not None
    operator = (
        db.get(AdminOperator, actor.identity_id)
        if actor.actor_type == "OPERATOR"
        else None
    )
    operator_allowed = bool(
        operator
        and operator.active
        and operator.mfa_enrolled_at is not None
        and operator.role in {"ADMIN", "OPERATOR"}
        and kind == "DISPATCH_PROOF"
    )
    if not (owner_allowed or advocate_allowed or operator_allowed):
        return NoticeWorkflowResult(False, "EVIDENCE_UPLOAD_NOT_AUTHORIZED")
    if (
        order.output_classification != "ADVOCATE_ISSUED_NOTICE"
        or order.state
        not in {"INTAKE", "EVIDENCE_PENDING", "ADVOCATE_TRIAGE", "ISSUED"}
        or not order.active_revision_number
        or (order.state == "ISSUED" and kind != "DISPATCH_PROOF")
    ):
        return NoticeWorkflowResult(False, "EVIDENCE_ORDER_STATE_INVALID")
    content_type = command.content_type.strip().lower()
    content = command.content
    if (
        kind not in _EVIDENCE_KINDS
        or content_type not in _EVIDENCE_CONTENT_TYPES
        or not isinstance(content, bytes)
        or not 0 < len(content) <= _MAX_EVIDENCE_BYTES
        or command.expires_at <= utc_now()
    ):
        return NoticeWorkflowResult(False, "EVIDENCE_FILE_INVALID")
    if file_scanner is None:
        return NoticeWorkflowResult(False, "EVIDENCE_SCANNER_REQUIRED")
    content_hash = hashlib.sha256(content).hexdigest()
    scan_status = str(
        file_scanner(
            content=content,
            content_type=content_type,
            content_hash=content_hash,
        )
        or ""
    ).strip().upper()
    if scan_status != "CLEAN":
        return NoticeWorkflowResult(False, "EVIDENCE_SCAN_REJECTED")
    evidence_ref = "EVD-" + secrets.token_hex(6).upper()
    vault = evidence_vault or S3EvidenceVault()
    stored = vault.put(
        order_ref=order.public_ref,
        evidence_ref=evidence_ref,
        content=content,
        content_type=content_type,
        content_hash=content_hash,
    )
    evidence = DocumentEvidenceArtifact(
        public_ref=evidence_ref,
        document_order_id=order.id,
        revision_number=order.active_revision_number,
        evidence_kind=kind,
        state="AVAILABLE",
        storage_provider=(
            "MEMORY_TEST_ONLY"
            if stored.bucket == "memory-evidence-test-only"
            else "S3"
        ),
        bucket=stored.bucket,
        object_key=stored.object_key,
        content_type=content_type,
        size_bytes=stored.size_bytes,
        content_hash=content_hash,
        scan_status=scan_status,
        review_status="PENDING",
        uploaded_by_type=actor.actor_type,
        uploaded_by_ref=str(actor.identity_id),
        expires_at=command.expires_at,
    )
    db.add(evidence)
    db.flush()
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type=actor.actor_type,
            event_type="DOCUMENT_EVIDENCE_STORED",
            from_state=order.state,
            to_state=order.state,
            details_json=_canonical(
                {
                    "evidence_ref": evidence.public_ref,
                    "kind": evidence.evidence_kind,
                    "content_hash": evidence.content_hash,
                    "size_bytes": evidence.size_bytes,
                    "scan_status": evidence.scan_status,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "EVIDENCE_STORED",
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "evidence": {
                "reference": evidence.public_ref,
                "kind": evidence.evidence_kind,
                "content_type": evidence.content_type,
                "size_bytes": evidence.size_bytes,
                "content_hash": evidence.content_hash,
                "scan_status": evidence.scan_status,
                "review_status": evidence.review_status,
            },
        },
    )


def _issue_evidence_link(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: IssueEvidenceLink,
    *,
    evidence_vault=None,
) -> NoticeWorkflowResult:
    evidence = (
        db.query(DocumentEvidenceArtifact)
        .filter(
            DocumentEvidenceArtifact.document_order_id == order.id,
            DocumentEvidenceArtifact.public_ref == command.evidence_ref,
        )
        .first()
    )
    owner_allowed = (
        actor.actor_type == "CLIENT" and actor.identity_id == order.user_id
    )
    advocate_assignment, _ = _advocate_assignment(db, order, actor)
    advocate_allowed = advocate_assignment is not None
    if evidence is None or not (owner_allowed or advocate_allowed):
        db.add(
            DocumentAccessEvent(
                document_order_id=order.id,
                document_evidence_artifact_id=(evidence.id if evidence else None),
                actor_type=actor.actor_type,
                actor_ref=str(actor.identity_id),
                action="EVIDENCE_DOWNLOAD",
                decision="DENIED",
                reason_code="EVIDENCE_ACCESS_DENIED",
            )
        )
        return NoticeWorkflowResult(False, "EVIDENCE_ACCESS_DENIED")
    if (
        evidence.state != "AVAILABLE"
        or evidence.scan_status != "CLEAN"
        or evidence.expires_at <= utc_now()
    ):
        db.add(
            DocumentAccessEvent(
                document_order_id=order.id,
                document_evidence_artifact_id=evidence.id,
                actor_type=actor.actor_type,
                actor_ref=str(actor.identity_id),
                action="EVIDENCE_DOWNLOAD",
                decision="DENIED",
                reason_code="EVIDENCE_NOT_AVAILABLE",
            )
        )
        return NoticeWorkflowResult(False, "EVIDENCE_NOT_AVAILABLE")
    vault = evidence_vault or S3EvidenceVault()
    download_url = vault.download_url(evidence.object_key)
    db.add(
        DocumentAccessEvent(
            document_order_id=order.id,
            document_evidence_artifact_id=evidence.id,
            actor_type=actor.actor_type,
            actor_ref=str(actor.identity_id),
            action="EVIDENCE_DOWNLOAD_URL_ISSUED",
            decision="ALLOWED",
            reason_code=("OWNER" if owner_allowed else "ASSIGNED_ADVOCATE"),
        )
    )
    return NoticeWorkflowResult(
        True,
        "EVIDENCE_LINK_READY",
        {
            "evidence_ref": evidence.public_ref,
            "download_url": download_url,
        },
    )


def _record_verified_payment(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: RecordVerifiedPayment,
) -> NoticeWorkflowResult:
    if actor.actor_type not in {"PROVIDER", "SYSTEM"}:
        return NoticeWorkflowResult(False, "PAYMENT_ACTOR_INVALID")
    payment_id = command.payment_id.strip()
    currency = command.currency.strip().upper()
    if order.payment_processed:
        if order.razorpay_payment_id == payment_id:
            return NoticeWorkflowResult(True, "ALREADY_PROCESSED")
        return NoticeWorkflowResult(False, "PAYMENT_CONFLICT")
    if (
        order.state != "PAYMENT_PENDING"
        or not re.fullmatch(r"pay_[A-Za-z0-9_-]{1,251}", payment_id)
        or command.amount_minor != order.price_minor
        or currency != order.currency
    ):
        return NoticeWorkflowResult(False, "PAYMENT_EVIDENCE_MISMATCH")
    quote = (
        db.query(DocumentQuote)
        .filter(
            DocumentQuote.document_order_id == order.id,
            DocumentQuote.status == "ACCEPTED",
            DocumentQuote.amount_minor == command.amount_minor,
            DocumentQuote.currency == currency,
        )
        .order_by(DocumentQuote.quote_version.desc())
        .first()
    )
    if quote is None:
        return NoticeWorkflowResult(False, "ACCEPTED_QUOTE_MISSING")
    previous = order.state
    order.payment_processed = True
    order.razorpay_payment_id = payment_id
    order.paid_at = utc_now()
    order.state = "ADVOCATE_DRAFTING"
    order.current_step = "advocate_drafting"
    order.exception_code = None
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type=actor.actor_type,
            event_type="DOCUMENT_NOTICE_PAYMENT_VERIFIED",
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "payment_id_hash": hashlib.sha256(
                        payment_id.encode("utf-8")
                    ).hexdigest(),
                    "quote_id": quote.id,
                    "quote_scope_hash": quote.scope_hash,
                    "amount_minor": command.amount_minor,
                    "currency": currency,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "ADVOCATE_DRAFTING",
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "payment_processed": True,
            "amount_minor": order.price_minor,
            "currency": order.currency,
        },
    )


def _scanned_pdf(
    content: bytes,
    file_scanner,
) -> tuple[str | None, str | None]:
    if (
        not isinstance(content, bytes)
        or not content.startswith(b"%PDF-")
        or not 0 < len(content) <= _MAX_EVIDENCE_BYTES
    ):
        return None, "NOTICE_PDF_INVALID"
    if file_scanner is None:
        return None, "EVIDENCE_SCANNER_REQUIRED"
    content_hash = hashlib.sha256(content).hexdigest()
    scan_status = str(
        file_scanner(
            content=content,
            content_type="application/pdf",
            content_hash=content_hash,
        )
        or ""
    ).strip().upper()
    if scan_status != "CLEAN":
        return None, "EVIDENCE_SCAN_REJECTED"
    return content_hash, None


def _store_notice_artifact(
    db,
    order: DocumentOrder,
    *,
    artifact_kind: str,
    content: bytes,
    content_hash: str,
    expires_at: datetime,
    artifact_vault,
) -> DocumentArtifact:
    manifest_hash = hashlib.sha256(
        _canonical(
            {
                "order_ref": order.public_ref,
                "revision_number": order.active_revision_number,
                "artifact_kind": artifact_kind,
                "content_hash": content_hash,
                "template_version": order.template_version,
            }
        ).encode("utf-8")
    ).hexdigest()
    vault = artifact_vault or S3ArtifactVault()
    stored = vault.put(
        order_ref=order.public_ref,
        revision_number=order.active_revision_number,
        artifact_kind=artifact_kind,
        content=content,
        content_type="application/pdf",
        content_hash=content_hash,
        manifest_hash=manifest_hash,
    )
    artifact = DocumentArtifact(
        public_ref="DSA-" + secrets.token_hex(6).upper(),
        document_order_id=order.id,
        revision_number=order.active_revision_number,
        artifact_kind=artifact_kind,
        state="AVAILABLE",
        storage_provider=(
            "MEMORY_TEST_ONLY"
            if stored.bucket == "memory-test-only"
            else "S3"
        ),
        bucket=stored.bucket,
        object_key=stored.object_key,
        content_type="application/pdf",
        size_bytes=stored.size_bytes,
        content_hash=content_hash,
        manifest_hash=manifest_hash,
        renderer_version="advocate-upload-v1",
        expires_at=expires_at,
    )
    db.add(artifact)
    db.flush()
    return artifact


def _submit_draft_for_fact_check(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: SubmitDraftForFactCheck,
    *,
    artifact_vault=None,
    file_scanner=None,
) -> NoticeWorkflowResult:
    assignment, _ = _advocate_assignment(db, order, actor)
    if assignment is None or assignment.status != "ACCEPTED":
        return NoticeWorkflowResult(False, "ASSIGNED_ADVOCATE_REQUIRED")
    if (
        order.state != "ADVOCATE_DRAFTING"
        or not order.payment_processed
        or not order.active_revision_number
        or command.expires_at <= utc_now()
    ):
        return NoticeWorkflowResult(False, "NOTICE_DRAFT_STATE_INVALID")
    content_hash, scan_error = _scanned_pdf(command.content, file_scanner)
    if scan_error:
        return NoticeWorkflowResult(False, scan_error)
    artifact = _store_notice_artifact(
        db,
        order,
        artifact_kind="NOTICE_DRAFT_PDF",
        content=command.content,
        content_hash=content_hash,
        expires_at=command.expires_at,
        artifact_vault=artifact_vault,
    )
    previous = order.state
    order.state = "CUSTOMER_FACT_CHECK"
    order.current_step = "customer_fact_check"
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="ADVOCATE",
            event_type="DOCUMENT_NOTICE_DRAFT_SUBMITTED",
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "artifact_ref": artifact.public_ref,
                    "artifact_hash": artifact.content_hash,
                    "revision_number": artifact.revision_number,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "CUSTOMER_FACT_CHECK",
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "artifact": {
                "reference": artifact.public_ref,
                "content_hash": artifact.content_hash,
                "revision_number": artifact.revision_number,
            },
        },
    )


def _confirm_notice_facts(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: ConfirmNoticeFacts,
) -> NoticeWorkflowResult:
    if actor.actor_type != "CLIENT" or actor.identity_id != order.user_id:
        return NoticeWorkflowResult(False, "ORDER_OWNER_REQUIRED")
    if order.state != "CUSTOMER_FACT_CHECK":
        return NoticeWorkflowResult(False, "FACT_CHECK_STATE_INVALID")
    artifact = (
        db.query(DocumentArtifact)
        .filter(
            DocumentArtifact.document_order_id == order.id,
            DocumentArtifact.public_ref == command.candidate_artifact_ref,
            DocumentArtifact.artifact_kind == "NOTICE_DRAFT_PDF",
            DocumentArtifact.revision_number == order.active_revision_number,
            DocumentArtifact.state == "AVAILABLE",
        )
        .first()
    )
    if artifact is None or artifact.expires_at <= utc_now():
        return NoticeWorkflowResult(False, "NOTICE_DRAFT_NOT_AVAILABLE")
    previous = order.state
    order.state = "ADVOCATE_FINAL_APPROVAL"
    order.current_step = "advocate_final_approval"
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="CLIENT",
            event_type="DOCUMENT_NOTICE_FACTS_CONFIRMED",
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "artifact_ref": artifact.public_ref,
                    "artifact_hash": artifact.content_hash,
                    "revision_number": artifact.revision_number,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "ADVOCATE_FINAL_APPROVAL",
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "candidate_artifact_ref": artifact.public_ref,
            "candidate_artifact_hash": artifact.content_hash,
        },
    )


def _approve_issued_artifact(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: ApproveIssuedArtifact,
    *,
    artifact_vault=None,
    file_scanner=None,
) -> NoticeWorkflowResult:
    assignment, identity = _advocate_assignment(db, order, actor)
    if assignment is None or identity is None or assignment.status != "ACCEPTED":
        return NoticeWorkflowResult(False, "ASSIGNED_ADVOCATE_REQUIRED")
    signing_method = command.signing_method.strip().upper()
    if (
        order.state != "ADVOCATE_FINAL_APPROVAL"
        or not order.payment_processed
        or signing_method != "ADVOCATE_OFFLINE_SIGNED_UPLOAD"
        or command.expires_at <= utc_now()
    ):
        return NoticeWorkflowResult(False, "ISSUE_APPROVAL_STATE_INVALID")
    candidate = (
        db.query(DocumentArtifact)
        .filter(
            DocumentArtifact.document_order_id == order.id,
            DocumentArtifact.public_ref == command.candidate_artifact_ref,
            DocumentArtifact.artifact_kind == "NOTICE_DRAFT_PDF",
            DocumentArtifact.revision_number == order.active_revision_number,
            DocumentArtifact.state == "AVAILABLE",
        )
        .first()
    )
    if candidate is None:
        return NoticeWorkflowResult(False, "CONFIRMED_DRAFT_MISSING")
    fact_confirmed = False
    for event in (
        db.query(DocumentAuditEvent)
        .filter(
            DocumentAuditEvent.document_order_id == order.id,
            DocumentAuditEvent.event_type == "DOCUMENT_NOTICE_FACTS_CONFIRMED",
        )
        .order_by(DocumentAuditEvent.id.desc())
        .all()
    ):
        try:
            details = json.loads(event.details_json)
        except (TypeError, ValueError):
            continue
        if (
            details.get("artifact_ref") == candidate.public_ref
            and details.get("artifact_hash") == candidate.content_hash
            and details.get("revision_number") == order.active_revision_number
        ):
            fact_confirmed = True
            break
    if not fact_confirmed:
        return NoticeWorkflowResult(False, "CUSTOMER_FACT_CONFIRMATION_MISSING")
    content_hash, scan_error = _scanned_pdf(command.signed_content, file_scanner)
    if scan_error:
        return NoticeWorkflowResult(False, scan_error)
    issued_artifact = _store_notice_artifact(
        db,
        order,
        artifact_kind="ISSUED_PDF",
        content=command.signed_content,
        content_hash=content_hash,
        expires_at=command.expires_at,
        artifact_vault=artifact_vault,
    )
    approval = DocumentIssueApproval(
        document_order_id=order.id,
        assignment_id=assignment.id,
        revision_number=order.active_revision_number,
        candidate_artifact_id=candidate.id,
        issued_artifact_id=issued_artifact.id,
        artifact_hash=issued_artifact.content_hash,
        template_version=order.template_version,
        decision="APPROVED",
        advocate_id=assignment.advocate_id,
        advocate_identity_id=identity.id,
        signing_method=signing_method,
        conditions=command.conditions,
    )
    db.add(approval)
    db.flush()
    previous = order.state
    order.state = "ISSUED"
    order.current_step = "issued"
    order.final_available_until = command.expires_at
    order.release_status = "ISSUED"
    assignment.status = "ISSUED"
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="ADVOCATE",
            event_type="DOCUMENT_NOTICE_ISSUED",
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "approval_id": approval.id,
                    "artifact_ref": issued_artifact.public_ref,
                    "artifact_hash": issued_artifact.content_hash,
                    "candidate_artifact_hash": candidate.content_hash,
                    "revision_number": approval.revision_number,
                    "signing_method": approval.signing_method,
                }
            ),
        )
    )
    from services.outbox_service import (
        DOCUMENT_FINAL_DELIVERY_KIND,
        enqueue_job,
    )

    enqueue_job(
        db,
        DOCUMENT_FINAL_DELIVERY_KIND,
        {"document_order_id": order.id},
        dedupe_key=f"document-issued:{approval.id}:final-delivery",
    )
    return NoticeWorkflowResult(
        True,
        "ISSUED",
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "approval": {
                "id": approval.id,
                "advocate_id": approval.advocate_id,
                "revision_number": approval.revision_number,
                "artifact_ref": issued_artifact.public_ref,
                "artifact_hash": approval.artifact_hash,
                "signing_method": approval.signing_method,
            },
        },
    )


def _issue_issued_artifact_link(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    *,
    artifact_vault=None,
) -> NoticeWorkflowResult:
    owner_allowed = (
        actor.actor_type in {"CLIENT", "SYSTEM"}
        and actor.identity_id == order.user_id
    )
    if not owner_allowed:
        db.add(
            DocumentAccessEvent(
                document_order_id=order.id,
                actor_type=actor.actor_type,
                actor_ref=str(actor.identity_id),
                action="DOWNLOAD",
                decision="DENIED",
                reason_code="ISSUED_ARTIFACT_ACCESS_DENIED",
            )
        )
        return NoticeWorkflowResult(False, "ISSUED_ARTIFACT_ACCESS_DENIED")
    if (
        order.output_classification != "ADVOCATE_ISSUED_NOTICE"
        or order.state not in {"ISSUED", "DISPATCH_RECORDED"}
        or not order.payment_processed
        or order.final_available_until is None
        or order.final_available_until <= utc_now()
    ):
        db.add(
            DocumentAccessEvent(
                document_order_id=order.id,
                actor_type=actor.actor_type,
                actor_ref=str(actor.identity_id),
                action="DOWNLOAD",
                decision="DENIED",
                reason_code="ISSUED_ARTIFACT_NOT_AVAILABLE",
            )
        )
        return NoticeWorkflowResult(False, "ISSUED_ARTIFACT_NOT_AVAILABLE")
    approval = (
        db.query(DocumentIssueApproval)
        .filter(
            DocumentIssueApproval.document_order_id == order.id,
            DocumentIssueApproval.revision_number
            == order.active_revision_number,
            DocumentIssueApproval.decision == "APPROVED",
            DocumentIssueApproval.revoked_at.is_(None),
        )
        .order_by(DocumentIssueApproval.id.desc())
        .first()
    )
    artifact = (
        db.get(DocumentArtifact, approval.issued_artifact_id)
        if approval is not None
        else None
    )
    if (
        artifact is None
        or artifact.artifact_kind != "ISSUED_PDF"
        or artifact.revision_number != order.active_revision_number
        or artifact.content_hash != approval.artifact_hash
        or artifact.state != "AVAILABLE"
        or artifact.expires_at <= utc_now()
    ):
        db.add(
            DocumentAccessEvent(
                document_order_id=order.id,
                document_artifact_id=(artifact.id if artifact else None),
                actor_type=actor.actor_type,
                actor_ref=str(actor.identity_id),
                action="DOWNLOAD",
                decision="DENIED",
                reason_code="ISSUED_ARTIFACT_NOT_AVAILABLE",
            )
        )
        return NoticeWorkflowResult(False, "ISSUED_ARTIFACT_NOT_AVAILABLE")
    vault = artifact_vault or S3ArtifactVault()
    download_url = vault.download_url(artifact.object_key)
    db.add(
        DocumentAccessEvent(
            document_order_id=order.id,
            document_artifact_id=artifact.id,
            actor_type=actor.actor_type,
            actor_ref=str(actor.identity_id),
            action="DOWNLOAD_URL_ISSUED",
            decision="ALLOWED",
            reason_code="OWNER_ENTITLED",
        )
    )
    return NoticeWorkflowResult(
        True,
        "ISSUED_ARTIFACT_LINK_READY",
        {
            "artifact_kind": "ISSUED_PDF",
            "artifact_ref": artifact.public_ref,
            "artifact_hash": artifact.content_hash,
            "download_url": download_url,
        },
    )


def _record_dispatch(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: RecordDispatch,
) -> NoticeWorkflowResult:
    operator = (
        db.get(AdminOperator, actor.identity_id)
        if actor.actor_type == "OPERATOR"
        else None
    )
    operator_allowed = bool(
        operator
        and operator.active
        and operator.mfa_enrolled_at is not None
        and operator.role in {"ADMIN", "OPERATOR"}
    )
    advocate_assignment, _ = _advocate_assignment(db, order, actor)
    if not (operator_allowed or advocate_assignment is not None):
        return NoticeWorkflowResult(False, "DISPATCH_ACTOR_NOT_AUTHORIZED")
    method = command.method.strip().upper()
    tracking_reference = command.tracking_reference.strip()
    if (
        order.state != "ISSUED"
        or method != "SPEED_POST_REGISTERED"
        or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9./_-]{5,119}", tracking_reference
        )
        or not re.fullmatch(r"[0-9a-f]{64}", command.address_snapshot_hash)
        or command.occurred_at > utc_now() + timedelta(minutes=5)
    ):
        return NoticeWorkflowResult(False, "DISPATCH_EVIDENCE_INVALID")
    approval = (
        db.query(DocumentIssueApproval)
        .filter(
            DocumentIssueApproval.document_order_id == order.id,
            DocumentIssueApproval.revision_number == order.active_revision_number,
            DocumentIssueApproval.decision == "APPROVED",
            DocumentIssueApproval.revoked_at.is_(None),
        )
        .first()
    )


    proof = (
        db.query(DocumentEvidenceArtifact)
        .filter(
            DocumentEvidenceArtifact.document_order_id == order.id,
            DocumentEvidenceArtifact.public_ref == command.proof_evidence_ref,
            DocumentEvidenceArtifact.evidence_kind == "DISPATCH_PROOF",
            DocumentEvidenceArtifact.scan_status == "CLEAN",
            DocumentEvidenceArtifact.state == "AVAILABLE",
        )
        .first()
    )
    if approval is None or proof is None or proof.expires_at <= utc_now():
        return NoticeWorkflowResult(False, "DISPATCH_PROOF_MISSING")
    existing = (
        db.query(DocumentDispatchEvent)
        .filter(
            DocumentDispatchEvent.document_order_id == order.id,
            DocumentDispatchEvent.status == "DISPATCHED",
        )
        .first()
    )
    if existing is not None:
        return NoticeWorkflowResult(False, "DISPATCH_ALREADY_RECORDED")
    tracking_hash = hashlib.sha256(
        tracking_reference.encode("utf-8")
    ).hexdigest()
    dispatch = DocumentDispatchEvent(
        document_order_id=order.id,
        issue_approval_id=approval.id,
        method=method,
        tracking_reference=tracking_reference,
        tracking_reference_hash=tracking_hash,
        address_snapshot_hash=command.address_snapshot_hash,
        status="DISPATCHED",
        proof_evidence_artifact_id=proof.id,
        recorded_by_type=actor.actor_type,
        recorded_by_ref=str(actor.identity_id),
        occurred_at=command.occurred_at,
    )
    db.add(dispatch)
    previous = order.state
    order.state = "DISPATCH_RECORDED"
    order.current_step = "dispatch_recorded"
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type=actor.actor_type,
            event_type="DOCUMENT_NOTICE_DISPATCH_RECORDED",
            from_state=previous,
            to_state=order.state,
            details_json=_canonical(
                {
                    "method": method,
                    "status": "DISPATCHED",
                    "tracking_reference_hash": tracking_hash,
                    "address_snapshot_hash": command.address_snapshot_hash,
                    "proof_evidence_ref": proof.public_ref,
                }
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "DISPATCH_RECORDED",
        {
            "order_ref": order.public_ref,
            "state": order.state,
            "dispatch": {
                "method": method,
                "status": "DISPATCHED",
                "tracking_reference_hash": tracking_hash,
                "proof_evidence_ref": proof.public_ref,
            },
        },
    )


def _legal_hold_admin(db, actor: WorkflowActor) -> AdminOperator | None:
    if actor.actor_type != "ADMIN":
        return None
    identity = db.get(AdminOperator, actor.identity_id)
    if (
        identity is None
        or not identity.active
        or identity.mfa_enrolled_at is None
        or identity.role != "ADMIN"
    ):
        return None
    return identity


def _open_legal_hold(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: OpenLegalHold,
) -> NoticeWorkflowResult:
    identity = _legal_hold_admin(db, actor)
    if identity is None:
        return NoticeWorkflowResult(False, "LEGAL_HOLD_ADMIN_REQUIRED")
    if order.output_classification != "ADVOCATE_ISSUED_NOTICE":
        return NoticeWorkflowResult(False, "NOTICE_ORDER_REQUIRED")
    reason_code = command.reason_code.strip().upper()
    authority_statement = command.authority_statement.strip()
    if (
        not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", reason_code)
        or not 10 <= len(authority_statement) <= 1_000
    ):
        return NoticeWorkflowResult(False, "LEGAL_HOLD_DETAILS_INVALID")
    active_hold = (
        db.query(DocumentLegalHold)
        .filter(
            DocumentLegalHold.document_order_id == order.id,
            DocumentLegalHold.status == "ACTIVE",
        )
        .first()
    )
    if active_hold is not None:
        return NoticeWorkflowResult(False, "LEGAL_HOLD_ALREADY_ACTIVE")
    hold = DocumentLegalHold(
        document_order_id=order.id,
        status="ACTIVE",
        reason_code=reason_code,
        authority_statement=authority_statement,
        opened_by_identity_id=identity.id,
    )
    db.add(hold)
    db.flush()
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="ADMIN",
            event_type="DOCUMENT_LEGAL_HOLD_OPENED",
            from_state=order.state,
            to_state=order.state,
            details_json=_canonical(
                {"hold_id": hold.id, "reason_code": reason_code}
            ),
        )
    )
    return NoticeWorkflowResult(
        True,
        "LEGAL_HOLD_OPENED",
        {
            "order_ref": order.public_ref,
            "hold_id": hold.id,
            "hold_status": hold.status,
            "reason_code": hold.reason_code,
        },
    )


def _close_legal_hold(
    db,
    order: DocumentOrder,
    actor: WorkflowActor,
    command: CloseLegalHold,
) -> NoticeWorkflowResult:
    identity = _legal_hold_admin(db, actor)
    if identity is None:
        return NoticeWorkflowResult(False, "LEGAL_HOLD_ADMIN_REQUIRED")
    closure_reason = command.closure_reason.strip()
    if not 10 <= len(closure_reason) <= 1_000:
        return NoticeWorkflowResult(False, "LEGAL_HOLD_DETAILS_INVALID")
    hold = db.get(DocumentLegalHold, command.hold_id)
    if (
        hold is None
        or hold.document_order_id != order.id
        or hold.status != "ACTIVE"
    ):
        return NoticeWorkflowResult(False, "ACTIVE_LEGAL_HOLD_NOT_FOUND")
    hold.status = "CLOSED"
    hold.closed_by_identity_id = identity.id
    hold.closed_at = utc_now()
    hold.closure_reason = closure_reason
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="ADMIN",
            event_type="DOCUMENT_LEGAL_HOLD_CLOSED",
            from_state=order.state,
            to_state=order.state,
            details_json=_canonical({"hold_id": hold.id}),
        )
    )
    return NoticeWorkflowResult(
        True,
        "LEGAL_HOLD_CLOSED",
        {
            "order_ref": order.public_ref,
            "hold_id": hold.id,
            "hold_status": hold.status,
        },
    )


def execute_notice_command(
    db,
    order: DocumentOrder,
    *,
    actor: WorkflowActor,
    command: object,
    payment_client=None,
    evidence_vault=None,
    file_scanner=None,
    artifact_vault=None,
) -> NoticeWorkflowResult:
    """Execute one authorized transition for an advocate-issued order."""

    if isinstance(command, EvaluateChequeNoticeIntake):
        return _evaluate_cheque_notice_intake(db, order, actor)
    if isinstance(command, AssignAdvocate):
        return _assign_advocate(db, order, actor, command)
    if isinstance(command, RecordConflictCheck):
        return _record_conflict_check(db, order, actor, command)
    if isinstance(command, RecordMatterDecision):
        return _record_matter_decision(db, order, actor, command)
    if isinstance(command, CreateQuote):
        return _create_quote(db, order, actor, command)
    if isinstance(command, AcceptQuote):
        return _accept_quote(db, order, actor, command)
    if isinstance(command, RequestPayment):
        return _request_payment(
            db,
            order,
            actor,
            payment_client=payment_client,
        )
    if isinstance(command, StoreEvidence):
        return _store_evidence(
            db,
            order,
            actor,
            command,
            evidence_vault=evidence_vault,
            file_scanner=file_scanner,
        )
    if isinstance(command, IssueEvidenceLink):
        return _issue_evidence_link(
            db,
            order,
            actor,
            command,
            evidence_vault=evidence_vault,
        )
    if isinstance(command, IssueIssuedArtifactLink):
        return _issue_issued_artifact_link(
            db,
            order,
            actor,
            artifact_vault=artifact_vault,
        )
    if isinstance(command, RecordVerifiedPayment):
        return _record_verified_payment(db, order, actor, command)
    if isinstance(command, SubmitDraftForFactCheck):
        return _submit_draft_for_fact_check(
            db,
            order,
            actor,
            command,
            artifact_vault=artifact_vault,
            file_scanner=file_scanner,
        )
    if isinstance(command, ConfirmNoticeFacts):
        return _confirm_notice_facts(db, order, actor, command)
    if isinstance(command, ApproveIssuedArtifact):
        return _approve_issued_artifact(
            db,
            order,
            actor,
            command,
            artifact_vault=artifact_vault,
            file_scanner=file_scanner,
        )
    if isinstance(command, RecordDispatch):
        return _record_dispatch(db, order, actor, command)
    if isinstance(command, OpenLegalHold):
        return _open_legal_hold(db, order, actor, command)
    if isinstance(command, CloseLegalHold):
        return _close_legal_hold(db, order, actor, command)
    return NoticeWorkflowResult(False, "NOTICE_COMMAND_UNSUPPORTED")
