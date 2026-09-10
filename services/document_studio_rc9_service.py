"""Release-gated Maharashtra residential Draft Studio workflow.

All users see the same product when Draft Studio is globally enabled.
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
    customer_visible,
    registered_product_codes,
    resolve_product,
    visible_products,
)
from services.document_capacity_service import (
    consume_capacity,
    release_capacity,
    reserve_capacity,
)
from services.document_address_service import render_premises_address
from services.postal_reference_service import lookup_maharashtra_pin


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
    "save": "doc_save_exit",
}
PRODUCT_ID_PREFIX = "doc_product::"
START_ID_PREFIX = "doc_start::"
PRODUCT_PAGE_ID_PREFIX = "doc_products_page::"
ANSWER_ID_PREFIX = "doc_answer::"
EDIT_SECTION_ID_PREFIX = "doc_edit_section::"
PRODUCT_PAGE_SIZE = 8

DOCUMENT_STUDIO_QUESTION = "DOCUMENT_STUDIO_QUESTION"
DOCUMENT_STUDIO_REVIEW = "DOCUMENT_STUDIO_REVIEW"
DOCUMENT_STUDIO_EDIT_SECTION = "DOCUMENT_STUDIO_EDIT_SECTION"
DOCUMENT_STUDIO_PRODUCT_SELECT = "DOCUMENT_STUDIO_PRODUCT_SELECT"

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
    when: tuple[str, str] | None = None,
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
        "when": when,
    }


YES_NO = (("YES", "Yes"), ("NO", "No"))

# Question order is part of the immutable schema hash.
QUESTION_DEFINITIONS = (
    _q(
        "property_eligibility",
        "Confirm all three: the property is in Maharashtra, is a completed premises ready for occupation, and will be used only as a private residence.",
        "choice",
        options=YES_NO,
        expected="YES",
    ),
    _q(
        "party_eligibility",
        "Confirm all three: there is one individual licensor and one individual licensee, both are adults able to understand this agreement, and each acts personally rather than through a company, trust, agent or representative.",
        "choice",
        options=YES_NO,
        expected="YES",
    ),
    _q(
        "authority_dispute_eligibility",
        "Confirm all three: the licensor states they have authority to permit this use, there is no ownership/possession/tenancy/licence/eviction dispute, and no conflicting occupant or claimant.",
        "choice",
        options=YES_NO,
        expected="YES",
    ),
    _q(
        "standard_product_terms",
        "Confirm this fixed product is suitable: an 11-month residential licence, no lock-in, 30-day ordinary notice, INR 0 non-refundable premium, lawful possession remedies, no transfer/PG/commercial use, and stamping/signing/registration outside NyaySetu.",
        "choice",
        options=YES_NO,
        expected="YES",
    ),
    _q("licensor_full_name", "Enter the licensor's full legal name.", "name"),
    _q("licensor_age_years", "Enter the licensor's age in completed years.", "integer", minimum=18, maximum=120),
    _q("licensee_full_name", "Enter the licensee's full legal name.", "name"),
    _q("licensee_age_years", "Enter the licensee's age in completed years.", "integer", minimum=18, maximum=120),
    _q("premises_pin", "Enter the 6-digit PIN code.", "pin"),
    _q(
        "premises_address_lines",
        "Enter the complete premises details in one message: flat/unit, building/society, floor if applicable, road/locality, city/town/village, taluka if known, and district. Do not repeat the PIN.",
        "long_text",
    ),
    _q(
        "premises_address_confirmed",
        "Confirm the complete premises address shown above, or choose Edit address.",
        "choice",
        options=(("CONFIRM", "Confirm"), ("EDIT", "Edit address")),
    ),
    _q("licensor_notice_address", "Enter the licensor's complete notice address in one message.", "long_text"),
    _q(
        "licensee_address_same_as_premises",
        "Is the licensee's notice address the same as the licensed premises?",
        "choice",
        options=YES_NO,
    ),
    _q(
        "licensee_notice_address",
        "Enter the licensee's complete notice address in one message.",
        "long_text",
        when=("licensee_address_same_as_premises", "NO"),
    ),
    _q("commencement_date", "Enter commencement date as DD-MM-YYYY.", "date"),
    _q("monthly_licence_fee_inr", "Enter monthly licence fee in INR (whole rupees).", "integer", minimum=1, maximum=100000000),
    _q("fee_due_day", "Enter the monthly due day from 1 to 28.", "integer", minimum=1, maximum=28),
    _q("fee_payment_mode", "Choose the fee payment mode.", "choice", options=(("BANK_TRANSFER", "Bank transfer"), ("UPI", "UPI"), ("ACCOUNT_PAYEE_CHEQUE", "A/C payee cheque"))),
    _q("refundable_deposit_inr", "Enter refundable security deposit in INR; zero is allowed.", "integer", minimum=0, maximum=1000000000),
    _q(
        "optional_details_mode",
        "Would you like to add optional property, occupant or inventory details, or skip all optional details?",
        "choice",
        options=(("ADD", "Add optional details"), ("SKIP", "Skip optional details")),
    ),
    _q("property_reference_present", "Do you want to add a CTS, survey or other property reference?", "choice", options=YES_NO, when=("optional_details_mode", "ADD")),
    _q("premises_property_reference", "Enter the exact CTS, survey or property reference.", "short_text", when=("property_reference_present", "YES")),
    _q("included_areas_present", "Does the licence include specifically identified parking, storage, terrace or another area?", "choice", options=YES_NO, when=("optional_details_mode", "ADD")),
    _q("included_areas", "List each included area with its exact identifier.", "long_text", when=("included_areas_present", "YES")),
    _q("other_occupants_present", "Will anyone other than the licensee live in the premises?", "choice", options=YES_NO, when=("optional_details_mode", "ADD")),
    _q("permitted_occupant_names", "Enter the other permitted occupant names separated by commas (maximum five).", "occupant_names", when=("other_occupants_present", "YES")),
    _q("inventory_present", "Do you want to include an inventory schedule?", "choice", options=YES_NO, when=("optional_details_mode", "ADD")),
    _q("inventory_items", "List inventory items separated by commas (maximum 25).", "inventory", when=("inventory_present", "YES")),
)

SECTION_ORDER = (
    ("eligibility", "Eligibility"),
    ("parties", "Parties"),
    ("premises", "Property & addresses"),
    ("agreement", "Dates & money"),
    ("optional", "Optional details"),
)
_SECTION_KEYS = {
    "eligibility": {
        "property_eligibility",
        "party_eligibility",
        "authority_dispute_eligibility",
        "standard_product_terms",
    },
    "parties": {
        "licensor_full_name",
        "licensor_age_years",
        "licensee_full_name",
        "licensee_age_years",
    },
    "premises": {
        "premises_pin",
        "premises_address_lines",
        "premises_address_confirmed",
        "licensor_notice_address",
        "licensee_address_same_as_premises",
        "licensee_notice_address",
    },
    "agreement": {
        "commencement_date",
        "monthly_licence_fee_inr",
        "fee_due_day",
        "fee_payment_mode",
        "refundable_deposit_inr",
    },
    "optional": {
        "optional_details_mode",
        "property_reference_present",
        "premises_property_reference",
        "included_areas_present",
        "included_areas",
        "other_occupants_present",
        "permitted_occupant_names",
        "inventory_present",
        "inventory_items",
    },
}
_SECTION_BY_KEY = {
    key: section
    for section, keys in _SECTION_KEYS.items()
    for key in keys
}
QUESTION_DEFINITIONS = tuple(
    {**question, "section": _SECTION_BY_KEY[str(question["key"])]}
    for question in QUESTION_DEFINITIONS
)


def document_studio_available(user=None) -> bool:
    """Return global product visibility; never sample an individual user."""

    return any(
        customer_visible(code)
        for code in registered_product_codes()
    )


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


def _translated_product_text(user, translate, key: str, fallback: str) -> str:
    value = str(translate(user, key) or "").strip()
    return fallback if not value or value == key else value


def product_rows(
    user,
    translate,
    *,
    page: int = 0,
) -> list[dict[str, str]]:
    """Return one provider-safe catalogue page with numbered fallback labels."""

    if not document_studio_available(user):
        return []
    products = visible_products()
    page_count = max(
        1,
        (len(products) + PRODUCT_PAGE_SIZE - 1) // PRODUCT_PAGE_SIZE,
    )
    if page < 0 or page >= page_count:
        return []
    start = page * PRODUCT_PAGE_SIZE
    selected = products[start:start + PRODUCT_PAGE_SIZE]
    rows = []
    for number, product in enumerate(selected, start=1):
        title = _translated_product_text(
            user,
            translate,
            product.display_name_key,
            product.display_name,
        )
        description = _translated_product_text(
            user,
            translate,
            product.list_description_key,
            product.list_description,
        )
        try:
            description = description.format(
                price_inr=product.price_minor // 100,
            )
        except (KeyError, ValueError):
            description = product.list_description
        rows.append({
            "id": f"{PRODUCT_ID_PREFIX}{product.code}",
            "title": f"{number}. {title}",
            "description": description,
        })
    if page > 0:
        rows.append({
            "id": f"{PRODUCT_PAGE_ID_PREFIX}{page - 1}",
            "title": _translated_product_text(
                user,
                translate,
                "document_products_previous",
                "Previous drafts",
            ),
            "description": _translated_product_text(
                user,
                translate,
                "document_products_previous_desc",
                "Show the previous catalogue page",
            ),
        })
    if page + 1 < page_count:
        rows.append({
            "id": f"{PRODUCT_PAGE_ID_PREFIX}{page + 1}",
            "title": _translated_product_text(
                user,
                translate,
                "document_products_next",
                "More drafts",
            ),
            "description": _translated_product_text(
                user,
                translate,
                "document_products_next_desc",
                "Show the next catalogue page",
            ),
        })
    return rows


def product_selection_state(page: int) -> str:
    return f"{DOCUMENT_STUDIO_PRODUCT_SELECT}:{page}"


def product_selection_page(flow_state: str | None) -> int | None:
    prefix = f"{DOCUMENT_STUDIO_PRODUCT_SELECT}:"
    raw = str(flow_state or "")
    if not raw.startswith(prefix):
        return None
    value = raw[len(prefix):]
    return int(value) if value.isdigit() else None


def parse_product_page_id(value: str | None) -> int | None:
    raw = str(value or "")
    if not raw.startswith(PRODUCT_PAGE_ID_PREFIX):
        return None
    value = raw[len(PRODUCT_PAGE_ID_PREFIX):]
    if not value.isdigit():
        return None
    page = int(value)
    product_count = len(visible_products())
    page_count = max(
        1,
        (product_count + PRODUCT_PAGE_SIZE - 1) // PRODUCT_PAGE_SIZE,
    )
    return page if page < page_count else None


def parse_product_number(value: str | None, *, page: int) -> str | None:
    """Resolve a numbered text reply only within the displayed page."""

    raw = str(value or "").strip()
    if not raw.isdigit() or page < 0:
        return None
    products = visible_products()
    index = page * PRODUCT_PAGE_SIZE + int(raw) - 1
    page_end = min((page + 1) * PRODUCT_PAGE_SIZE, len(products))
    if index < page * PRODUCT_PAGE_SIZE or index >= page_end:
        return None
    return products[index].code


def product_selection_details(user, translate, code: str) -> tuple[str, str]:
    """Return catalogue-owned overview and CTA copy for one visible product."""

    product = resolve_product(code)
    return (
        _translated_product_text(
            user,
            translate,
            product.selection_overview_key,
            product.selection_overview,
        ),
        _translated_product_text(
            user,
            translate,
            product.start_label_key,
            product.start_label,
        ),
    )


def parse_product_id(value: str | None, *, start: bool = False) -> str | None:
    prefix = START_ID_PREFIX if start else PRODUCT_ID_PREFIX
    raw = str(value or "")
    if not raw.startswith(prefix):
        return None
    code = raw[len(prefix):]
    return code if customer_visible(code) else None


def parse_answer_id(value: str | None) -> tuple[str, str] | None:
    raw = str(value or "")
    if not raw.startswith(ANSWER_ID_PREFIX):
        return None
    parts = raw.split("::", 2)
    return (parts[1], parts[2]) if len(parts) == 3 and parts[1] and parts[2] else None


def parse_edit_section_id(value: str | None) -> str | None:
    raw = str(value or "")
    if not raw.startswith(EDIT_SECTION_ID_PREFIX):
        return None
    section = raw[len(EDIT_SECTION_ID_PREFIX):]
    return section if section in dict(SECTION_ORDER) else None


def edit_section_rows() -> list[dict[str, str]]:
    return [
        {
            "id": f"{EDIT_SECTION_ID_PREFIX}{section}",
            "title": title[:24],
            "description": "Change only this section",
        }
        for section, title in SECTION_ORDER
    ]


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


def latest_draft(
    db,
    user_id: int,
    product_code: str = PRODUCT_CODE,
) -> DocumentOrder | None:
    updated_after = utc_now() - timedelta(days=DOCUMENT_STUDIO_DRAFT_TTL_DAYS)
    return db.query(DocumentOrder).filter(DocumentOrder.user_id == user_id, DocumentOrder.product_code == product_code, DocumentOrder.state.in_(_ACTIVE_STATES), DocumentOrder.updated_at >= updated_after).order_by(DocumentOrder.id.desc()).first()


def latest_order(db, user_id: int) -> DocumentOrder | None:
    """Return the newest order for customer-owned status/download actions."""

    return (
        db.query(DocumentOrder)
        .filter(DocumentOrder.user_id == user_id)
        .order_by(DocumentOrder.id.desc())
        .first()
    )


def create_or_resume_order(
    db,
    user_id: int,
    product_code: str = PRODUCT_CODE,
) -> DocumentOrder:
    product = resolve_product(product_code)
    if not customer_visible(product.code):
        raise ValueError("document_product_not_enabled")
    if (
        product.code != PRODUCT_CODE
        or product.output_classification != OUTPUT_CLASSIFICATION
    ):
        raise ValueError("document_product_workflow_unsupported")
    existing = latest_draft(db, user_id, product.code)
    if existing and existing.schema_hash == product.schema_hash:
        reserve_capacity(db, existing)
        return existing
    if existing:
        previous = existing.state
        release_capacity(db, existing, reason="SCHEMA_SUPERSEDED")
        existing.state = "ABANDONED"
        existing.current_step = "superseded"
        existing.exception_code = "SCHEMA_SUPERSEDED"
        _audit(
            db,
            existing,
            "DOCUMENT_SCHEMA_SUPERSEDED",
            from_state=previous,
            to_state=existing.state,
            details={
                "replacement_schema_hash": product.schema_hash,
            },
        )
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
    answers = _answers(order)
    for index, question in enumerate(QUESTION_DEFINITIONS):
        if question["key"] == order.current_step:
            if _question_applies(question, answers):
                return _present_question(question, answers)
            next_question = _next_question(index, answers)
            if next_question is not None:
                order.current_step = str(next_question["key"])
                return _present_question(next_question, answers)
            order.current_step = "review"
            return question
    order.current_step = str(QUESTION_DEFINITIONS[0]["key"])
    return QUESTION_DEFINITIONS[0]


def _present_question(
    question: dict[str, object],
    answers: dict[str, object],
) -> dict[str, object]:
    """Add customer-facing context without changing the hashed schema."""

    presented = dict(question)
    section = str(question["section"])
    sections = dict(SECTION_ORDER)
    presented.update(
        {
            "section_title": sections[section],
            "section_number": tuple(sections).index(section) + 1,
            "section_total": len(SECTION_ORDER),
        }
    )
    if question["key"] == "premises_address_lines":
        pin = str(answers.get("premises_pin") or "").strip()
        hint = lookup_maharashtra_pin(pin)
        if hint:
            districts = ", ".join(hint["districts"]) or "not listed"
            talukas = ", ".join(hint["talukas"]) or "not listed"
            offices = ", ".join(hint["offices"]) or "not listed"
            assistance = (
                f"For PIN {pin}, postal reference suggests district: "
                f"{districts}; taluka: {talukas}; post offices: {offices}. "
            )
        else:
            assistance = (
                f"We could not suggest locality details for PIN {pin}. "
            )
        presented["prompt"] = (
            assistance
            + "Please type the complete address yourself: flat/unit, "
            "building/society, floor if applicable, road/locality, "
            "city/town/village, taluka if known, and district. Do not "
            "repeat the PIN. You will confirm it next."
        )
    elif question["key"] == "premises_address_confirmed":
        address = render_premises_address(answers)
        presented["prompt"] = (
            "Please check the complete premises address:\n"
            f"{address}\n\nChoose Confirm only if it is correct, or "
            "Edit address to enter it again."
        )
    return presented


def _question_applies(
    question: dict[str, object],
    answers: dict[str, object],
) -> bool:
    condition = question.get("when")
    if not condition:
        return True
    dependency_key, expected_value = condition
    return answers.get(str(dependency_key)) == expected_value


def _next_question(
    current_index: int,
    answers: dict[str, object],
) -> dict[str, object] | None:
    for question in QUESTION_DEFINITIONS[current_index + 1 :]:
        if (
            _question_applies(question, answers)
            and str(question["key"]) not in answers
        ):
            return question
    return None


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
    if kind == "occupant_names":
        if not _SAFE_TEXT.fullmatch(value):
            return None
        names = [item.strip() for item in value.split(",") if item.strip()]
        return ", ".join(names) if 1 <= len(names) <= 5 else None
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
    if question["key"] == "premises_address_confirmed" and value == "EDIT":
        for key in (
            "premises_pin",
            "premises_address_lines",
            "premises_address_confirmed",
        ):
            answers.pop(key, None)
        order.draft_answers_json = _canonical_json(answers)
        order.current_step = "premises_pin"
        return False
    for dependent in QUESTION_DEFINITIONS:
        condition = dependent.get("when")
        if condition and condition[0] == question["key"]:
            if value != condition[1]:
                answers.pop(str(dependent["key"]), None)
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
    next_question = _next_question(index, answers)
    if next_question is None:
        if order.state == "ELIGIBILITY":
            order.state = "DRAFTING"
        order.current_step = "review"
        return True
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


def reset_section_for_edit(db, order: DocumentOrder, section: str) -> bool:
    """Clear one draft section while preserving all unrelated answers."""

    if section not in _SECTION_KEYS:
        return False
    answers = _answers(order)
    for key in _SECTION_KEYS[section]:
        answers.pop(key, None)
    order.draft_answers_json = _canonical_json(answers)
    order.state = "ELIGIBILITY" if section == "eligibility" else "DRAFTING"
    order.current_step = next(
        str(question["key"])
        for question in QUESTION_DEFINITIONS
        if question["section"] == section
    )
    order.exception_code = None
    _audit(
        db,
        order,
        "DOCUMENT_SECTION_EDIT_STARTED",
        details={"section": section},
    )
    return True


def _add_months_less_day(iso_date: str, months: int) -> str:
    start = datetime.strptime(iso_date, "%Y-%m-%d").date()
    target = start.month - 1 + months
    year, month = start.year + target // 12, target % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return (date(year, month, day) - timedelta(days=1)).isoformat()


def confirmed_snapshot(order: DocumentOrder) -> dict[str, object]:
    answers = _answers(order)
    premises_address = render_premises_address(answers)
    answers["rendered_premises_address"] = premises_address
    if answers.get("licensee_address_same_as_premises") == "YES":
        answers["licensee_notice_address"] = premises_address
    if answers.get("property_reference_present") != "YES":
        answers["premises_property_reference"] = "NONE"
    if answers.get("included_areas_present") != "YES":
        answers["included_areas"] = "NONE"
    if answers.get("other_occupants_present") != "YES":
        answers["permitted_occupant_names"] = "NONE"
        answers["occupant_count"] = "1"
    else:
        names = [
            value.strip()
            for value in str(
                answers.get("permitted_occupant_names") or ""
            ).split(",")
            if value.strip()
        ]
        answers["occupant_count"] = str(1 + len(names))
    if answers.get("inventory_present") != "YES":
        answers["inventory_items"] = "NONE"
    if answers.get("commencement_date"):
        answers["expiry_date"] = _add_months_less_day(str(answers["commencement_date"]), 11)
    answers.update({
        "term_months": "11",
        "non_refundable_consideration_inr": "0", "maintenance_payer": "LICENSOR",
        "utilities_payer": "LICENSEE", "deposit_refund_business_days": "7",
        "ordinary_notice_days": "30", "inspection_notice_hours": "24",
    })
    return answers


def summary_values(order: DocumentOrder) -> dict[str, str]:
    answers = confirmed_snapshot(order)
    return {
        "reference": order.public_ref,
        "party_a": str(answers.get("licensor_full_name") or "-")[:120],
        "party_b": str(answers.get("licensee_full_name") or "-")[:120],
        "premises_address": str(
            answers.get("rendered_premises_address") or "-"
        )[:500],
        "licensor_notice_address": str(
            answers.get("licensor_notice_address") or "-"
        )[:500],
        "licensee_notice_address": str(
            answers.get("licensee_notice_address") or "-"
        )[:500],
        "months": "11", "commencement": str(answers.get("commencement_date") or "-"),
        "expiry": str(answers.get("expiry_date") or "-"),
        "fee": str(answers.get("monthly_licence_fee_inr") or "-"),
        "deposit": str(answers.get("refundable_deposit_inr") or "-"),
    }


def review_message(order: DocumentOrder) -> str:
    values = summary_values(order)
    return (
        "Please confirm these customer-provided facts:\n"
        f"Reference: {values['reference']}\n"
        f"Licensor: {values['party_a']}\n"
        f"Licensor notice address: {values['licensor_notice_address']}\n"
        f"Licensee: {values['party_b']}\n"
        f"Licensee notice address: {values['licensee_notice_address']}\n"
        f"Premises: {values['premises_address']}\n"
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
        return "No Draft Studio drafts found."
    lines = ["Your recent Draft Studio items:"]
    lines.extend(f"- {order.public_ref}: {order.state}" for order in orders)
    lines.append("Final files are released only after all legal, payment and storage checks pass.")
    return "\n".join(lines)
