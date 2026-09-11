"""Phase E customer intake for the private advocate-issued cheque product.

The Meta Flow is a presentation layer only.  This service owns resumable
server-side progress, input validation, immutable confirmation and the
handover into the existing advocate-issued state machine.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import timedelta
from types import MappingProxyType

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func

from config import (
    CHEQUE_NOTICE_STAGING_UAT_ENABLED,
    DOCUMENT_STUDIO_DRAFT_TTL_DAYS,
    ENV,
    SECRET_KEY,
)
from models import DocumentAnswerRevision, DocumentAuditEvent, DocumentOrder, utc_now
from services.advocate_issued_workflow import (
    EvaluateChequeNoticeIntake,
    WorkflowActor,
    execute_notice_command,
)
from services.cheque_notice_product import golden_answers, validate_intake
from services.document_catalogue import (
    CHEQUE_NOTICE_PRODUCT_CODE,
    customer_visible,
    resolve_product,
)
from services.document_release_service import release_gate


DOCUMENT_NOTICE_FLOW_PENDING = "DOCUMENT_NOTICE_FLOW_PENDING"
FLOW_START_SCREEN = "SUITABILITY"
FLOW_TERMINAL_SCREEN = "SUCCESS"
FLOW_SCREENS = (
    "SUITABILITY",
    "PEOPLE_ADDRESSES",
    "DEBT_CHEQUE",
    "DISHONOUR",
    "EVIDENCE_CHANGES",
    "REVIEW_HANDOVER",
)
SCREEN_FIELDS = MappingProxyType(
    {
        "SUITABILITY": (
            "claimant_scope",
            "instrument_scope",
            "liability_scope",
            "conflict_scope",
        ),
        "PEOPLE_ADDRESSES": (
            "payee_full_name",
            "payee_notice_address",
            "drawer_full_name",
            "drawer_service_address",
            "drawer_alternate_address_present",
            "drawer_alternate_address",
        ),
        "DEBT_CHEQUE": (
            "liability_category",
            "liability_due_date",
            "liability_summary",
            "cheque_number",
            "cheque_date",
            "cheque_amount_inr",
            "payee_name_on_cheque",
            "drawer_bank_name",
            "drawer_bank_branch",
        ),
        "DISHONOUR": (
            "presented_on",
            "return_memo_date",
            "dishonour_information_received_on",
            "return_reason_exact",
            "return_bank_name",
        ),
        "EVIDENCE_CHANGES": (
            "evidence_checklist",
            "post_issue_change",
            "prior_demand_or_notice",
            "existing_proceeding",
        ),
        "REVIEW_HANDOVER": (
            "cheque_amount_confirmation_inr",
            "facts_confirmed",
            "review_consent",
            "contact_permission",
        ),
    }
)
_OPTIONAL_FIELDS = frozenset({"drawer_alternate_address"})
_EDITABLE_SCREENS = frozenset(FLOW_SCREENS[:-1])
_TOKEN_SALT = "nyaysetu-cheque-notice-flow-v1"
_MAX_FLOW_FIELDS = 16


class ChequeNoticeFlowError(ValueError):
    """A bounded fail-closed error safe for status-code mapping."""


def _canonical(value: dict[str, object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _answers(order: DocumentOrder) -> dict[str, object]:
    try:
        value = json.loads(order.draft_answers_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _audit(
    db,
    order: DocumentOrder,
    event_type: str,
    *,
    from_state: str | None = None,
    to_state: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="CLIENT",
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            details_json=_canonical(details or {}),
        )
    )


def latest_resumable_notice_order(db, user_id: int) -> DocumentOrder | None:
    """Return only a current, unfinished cheque-notice intake."""

    updated_after = utc_now() - timedelta(days=DOCUMENT_STUDIO_DRAFT_TTL_DAYS)
    return (
        db.query(DocumentOrder)
        .filter(
            DocumentOrder.user_id == user_id,
            DocumentOrder.product_code == CHEQUE_NOTICE_PRODUCT_CODE,
            DocumentOrder.state.in_(("INTAKE", "EVIDENCE_PENDING")),
            DocumentOrder.updated_at >= updated_after,
        )
        .order_by(DocumentOrder.id.desc())
        .first()
    )


def create_or_resume_notice_order(db, user_id: int) -> DocumentOrder:
    """Create the exact approved product snapshot or resume it unchanged."""

    if ENV != "staging" or not CHEQUE_NOTICE_STAGING_UAT_ENABLED:
        raise ChequeNoticeFlowError("cheque_notice_uat_not_configured")

    product = resolve_product(CHEQUE_NOTICE_PRODUCT_CODE)
    if not customer_visible(product.code):
        raise ChequeNoticeFlowError("document_product_not_enabled")
    if product.output_classification != "ADVOCATE_ISSUED_NOTICE":
        raise ChequeNoticeFlowError("document_product_workflow_unsupported")
    gate = release_gate(db, product.code)
    if not gate.allowed:
        raise ChequeNoticeFlowError(gate.reason_code)

    existing = latest_resumable_notice_order(db, user_id)
    if existing and product.matches_package_snapshot(
        template_version=existing.template_version,
        schema_hash=existing.schema_hash,
        template_hash=existing.template_hash,
        output_classification=existing.output_classification,
    ):
        return existing
    if existing:
        previous = existing.state
        existing.state = "ABANDONED"
        existing.current_step = "superseded"
        existing.exception_code = "SCHEMA_SUPERSEDED"
        _audit(
            db,
            existing,
            "DOCUMENT_SCHEMA_SUPERSEDED",
            from_state=previous,
            to_state=existing.state,
            details={"replacement_schema_hash": product.schema_hash},
        )

    order = DocumentOrder(
        public_ref=f"DS-{secrets.token_hex(6).upper()}",
        user_id=user_id,
        product_code=product.code,
        template_version=product.template_version,
        state="INTAKE",
        current_step=FLOW_START_SCREEN,
        draft_answers_json="{}",
        output_classification=product.output_classification,
        uat_only=True,
        schema_hash=product.schema_hash,
        template_hash=product.template_hash,
        price_minor=None,
        currency=product.currency,
        release_status="CANDIDATE",
    )
    db.add(order)
    db.flush()
    _audit(db, order, "DOCUMENT_ORDER_CREATED", to_state=order.state)
    return order


def cancel_notice_order(db, order: DocumentOrder) -> None:
    if order.product_code != CHEQUE_NOTICE_PRODUCT_CODE:
        raise ChequeNoticeFlowError("document_product_mismatch")
    previous = order.state
    order.state = "ABANDONED"
    order.current_step = "cancelled"
    order.exception_code = "CUSTOMER_CANCELLED"
    _audit(
        db,
        order,
        "DOCUMENT_ORDER_ABANDONED",
        from_state=previous,
        to_state=order.state,
    )


def _serializer() -> URLSafeTimedSerializer:
    if len(str(SECRET_KEY or "")) < 32:
        raise ChequeNoticeFlowError("flow_signing_key_unavailable")
    return URLSafeTimedSerializer(SECRET_KEY, salt=_TOKEN_SALT)


def issue_notice_flow_token(order: DocumentOrder) -> str:
    """Issue a time-limited unguessable capability for one product snapshot."""

    if ENV != "staging" or not CHEQUE_NOTICE_STAGING_UAT_ENABLED:
        raise ChequeNoticeFlowError("cheque_notice_uat_not_configured")
    if order.product_code != CHEQUE_NOTICE_PRODUCT_CODE:
        raise ChequeNoticeFlowError("document_product_mismatch")
    return _serializer().dumps(
        {
            "nonce": secrets.token_urlsafe(24),
            "order_ref": order.public_ref,
            "product_code": order.product_code,
            "schema_hash": order.schema_hash,
        }
    )


def resolve_notice_flow_token(db, token: object) -> DocumentOrder:
    raw = str(token or "").strip()
    if not raw or len(raw) > 1024:
        raise ChequeNoticeFlowError("invalid_flow_token")
    try:
        payload = _serializer().loads(
            raw,
            max_age=DOCUMENT_STUDIO_DRAFT_TTL_DAYS * 86400,
        )
    except SignatureExpired as exc:
        raise ChequeNoticeFlowError("expired_flow_token") from exc
    except BadSignature as exc:
        raise ChequeNoticeFlowError("invalid_flow_token") from exc
    if not isinstance(payload, dict):
        raise ChequeNoticeFlowError("invalid_flow_token")
    order_ref = str(payload.get("order_ref") or "")
    order = (
        db.query(DocumentOrder)
        .filter(DocumentOrder.public_ref == order_ref)
        .with_for_update()
        .one_or_none()
    )
    if (
        order is None
        or payload.get("product_code") != CHEQUE_NOTICE_PRODUCT_CODE
        or order.product_code != CHEQUE_NOTICE_PRODUCT_CODE
        or payload.get("schema_hash") != order.schema_hash
        or order.state not in {"INTAKE", "EVIDENCE_PENDING", "ROUTED_OUT"}
    ):
        raise ChequeNoticeFlowError("invalid_flow_token")
    return order


def _screen_data(
    order: DocumentOrder,
    screen: str,
    *,
    error_message: str = "",
) -> dict[str, object]:
    answers = _answers(order)
    data = {field: str(answers.get(field) or "") for field in SCREEN_FIELDS[screen]}
    data.update(
        {
            "has_error": bool(error_message),
            "error_message": error_message[:300],
        }
    )
    if screen == "REVIEW_HANDOVER":
        data["review_summary"] = _review_summary(order)
    return data


def _review_summary(order: DocumentOrder) -> str:
    answers = _answers(order)
    return (
        f"Payee: {str(answers.get('payee_full_name') or '-')[:160]}\n"
        f"Drawer: {str(answers.get('drawer_full_name') or '-')[:160]}\n"
        f"Cheque: {str(answers.get('cheque_number') or '-')[:20]}\n"
        f"Amount: INR {str(answers.get('cheque_amount_inr') or '-')[:24]}\n"
        f"Cheque date: {str(answers.get('cheque_date') or '-')[:10]}\n"
        f"Memo date: {str(answers.get('return_memo_date') or '-')[:10]}\n"
        "No eligibility, deadline, issuance or outcome has been confirmed."
    )


def _validated_screen_values(
    order: DocumentOrder,
    screen: str,
    supplied: object,
) -> tuple[dict[str, str] | None, str | None]:
    if not isinstance(supplied, dict) or len(supplied) > _MAX_FLOW_FIELDS:
        return None, "Please check every field on this section."
    allowed = set(SCREEN_FIELDS[screen])
    if screen == "REVIEW_HANDOVER":
        allowed.add("edit_section")
    if any(not isinstance(key, str) or key not in allowed for key in supplied):
        return None, "This form contained an unexpected field. Please reopen it."

    required = set(SCREEN_FIELDS[screen]) - _OPTIONAL_FIELDS
    if any(not str(supplied.get(field) or "").strip() for field in required):
        return None, "Please complete every required field on this section."
    candidate = golden_answers()
    candidate.update(_answers(order))
    candidate.update(
        {
            field: supplied[field]
            for field in SCREEN_FIELDS[screen]
            if field in supplied and str(supplied[field] or "").strip()
        }
    )
    if screen == "REVIEW_HANDOVER":
        candidate["review_consent_version"] = "cheque-notice-review-2026-09"
    else:
        candidate["cheque_amount_confirmation_inr"] = candidate.get(
            "cheque_amount_inr",
            "250000.00",
        )
    validation = validate_intake(candidate)
    if validation.status == "INVALID":
        return None, "One or more values are invalid. Check the displayed format."
    values = {
        field: str(validation.normalized_answers[field])
        for field in SCREEN_FIELDS[screen]
        if field in validation.normalized_answers
    }
    if screen == "REVIEW_HANDOVER":
        values["review_consent_version"] = "cheque-notice-review-2026-09"
    return values, None


def _next_screen(screen: str) -> str:
    return FLOW_SCREENS[FLOW_SCREENS.index(screen) + 1]


def handle_notice_flow_request(db, request_body: object) -> dict[str, object]:
    """Handle one decrypted INIT/data_exchange/ping request."""

    if not isinstance(request_body, dict):
        raise ChequeNoticeFlowError("invalid_flow_request")
    action = str(request_body.get("action") or "").strip()
    if action == "ping":
        return {"data": {"status": "active"}}
    data = request_body.get("data")
    if isinstance(data, dict) and data.get("error"):
        return {"data": {"acknowledged": True}}

    token = request_body.get("flow_token")
    order = resolve_notice_flow_token(db, token)
    gate = release_gate(db, CHEQUE_NOTICE_PRODUCT_CODE)
    if not gate.allowed:
        raise ChequeNoticeFlowError("document_release_not_approved")
    if action == "INIT":
        if order.state != "INTAKE" or order.current_step not in FLOW_SCREENS:
            raise ChequeNoticeFlowError("flow_already_completed")
        return {
            "screen": order.current_step,
            "data": _screen_data(order, order.current_step),
        }
    if action != "data_exchange":
        raise ChequeNoticeFlowError("unsupported_flow_action")

    screen = str(request_body.get("screen") or "").strip().upper()
    if (
        order.state != "INTAKE"
        or screen not in FLOW_SCREENS
        or screen != order.current_step
    ):
        raise ChequeNoticeFlowError("flow_screen_out_of_sequence")
    values, error_message = _validated_screen_values(order, screen, data)
    if error_message:
        return {
            "screen": screen,
            "data": _screen_data(order, screen, error_message=error_message),
        }
    assert values is not None

    if screen == "REVIEW_HANDOVER" and values.get("facts_confirmed") == "EDIT":
        target = str((data or {}).get("edit_section") or "").strip().upper()
        if target not in _EDITABLE_SCREENS:
            return {
                "screen": screen,
                "data": _screen_data(
                    order,
                    screen,
                    error_message="Choose the section you want to correct.",
                ),
            }
        answers = _answers(order)
        for field in SCREEN_FIELDS[target]:
            answers.pop(field, None)
        order.draft_answers_json = _canonical(answers)
        order.current_step = target
        _audit(
            db,
            order,
            "DOCUMENT_SECTION_EDIT_STARTED",
            details={"section": target},
        )
        return {"screen": target, "data": _screen_data(order, target)}

    answers = _answers(order)
    answers.update(values)
    order.draft_answers_json = _canonical(answers)
    if screen != "REVIEW_HANDOVER":
        order.current_step = _next_screen(screen)
        _audit(
            db,
            order,
            "DOCUMENT_INTAKE_SECTION_SAVED",
            details={"section": screen},
        )
        return {
            "screen": order.current_step,
            "data": _screen_data(order, order.current_step),
        }

    validation = validate_intake(answers)
    if validation.status == "INVALID":
        return {
            "screen": screen,
            "data": _screen_data(
                order,
                screen,
                error_message="The complete form did not pass validation.",
            ),
        }
    normalized = dict(validation.normalized_answers)
    answers_json = _canonical(normalized)
    last_revision = (
        db.query(func.max(DocumentAnswerRevision.revision_number))
        .filter(DocumentAnswerRevision.document_order_id == order.id)
        .scalar()
        or 0
    )
    revision = DocumentAnswerRevision(
        document_order_id=order.id,
        revision_number=last_revision + 1,
        schema_version=resolve_product(order.product_code).schema_version,
        answers_json=answers_json,
        content_hash=hashlib.sha256(answers_json.encode("utf-8")).hexdigest(),
    )
    db.add(revision)
    order.active_revision_number = revision.revision_number
    order.draft_answers_json = answers_json
    if normalized.get("review_consent") == "YES":
        order.consent_version = normalized.get("review_consent_version")
        order.consented_at = utc_now()
    db.flush()
    result = execute_notice_command(
        db,
        order,
        actor=WorkflowActor("SYSTEM", 0),
        command=EvaluateChequeNoticeIntake(),
    )
    if not result.ok:
        raise ChequeNoticeFlowError(result.code)
    return {
        "screen": FLOW_TERMINAL_SCREEN,
        "data": {
            "extension_message_response": {
                "params": {
                    "flow_token": str(token),
                    "order_ref": order.public_ref,
                    "status": order.state,
                }
            }
        },
    }


def completion_for_user(
    db,
    response: object,
    *,
    user_id: int,
) -> DocumentOrder:
    """Bind the terminal webhook acknowledgement back to its owner."""

    if not isinstance(response, dict) or len(response) > 8:
        raise ChequeNoticeFlowError("invalid_flow_completion")
    order = resolve_notice_flow_token(db, response.get("flow_token"))
    if (
        order.user_id != user_id
        or order.state not in {"EVIDENCE_PENDING", "ROUTED_OUT"}
        or response.get("order_ref") != order.public_ref
        or response.get("status") != order.state
    ):
        raise ChequeNoticeFlowError("invalid_flow_completion")
    return order
