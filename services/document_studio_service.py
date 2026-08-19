"""Safe, staging-only Document Studio workflow primitives.

This module deliberately does not generate a legal document, take payment,
collect signatures, upload files, or create a public download.  It provides a
small synthetic-data UAT flow so navigation, validation, resumption, consent,
database persistence, and audit evidence can be tested before any legal
template is approved.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import timedelta

from sqlalchemy import func

from config import (
    DOCUMENT_STUDIO_CONSENT_VERSION,
    DOCUMENT_STUDIO_DRAFT_TTL_DAYS,
    DOCUMENT_STUDIO_ENABLED,
    DOCUMENT_STUDIO_PRODUCT_ALLOWLIST,
    DOCUMENT_STUDIO_TESTER_WA_IDS,
    DOCUMENT_STUDIO_UAT_ONLY,
    ENV,
)
from models import (
    DocumentAnswerRevision,
    DocumentAuditEvent,
    DocumentOrder,
    utc_now,
)


UAT_PRODUCT_CODE = "residential_agreement_mh_uat"
UAT_TEMPLATE_VERSION = "uat-schema-2026-08-v1"
UAT_OUTPUT_CLASSIFICATION = "UAT_NON_LEGAL"

DOCUMENT_STUDIO_IDS = {
    "create": "doc_create",
    "continue": "doc_continue",
    "mine": "doc_mine",
    "help": "doc_help",
    "back": "doc_back_home",
    "confirm": "doc_uat_confirm",
    "edit": "doc_uat_edit",
    "cancel": "doc_uat_cancel",
}
PRODUCT_ID_PREFIX = "doc_product::"
START_ID_PREFIX = "doc_start::"

DOCUMENT_STUDIO_QUESTION = "DOCUMENT_STUDIO_QUESTION"
DOCUMENT_STUDIO_REVIEW = "DOCUMENT_STUDIO_REVIEW"

_ACTIVE_STATES = ("DRAFT",)
_LABEL_PATTERN = re.compile(r"^[^\r\n<>]{2,60}$")

_QUESTION_DEFINITIONS = (
    {
        "key": "party_a_label",
        "translation_key": "document_uat_party_a_prompt",
    },
    {
        "key": "party_b_label",
        "translation_key": "document_uat_party_b_prompt",
    },
    {
        "key": "premises_city",
        "translation_key": "document_uat_city_prompt",
    },
    {
        "key": "term_months",
        "translation_key": "document_uat_term_prompt",
    },
)


def document_studio_available(user=None) -> bool:
    """Return whether the intentionally limited UAT feature may be exposed."""

    tester_wa_id = str(getattr(user, "whatsapp_id", "") or "").strip()
    return bool(
        DOCUMENT_STUDIO_ENABLED
        and DOCUMENT_STUDIO_UAT_ONLY
        and ENV in {"development", "test", "staging"}
        and UAT_PRODUCT_CODE in DOCUMENT_STUDIO_PRODUCT_ALLOWLIST
        and tester_wa_id in DOCUMENT_STUDIO_TESTER_WA_IDS
    )


def home_rows(user, translate) -> list[dict[str, str]]:
    """Return the four-row home menu used when Document Studio UAT is on."""

    return [
        {
            "id": "home_ai",
            "title": translate(user, "ask_ai"),
            "description": translate(user, "home_ai_desc"),
        },
        {
            "id": "home_book",
            "title": translate(user, "book_consult"),
            "description": translate(user, "home_book_desc"),
        },
        {
            "id": "home_documents",
            "title": translate(user, "document_studio"),
            "description": translate(user, "document_studio_desc"),
        },
        {
            "id": "home_more",
            "title": translate(user, "more_options"),
            "description": translate(user, "home_more_desc"),
        },
    ]


def landing_rows(user, translate) -> list[dict[str, str]]:
    return [
        {
            "id": DOCUMENT_STUDIO_IDS["create"],
            "title": translate(user, "document_create_test"),
            "description": translate(user, "document_create_test_desc"),
        },
        {
            "id": DOCUMENT_STUDIO_IDS["continue"],
            "title": translate(user, "document_continue"),
            "description": translate(user, "document_continue_desc"),
        },
        {
            "id": DOCUMENT_STUDIO_IDS["mine"],
            "title": translate(user, "document_my_tests"),
            "description": translate(user, "document_my_tests_desc"),
        },
        {
            "id": DOCUMENT_STUDIO_IDS["help"],
            "title": translate(user, "document_help"),
            "description": translate(user, "document_help_desc"),
        },
    ]


def product_rows(user, translate) -> list[dict[str, str]]:
    if UAT_PRODUCT_CODE not in DOCUMENT_STUDIO_PRODUCT_ALLOWLIST:
        return []
    return [
        {
            "id": f"{PRODUCT_ID_PREFIX}{UAT_PRODUCT_CODE}",
            "title": translate(user, "document_uat_product"),
            "description": translate(user, "document_uat_product_desc"),
        }
    ]


def parse_product_id(value: str | None, *, start: bool = False) -> str | None:
    prefix = START_ID_PREFIX if start else PRODUCT_ID_PREFIX
    raw = str(value or "")
    if not raw.startswith(prefix):
        return None
    product_code = raw[len(prefix):]
    if product_code != UAT_PRODUCT_CODE:
        return None
    if product_code not in DOCUMENT_STUDIO_PRODUCT_ALLOWLIST:
        return None
    return product_code


def _answers(order: DocumentOrder) -> dict[str, object]:
    try:
        value = json.loads(order.draft_answers_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _audit(
    db,
    order: DocumentOrder,
    event_type: str,
    *,
    from_state: str | None = None,
    to_state: str | None = None,
) -> None:
    db.add(
        DocumentAuditEvent(
            document_order_id=order.id,
            actor_type="CLIENT",
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            details_json="{}",
        )
    )


def latest_draft(db, user_id: int) -> DocumentOrder | None:
    updated_after = utc_now() - timedelta(
        days=DOCUMENT_STUDIO_DRAFT_TTL_DAYS
    )
    return (
        db.query(DocumentOrder)
        .filter(
            DocumentOrder.user_id == user_id,
            DocumentOrder.state.in_(_ACTIVE_STATES),
            DocumentOrder.uat_only.is_(True),
            DocumentOrder.updated_at >= updated_after,
        )
        .order_by(DocumentOrder.id.desc())
        .first()
    )


def create_or_resume_uat_order(db, user_id: int) -> DocumentOrder:
    existing = latest_draft(db, user_id)
    if existing:
        return existing

    order = DocumentOrder(
        public_ref=f"DSU-{secrets.token_hex(4).upper()}",
        user_id=user_id,
        product_code=UAT_PRODUCT_CODE,
        template_version=UAT_TEMPLATE_VERSION,
        state="DRAFT",
        current_step=_QUESTION_DEFINITIONS[0]["key"],
        draft_answers_json="{}",
        output_classification=UAT_OUTPUT_CLASSIFICATION,
        uat_only=True,
    )
    db.add(order)
    db.flush()
    _audit(db, order, "UAT_ORDER_CREATED", to_state="DRAFT")
    return order


def current_question(order: DocumentOrder) -> dict[str, str]:
    for question in _QUESTION_DEFINITIONS:
        if question["key"] == order.current_step:
            return question
    order.current_step = _QUESTION_DEFINITIONS[0]["key"]
    return _QUESTION_DEFINITIONS[0]


def validate_answer(question_key: str, raw_value: str) -> str | None:
    value = str(raw_value or "").strip()
    if question_key in {"party_a_label", "party_b_label", "premises_city"}:
        return value if _LABEL_PATTERN.fullmatch(value) else None
    if question_key == "term_months":
        if not value.isdigit():
            return None
        months = int(value)
        return str(months) if 1 <= months <= 60 else None
    return None


def save_answer(order: DocumentOrder, value: str) -> bool:
    """Save one draft answer and return whether the review is now ready."""

    question = current_question(order)
    answers = _answers(order)
    answers[question["key"]] = value
    order.draft_answers_json = _canonical_json(answers)

    current_index = next(
        index
        for index, item in enumerate(_QUESTION_DEFINITIONS)
        if item["key"] == question["key"]
    )
    if current_index + 1 >= len(_QUESTION_DEFINITIONS):
        order.current_step = "review"
        return True
    order.current_step = _QUESTION_DEFINITIONS[current_index + 1]["key"]
    return False


def reset_for_edit(order: DocumentOrder) -> None:
    order.current_step = _QUESTION_DEFINITIONS[0]["key"]
    order.draft_answers_json = "{}"


def summary_values(order: DocumentOrder) -> dict[str, str]:
    answers = _answers(order)
    return {
        "reference": order.public_ref,
        "party_a": str(answers.get("party_a_label") or "-")[:60],
        "party_b": str(answers.get("party_b_label") or "-")[:60],
        "city": str(answers.get("premises_city") or "-")[:60],
        "months": str(answers.get("term_months") or "-"),
    }


def confirm_answers(db, order: DocumentOrder) -> DocumentAnswerRevision:
    answers_json = _canonical_json(_answers(order))
    last_revision = (
        db.query(func.max(DocumentAnswerRevision.revision_number))
        .filter(DocumentAnswerRevision.document_order_id == order.id)
        .scalar()
        or 0
    )
    revision = DocumentAnswerRevision(
        document_order_id=order.id,
        revision_number=last_revision + 1,
        schema_version=UAT_TEMPLATE_VERSION,
        answers_json=answers_json,
        content_hash=hashlib.sha256(answers_json.encode("utf-8")).hexdigest(),
    )
    db.add(revision)
    previous_state = order.state
    order.state = "ANSWERS_CONFIRMED"
    order.consent_version = DOCUMENT_STUDIO_CONSENT_VERSION
    order.consented_at = utc_now()
    _audit(
        db,
        order,
        "UAT_ANSWERS_CONFIRMED",
        from_state=previous_state,
        to_state=order.state,
    )
    return revision


def cancel_order(db, order: DocumentOrder) -> None:
    previous_state = order.state
    order.state = "CANCELLED"
    _audit(
        db,
        order,
        "UAT_ORDER_CANCELLED",
        from_state=previous_state,
        to_state=order.state,
    )


def recent_orders_message(db, user_id: int) -> str:
    orders = (
        db.query(DocumentOrder)
        .filter(DocumentOrder.user_id == user_id)
        .order_by(DocumentOrder.id.desc())
        .limit(5)
        .all()
    )
    if not orders:
        return "No Document Studio UAT tests found."
    lines = ["Your recent Document Studio UAT tests:"]
    for order in orders:
        lines.append(f"- {order.public_ref}: {order.state}")
    lines.append("These are test records only; no legal document was created.")
    return "\n".join(lines)
