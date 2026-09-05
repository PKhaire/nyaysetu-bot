"""Release-gated Maharashtra residential Document Studio workflow.

All users see the same product when Document Studio is globally enabled.
Eligibility and answer collection can be tested before publication, while
payment/final release is governed separately by authenticated template,
renderer and storage evidence.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import func

from config import (
    DOCUMENT_STUDIO_CONSENT_VERSION,
    DOCUMENT_STUDIO_DRAFT_TTL_DAYS,
)
from models import (
    DocumentAnswerRevision,
    DocumentAuditEvent,
    DocumentOrder,
    utc_now,
)
from services.document_catalogue import (
    OUTPUT_CLASSIFICATION,
    PRODUCT_CODE,
    SCHEMA_VERSION,
    TEMPLATE_VERSION,
)
from services.document_capacity_service import (
    consume_capacity,
    release_capacity,
    reserve_capacity,
)


# Backwards-compatible names retained for one release because deployment
# checks and older imports may still reference them.
UAT_PRODUCT_CODE = PRODUCT_CODE
UAT_TEMPLATE_VERSION = TEMPLATE_VERSION
UAT_OUTPUT_CLASSIFICATION = OUTPUT_CLASSIFICATION

DOCUMENT_STUDIO_IDS = {
    "create": "doc_create",
    "continue": "doc_continue",
    "mine": "doc_mine",
    "help": "doc_help",
    "back": "doc_back_home",
    "confirm": "doc_confirm",
    "edit": "doc_edit",
    "cancel": "doc_cancel",
}
PRODUCT_ID_PREFIX = "doc_product::"
START_ID_PREFIX = "doc_start::"
ANSWER_ID_PREFIX = "doc_answer::"

DOCUMENT_STUDIO_QUESTION = "DOCUMENT_STUDIO_QUESTION"
DOCUMENT_STUDIO_REVIEW = "DOCUMENT_STUDIO_REVIEW"

_ACTIVE_STATES = ("STARTED", "ELIGIBILITY", "DRAFTING")
_SAFE_TEXT = re.compile(r"^[^<>\x00-\x08\x0b\x0c\x0e-\x1f]{1,500}$")
_NAME = re.compile(r"^[^<>\r\n]{2,120}$")
_PIN = re.compile(r"^[1-9][0-9]{5}$")


def _q(
    key: str,
    prompt: str,
    kind: str = "text",
    *,
    options: tuple[tuple[str, str], ...] = (),
    expected: str | None = None,
    required: bool = True,
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, object]:
    return {
        "key": key,
        "prompt": prompt,
        "kind": kind,
        "options": options,
        "expected": expected,
        "required": required,
        "minimum": minimum,
        "maximum": maximum,
    }


YES_NO = (("YES", "Yes"), ("NO", "No"))

# Question order is part of the immutable schema hash.
QUESTION_DEFINITIONS = (
    _q("property_state", "Is the residential property located in Maharashtra?", "choice", options=(("MAHARASHTRA", "Yes, Maharashtra"), ("OTHER", "No")), expected="MAHARASHTRA"),
    _q("premises_use", "Will the premises be used only as a private residence?", "choice", options=(("RESIDENTIAL", "Yes"), ("OTHER", "No")), expected="RESIDENTIAL"),
    _q("completed_premises", "Is this a completed premises ready for occupation?", "choice", options=YES_NO, expected="YES"),
    _q("party_structure", "Is there exactly one individual licensor and one individual licensee?", "choice", options=(("ONE_EACH", "Yes"), ("OTHER", "No")), expected="ONE_EACH"),
    _q("parties_adult_competent", "Are both parties adults who understand and can enter this agreement?", "choice", options=YES_NO, expected="YES"),
    _q("self_represented_parties", "Will both parties act for themselves, not through a company or agent?", "choice", options=YES_NO, expected="YES"),
    _q("licensor_authority_confirmed", "Does the licensor confirm lawful authority to permit this use?", "choice", options=YES_NO, expected="YES"),
    _q("existing_dispute", "Is there any ownership, possession, tenancy, licence or eviction dispute?", "choice", options=YES_NO, expected="NO"),
    _q("conflicting_occupant", "Is anyone in conflicting possession or claiming a right to occupy?", "choice", options=YES_NO, expected="NO"),
    _q("term_months", "Enter the fixed term in months. This V1 product supports exactly 11.", "integer", expected="11", minimum=11, maximum=11),
    _q("standard_terms_accepted", "Do you accept the fixed V1 terms: no lock-in, 30-day notice and 7-day breach cure?", "choice", options=YES_NO, expected="YES"),
    _q("non_refundable_zero", "Confirm that non-refundable consideration is INR 0.", "choice", options=YES_NO, expected="YES"),
    _q("external_steps_understood", "Do you understand stamping, signing and registration happen outside NyaySetu?", "choice", options=YES_NO, expected="YES"),
    _q("facts_uncontested", "Can both parties confirm the facts without NyaySetu verifying identity or title?", "choice", options=YES_NO, expected="YES"),
    _q("licensor_full_name", "Enter the licensor's full legal name.", "name"),
    _q("licensor_age_years", "Enter the licensor's age in completed years.", "integer", minimum=18, maximum=120),
    _q("licensor_notice_address", "Enter the licensor's complete notice address.", "long_text"),
    _q("licensee_full_name", "Enter the licensee's full legal name.", "name"),
    _q("licensee_age_years", "Enter the licensee's age in completed years.", "integer", minimum=18, maximum=120),
    _q("licensee_notice_address", "Enter the licensee's complete notice address.", "long_text"),
    _q("premises_unit", "Enter flat/house/unit number.", "short_text"),
    _q("premises_building", "Enter building/society name, or type NONE.", "short_text", required=False),
    _q("premises_floor", "Enter floor, or type NONE.", "short_text", required=False),
    _q("premises_street_locality", "Enter street and locality.", "short_text"),
    _q("premises_city", "Enter city/town/village.", "short_text"),
    _q("premises_taluka", "Enter taluka.", "short_text"),
    _q("premises_district", "Enter the Maharashtra district.", "district"),
    _q("premises_pin", "Enter the 6-digit PIN code.", "pin"),
    _q("premises_property_reference", "Enter property reference/CTS/survey number, or type NONE.", "short_text", required=False),
    _q("included_areas", "List specifically included parking/areas, or type NONE.", "long_text", required=False),
    _q("commencement_date", "Enter commencement date as DD-MM-YYYY.", "date"),
    _q("monthly_licence_fee_inr", "Enter monthly licence fee in INR (whole rupees).", "integer", minimum=1, maximum=100000000),
    _q("fee_due_day", "Enter the monthly due day from 1 to 28.", "integer", minimum=1, maximum=28),
    _q("fee_payment_mode", "Choose the fee payment mode.", "choice", options=(("BANK_TRANSFER", "Bank transfer"), ("UPI", "UPI"), ("ACCOUNT_PAYEE_CHEQUE", "A/C payee cheque"))),
    _q("refundable_deposit_inr", "Enter refundable security deposit in INR; zero is allowed.", "integer", minimum=0, maximum=1000000000),
    _q("occupant_count", "Enter total occupants including the licensee (1-6).", "integer", minimum=1, maximum=6),
    _q("permitted_occupant_names", "Enter other permitted occupant names separated by commas, or type NONE.", "long_text", required=False),
    _q("furnishing", "Choose furnishing status.", "choice", options=(("UNFURNISHED", "Unfurnished"), ("SEMI_FURNISHED", "Semi-furnished"), ("FURNISHED", "Furnished"))),
    _q("inventory_items", "List inventory items separated by commas (maximum 25), or type NONE.", "inventory", required=False),
    _q("no_lock_in_ack", "Confirm there is no lock-in period.", "choice", options=YES_NO, expected="YES"),
    _q("possession_process_ack", "Confirm possession and remedies will use lawful process only.", "choice", options=YES_NO, expected="YES"),
    _q("no_transfer_ack", "Confirm no assignment, sub-licence, paying guest, co-living or commercial use.", "choice", options=YES_NO, expected="YES"),
    _q("lawful_use_ack", "Confirm lawful residential use and compliance with lawful society rules.", "choice", options=YES_NO, expected="YES"),
)


def document_studio_available(user=None) -> bool:
    """Return global product visibility; never sample an individual user."""

    from services.document_catalogue import customer_visible

    return customer_visible()


def home_rows(user, translate) -> list[dict[str, str]]:
    return [
        {"id": "home_ai", "title": translate(user, "ask_ai"), "description": translate(user, "home_ai_desc")},
        {"id": "home_book", "title": translate(user, "book_consult"), "description": translate(user, "home_book_desc")},
        {"id": "home_documents", "title": translate(user, "document_studio"), "description": translate(user, "document_studio_desc")},
        {"id": "home_more", "title": translate(user, "more_options"), "description": translate(user, "home_more_desc")},
    ]


def landing_rows(user, translate) -> list[dict[str, str]]:
    return [
        {"id": DOCUMENT_STUDIO_IDS["create"], "title": "Create a document", "description": "Check eligibility and prepare a draft"},
        {"id": DOCUMENT_STUDIO_IDS["continue"], "title": "Continue draft", "description": "Resume your latest saved answers"},
        {"id": DOCUMENT_STUDIO_IDS["mine"], "title": "My documents", "description": "View recent document references"},
        {"id": DOCUMENT_STUDIO_IDS["help"], "title": "How it works", "description": "Scope, exclusions and next steps"},
    ]


def product_rows(user, translate) -> list[dict[str, str]]:
    if not document_studio_available(user):
        return []
    return [{"id": f"{PRODUCT_ID_PREFIX}{PRODUCT_CODE}", "title": "Residential agreement", "description": "Maharashtra, 11-month self-service draft"}]


def parse_product_id(value: str | None, *, start: bool = False) -> str | None:
    prefix = START_ID_PREFIX if start else PRODUCT_ID_PREFIX
    raw = str(value or "")
    if not raw.startswith(prefix):
        return None
    code = raw[len(prefix):]
    return code if code == PRODUCT_CODE and document_studio_available() else None


def parse_answer_id(value: str | None) -> tuple[str, str] | None:
    raw = str(value or "")
    if not raw.startswith(ANSWER_ID_PREFIX):
        return None
    parts = raw.split("::", 2)
    return (parts[1], parts[2]) if len(parts) == 3 and parts[1] and parts[2] else None


def _answers(order: DocumentOrder) -> dict[str, object]:
    try:
        value = json.loads(order.draft_answers_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _audit(db, order: DocumentOrder, event_type: str, *, from_state=None, to_state=None, details=None) -> None:
    db.add(DocumentAuditEvent(document_order_id=order.id, actor_type="CLIENT", event_type=event_type, from_state=from_state, to_state=to_state, details_json=_canonical_json(details or {})))


def latest_draft(db, user_id: int) -> DocumentOrder | None:
    updated_after = utc_now() - timedelta(days=DOCUMENT_STUDIO_DRAFT_TTL_DAYS)
    return db.query(DocumentOrder).filter(DocumentOrder.user_id == user_id, DocumentOrder.product_code == PRODUCT_CODE, DocumentOrder.state.in_(_ACTIVE_STATES), DocumentOrder.updated_at >= updated_after).order_by(DocumentOrder.id.desc()).first()


def latest_order(db, user_id: int) -> DocumentOrder | None:
    """Return the newest order for customer-owned status/download actions."""

    return (
        db.query(DocumentOrder)
        .filter(DocumentOrder.user_id == user_id)
        .order_by(DocumentOrder.id.desc())
        .first()
    )


def create_or_resume_order(db, user_id: int) -> DocumentOrder:
    from services.document_catalogue import resolve_product

    existing = latest_draft(db, user_id)
    if existing:
        reserve_capacity(db, existing)
        return existing
    product = resolve_product()
    order = DocumentOrder(
        public_ref=f"DS-{secrets.token_hex(6).upper()}", user_id=user_id,
        product_code=product.code, template_version=product.template_version,
        state="ELIGIBILITY", current_step=str(QUESTION_DEFINITIONS[0]["key"]),
        draft_answers_json="{}", output_classification=product.output_classification,
        uat_only=False, schema_hash=product.schema_hash,
        template_hash=product.template_hash, price_minor=product.price_minor,
        currency=product.currency, release_status="CANDIDATE",
    )
    db.add(order)
    db.flush()
    reserve_capacity(db, order)
    _audit(db, order, "DOCUMENT_ORDER_CREATED", to_state="ELIGIBILITY")
    return order


# Compatibility name for pre-RC9 callers. New code must use the product name.
create_or_resume_uat_order = create_or_resume_order


def current_question(order: DocumentOrder) -> dict[str, object]:
    for question in QUESTION_DEFINITIONS:
        if question["key"] == order.current_step:
            return question
    order.current_step = str(QUESTION_DEFINITIONS[0]["key"])
    return QUESTION_DEFINITIONS[0]


def _normalize_date(value: str) -> str | None:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError:
            continue
        if parsed < date.today() or parsed > date.today() + timedelta(days=730):
            return None
        return parsed.isoformat()
    return None


def validate_answer(question_key: str, raw_value: str) -> str | None:
    question = next((item for item in QUESTION_DEFINITIONS if item["key"] == question_key), None)
    if not question:
        return None
    value = str(raw_value or "").strip()
    if not value:
        return None
    if not question["required"] and value.upper() in {"NONE", "NA", "N/A"}:
        return "NONE"
    kind = question["kind"]
    if kind == "choice":
        allowed = {code for code, _ in question["options"]}
        normalized = value.upper().replace(" ", "_")
        labels = {label.upper(): code for code, label in question["options"]}
        normalized = labels.get(value.upper(), normalized)
        return normalized if normalized in allowed else None
    if kind == "integer":
        if not value.isdigit():
            return None
        number = int(value)
        if question["minimum"] is not None and number < question["minimum"]:
            return None
        if question["maximum"] is not None and number > question["maximum"]:
            return None
        return str(number)
    if kind == "date":
        return _normalize_date(value)
    if kind == "pin":
        return value if _PIN.fullmatch(value) else None
    if kind == "name":
        return value if _NAME.fullmatch(value) else None
    if kind == "inventory":
        if not _SAFE_TEXT.fullmatch(value):
            return None
        items = [item.strip() for item in value.split(",") if item.strip()]
        return ", ".join(items) if 1 <= len(items) <= 25 else None
    if kind == "district":
        return value.title() if _NAME.fullmatch(value) else None
    if kind in {"short_text", "long_text"}:
        limit = 160 if kind == "short_text" else 500
        return value if len(value) <= limit and _SAFE_TEXT.fullmatch(value) else None
    return None


def save_answer(order: DocumentOrder, value: str, *, db=None) -> bool:
    question = current_question(order)
    answers = _answers(order)
    answers[str(question["key"])] = value
    order.draft_answers_json = _canonical_json(answers)
    if question.get("expected") is not None and value != question["expected"]:
        order.state = "ROUTED_OUT"
        order.current_step = "route_out"
        order.exception_code = f"INELIGIBLE_{str(question['key']).upper()}"
        if db is not None:
            release_capacity(
                db,
                order,
                reason="INELIGIBLE_ROUTE_OUT",
            )
        return True
    index = next(i for i, item in enumerate(QUESTION_DEFINITIONS) if item["key"] == question["key"])
    if index + 1 >= len(QUESTION_DEFINITIONS):
        order.current_step = "review"
        return True
    next_question = QUESTION_DEFINITIONS[index + 1]
    if order.state == "ELIGIBILITY" and next_question.get("expected") is None:
        order.state = "DRAFTING"
    order.current_step = str(next_question["key"])
    return False


def order_routed_out(order: DocumentOrder) -> bool:
    return order.state == "ROUTED_OUT"


def reset_for_edit(order: DocumentOrder) -> None:
    order.state = "ELIGIBILITY"
    order.current_step = str(QUESTION_DEFINITIONS[0]["key"])
    order.draft_answers_json = "{}"
    order.exception_code = None


def _add_months_less_day(iso_date: str, months: int) -> str:
    start = datetime.strptime(iso_date, "%Y-%m-%d").date()
    target = start.month - 1 + months
    year, month = start.year + target // 12, target % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return (date(year, month, day) - timedelta(days=1)).isoformat()


def confirmed_snapshot(order: DocumentOrder) -> dict[str, object]:
    answers = _answers(order)
    if answers.get("commencement_date"):
        answers["expiry_date"] = _add_months_less_day(str(answers["commencement_date"]), 11)
    answers.update({
        "non_refundable_consideration_inr": "0", "maintenance_payer": "LICENSOR",
        "utilities_payer": "LICENSEE", "deposit_refund_business_days": "7",
        "ordinary_notice_days": "30", "inspection_notice_hours": "24",
    })
    return answers


def summary_values(order: DocumentOrder) -> dict[str, str]:
    answers = confirmed_snapshot(order)
    address_parts = [answers.get(key) for key in ("premises_unit", "premises_building", "premises_city", "premises_district", "premises_pin")]
    return {
        "reference": order.public_ref,
        "party_a": str(answers.get("licensor_full_name") or "-")[:120],
        "party_b": str(answers.get("licensee_full_name") or "-")[:120],
        "city": ", ".join(str(item) for item in address_parts if item and item != "NONE")[:300] or "-",
        "months": "11", "commencement": str(answers.get("commencement_date") or "-"),
        "expiry": str(answers.get("expiry_date") or "-"),
        "fee": str(answers.get("monthly_licence_fee_inr") or "-"),
        "deposit": str(answers.get("refundable_deposit_inr") or "-"),
    }


def review_message(order: DocumentOrder) -> str:
    values = summary_values(order)
    return (
        "Please confirm these customer-provided facts:\n"
        f"Reference: {values['reference']}\nLicensor: {values['party_a']}\n"
        f"Licensee: {values['party_b']}\nPremises: {values['city']}\n"
        f"Term: {values['commencement']} to {values['expiry']} (11 months)\n"
        f"Monthly fee: INR {values['fee']}\nRefundable deposit: INR {values['deposit']}\n\n"
        "NyaySetu has not verified identity, title, authority or facts. Stamping, signing and registration are external."
    )


def confirm_answers(db, order: DocumentOrder) -> DocumentAnswerRevision:
    if order.current_step != "review" or order.state != "DRAFTING":
        raise ValueError("document_order_not_ready_for_confirmation")
    consume_capacity(db, order)
    answers_json = _canonical_json(confirmed_snapshot(order))
    last_revision = db.query(func.max(DocumentAnswerRevision.revision_number)).filter(DocumentAnswerRevision.document_order_id == order.id).scalar() or 0
    revision_number = last_revision + 1
    revision = DocumentAnswerRevision(
        document_order_id=order.id, revision_number=revision_number,
        schema_version=SCHEMA_VERSION, answers_json=answers_json,
        content_hash=hashlib.sha256(answers_json.encode("utf-8")).hexdigest(),
    )
    db.add(revision)
    previous = order.state
    order.state = "CONFIRMED"
    order.active_revision_number = revision_number
    order.consent_version = DOCUMENT_STUDIO_CONSENT_VERSION
    order.consented_at = utc_now()
    _audit(db, order, "DOCUMENT_ANSWERS_CONFIRMED", from_state=previous, to_state=order.state, details={"revision_number": revision_number, "content_hash": revision.content_hash})
    # SessionLocal deliberately disables autoflush. Persist the immutable
    # revision inside this transaction before the preview workflow queries it.
    db.flush()
    return revision


def cancel_order(db, order: DocumentOrder) -> None:
    previous = order.state
    release_capacity(db, order, reason="CUSTOMER_CANCELLED")
    order.state = "ABANDONED"
    _audit(db, order, "DOCUMENT_ORDER_ABANDONED", from_state=previous, to_state=order.state)


def recent_orders_message(db, user_id: int) -> str:
    orders = db.query(DocumentOrder).filter(DocumentOrder.user_id == user_id).order_by(DocumentOrder.id.desc()).limit(5).all()
    if not orders:
        return "No Document Studio drafts found."
    lines = ["Your recent Document Studio items:"]
    lines.extend(f"- {order.public_ref}: {order.state}" for order in orders)
    lines.append("Final files are released only after all legal, payment and storage checks pass.")
    return "\n".join(lines)
