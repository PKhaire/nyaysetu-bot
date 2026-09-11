"""Versioned product package for one advocate-issued cheque notice.

This module owns legal-package data only. It does not publish the product,
create a payment entitlement, decide legal eligibility, or issue a notice.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType


PRODUCT_CODE = "in_ni138_single_cheque_individual_advocate_issued"
TEMPLATE_VERSION = "in-ni138-single-cheque-en-2026-09-candidate-1"
SCHEMA_VERSION = "in-ni138-single-cheque-en-2026-09-v1"
RENDERER_VERSION = "nyaysetu-cheque-notice-renderer-1"
OUTPUT_CLASSIFICATION = "ADVOCATE_ISSUED_NOTICE"

SUPPORTED_LIABILITY_CATEGORIES = ("PERSONAL_LOAN",)
SUPPORTED_RETURN_REASONS = ("FUNDS INSUFFICIENT",)
MANDATORY_EVIDENCE_KINDS = (
    "CHEQUE_FRONT",
    "RETURN_MEMO",
    "LIABILITY_SUPPORT",
)


@dataclass(frozen=True)
class QuestionDefinition:
    """One customer response, which may confirm a bounded field group."""

    code: str
    section: str
    prompt: str
    kind: str
    field_codes: tuple[str, ...]
    options: tuple[str, ...] = ()
    conditional_on: tuple[str, str] | None = None


@dataclass(frozen=True)
class IntakeValidation:
    """Fail-closed intake result without a software legal conclusion."""

    status: str
    reason_codes: tuple[str, ...]
    normalized_answers: Mapping[str, str]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GoldenScenario:
    """One synthetic advocate-review scenario bound to expected behavior."""

    code: str
    answers: Mapping[str, object]
    evidence_scan_statuses: Mapping[str, str]
    as_of: date
    expected_status: str
    expected_reason_codes: tuple[str, ...]


# The tuple order and exact prompts are immutable inputs to the schema hash.
# The supported path is exactly 18 customer responses. The alternate-address
# response is conditional and therefore is not part of that shortest path.
QUESTION_DEFINITIONS = (
    QuestionDefinition("claimant_scope", "suitability", "Confirm: you are the individual named payee acting for yourself, and the drawer is one living adult individual acting personally.", "confirmation", ("claimant_scope",), ("YES", "NO", "UNSURE")),
    QuestionDefinition("instrument_scope", "suitability", "Confirm: this request concerns one cheque, one return event and no earlier statutory notice for that dishonour.", "confirmation", ("instrument_scope",), ("YES", "NO", "UNSURE")),
    QuestionDefinition("liability_scope", "suitability", "Confirm: the cheque was issued for a real legally payable debt or liability, not a gift or an uncertain security arrangement.", "confirmation", ("liability_scope",), ("YES", "NO", "UNSURE")),
    QuestionDefinition("conflict_scope", "suitability", "Confirm: there has been no part-payment, settlement, replacement cheque, insolvency or existing proceeding for this demand.", "confirmation", ("conflict_scope",), ("YES", "NO", "UNSURE")),
    QuestionDefinition("payee_identity", "people_and_addresses", "Enter the payee's full name exactly as it should be reviewed.", "name", ("payee_full_name",)),
    QuestionDefinition("payee_address", "people_and_addresses", "Enter and confirm the payee's complete notice address with PIN.", "address", ("payee_notice_address",)),
    QuestionDefinition("drawer_identity", "people_and_addresses", "Enter the drawer's full name exactly as shown in the records.", "name", ("drawer_full_name",)),
    QuestionDefinition("drawer_address", "people_and_addresses", "Enter and confirm the drawer's primary service address with PIN and whether another address is known.", "address", ("drawer_service_address", "drawer_alternate_address_present")),
    QuestionDefinition("drawer_alternate_address", "people_and_addresses", "Enter the second known service address for advocate review.", "address", ("drawer_alternate_address",), conditional_on=("drawer_alternate_address_present", "YES")),
    QuestionDefinition("liability_details", "debt_and_cheque", "Provide the liability category, due date and a short factual summary.", "field_group", ("liability_category", "liability_due_date", "liability_summary")),
    QuestionDefinition("cheque_details", "debt_and_cheque", "Provide the cheque number, date, amount, payee text, bank and branch.", "field_group", ("cheque_number", "cheque_date", "cheque_amount_inr", "payee_name_on_cheque", "drawer_bank_name", "drawer_bank_branch")),
    QuestionDefinition("dishonour_details", "presentation_and_dishonour", "Provide presentation date, memo date, date you received bank information, exact return reason and communicating bank.", "field_group", ("presented_on", "return_memo_date", "dishonour_information_received_on", "return_reason_exact", "return_bank_name")),
    QuestionDefinition("evidence_checklist", "evidence_and_changes", "Confirm you can provide the cheque front, return memo and debt support. Uploads are scanned and reviewed separately.", "confirmation", ("evidence_checklist",), ("YES", "NO", "UNSURE")),
    QuestionDefinition("post_issue_change", "evidence_and_changes", "Has any payment, settlement, set-off, replacement instrument or written adjustment occurred after cheque issue?", "confirmation", ("post_issue_change",), ("NO", "YES", "UNSURE")),
    QuestionDefinition("prior_demand_or_notice", "evidence_and_changes", "Was any earlier demand or statutory notice sent for this cheque?", "confirmation", ("prior_demand_or_notice",), ("NO", "YES", "UNSURE")),
    QuestionDefinition("existing_proceeding", "evidence_and_changes", "Is any complaint, suit, arbitration, insolvency or police proceeding already pending for this demand?", "confirmation", ("existing_proceeding",), ("NO", "YES", "UNSURE")),
    QuestionDefinition("facts_confirmed", "review_and_handover", "Re-enter the cheque amount and confirm the complete factual summary.", "amount_and_confirmation", ("cheque_amount_confirmation_inr", "facts_confirmed"), ("CONFIRM", "EDIT")),
    QuestionDefinition("review_consent", "review_and_handover", "Permit the assigned advocate to review these facts and evidence for this request under the displayed consent notice.", "consent", ("review_consent", "review_consent_version"), ("YES", "NO")),
    QuestionDefinition("contact_permission", "review_and_handover", "Choose how the advocate or operator may contact you about missing facts, scope and quote.", "choice", ("contact_permission",), ("WHATSAPP", "PHONE", "BOTH")),
)
_ALLOWED_ANSWER_FIELDS = frozenset(
    field
    for question in QUESTION_DEFINITIONS
    for field in question.field_codes
)


def questionnaire_schema_bytes() -> bytes:
    """Return the canonical bytes bound into the product package identity."""

    return json.dumps(
        {
            "mandatory_evidence_kinds": MANDATORY_EVIDENCE_KINDS,
            "questions": [asdict(question) for question in QUESTION_DEFINITIONS],
            "schema_version": SCHEMA_VERSION,
            "supported_liability_categories": SUPPORTED_LIABILITY_CATEGORIES,
            "supported_return_reasons": SUPPORTED_RETURN_REASONS,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def golden_answers() -> dict[str, object]:
    """Return synthetic package-review facts; never use them for a live order."""

    return {
        "claimant_scope": "YES", "instrument_scope": "YES",
        "liability_scope": "YES", "conflict_scope": "YES",
        "payee_full_name": "Asha Synthetic Payee",
        "payee_notice_address": "1 Test Road, Pune, Maharashtra 411001",
        "drawer_full_name": "Ravi Synthetic Drawer",
        "drawer_service_address": "2 Example Lane, Nashik, Maharashtra 422001",
        "drawer_alternate_address_present": "NO",
        "liability_category": "PERSONAL_LOAN",
        "liability_due_date": "2026-07-15",
        "liability_summary": "Customer states that a personal loan became due and remained unpaid.",
        "cheque_number": "123456", "cheque_date": "2026-08-01",
        "cheque_amount_inr": "250000.00",
        "cheque_amount_confirmation_inr": "250000.00",
        "payee_name_on_cheque": "Asha Synthetic Payee",
        "drawer_bank_name": "Synthetic Bank",
        "drawer_bank_branch": "Pune Test Branch",
        "presented_on": "2026-08-05", "return_memo_date": "2026-08-06",
        "dishonour_information_received_on": "2026-08-06",
        "return_reason_exact": "FUNDS INSUFFICIENT",
        "return_bank_name": "Synthetic Bank", "evidence_checklist": "YES",
        "post_issue_change": "NO", "prior_demand_or_notice": "NO",
        "existing_proceeding": "NO", "facts_confirmed": "CONFIRM",
        "review_consent": "YES",
        "review_consent_version": "cheque-notice-review-2026-09",
        "contact_permission": "WHATSAPP",
    }


def golden_scenarios() -> tuple[GoldenScenario, ...]:
    """Return supported, timing-boundary and decline package fixtures."""

    clean_evidence = MappingProxyType(
        {kind: "CLEAN" for kind in MANDATORY_EVIDENCE_KINDS}
    )
    supported = golden_answers()
    boundary = {
        **supported,
        "cheque_date": "2026-08-15",
        "presented_on": "2026-08-20",
        "return_memo_date": "2026-08-21",
        "dishonour_information_received_on": "2026-09-10",
    }
    decline = {**supported, "claimant_scope": "NO"}
    return (
        GoldenScenario(
            "SUPPORTED",
            MappingProxyType(supported),
            clean_evidence,
            date(2026, 9, 11),
            "READY_FOR_ADVOCATE_TRIAGE",
            (),
        ),
        GoldenScenario(
            "TIMING_BOUNDARY",
            MappingProxyType(boundary),
            clean_evidence,
            date(2026, 9, 11),
            "READY_FOR_ADVOCATE_TRIAGE",
            (),
        ),
        GoldenScenario(
            "DECLINE",
            MappingProxyType(decline),
            clean_evidence,
            date(2026, 9, 11),
            "ROUTED_OUT",
            ("CLAIMANT_SCOPE_UNSUPPORTED",),
        ),
    )


_SAFE_TEXT = re.compile(r"^[^<>\x00-\x08\x0b\x0c\x0e-\x1f]+$")
_NAME = re.compile(r"^[^<>\r\n]{2,160}$")
_CHEQUE_NUMBER = re.compile(r"^[A-Za-z0-9/-]{3,20}$")
_PIN = re.compile(r"(?<!\d)[1-9][0-9]{5}(?!\d)")
_ACCUSATION = re.compile(
    r"\b(fraud|fraudulent|cheat|cheating|criminal|thief|scam|punish|punishment)\b",
    re.IGNORECASE,
)
_REVIEW_CONSENT_VERSION = "cheque-notice-review-2026-09"
_WARNINGS = ("ADVOCATE_TIMING_CONFIRMATION_REQUIRED",)


def _text(value: object, *, minimum: int, maximum: int) -> str | None:
    text = str(value or "").strip()
    if not minimum <= len(text) <= maximum or not _SAFE_TEXT.fullmatch(text):
        return None
    return text


def _date(value: object) -> str | None:
    raw = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _amount(value: object) -> str | None:
    raw = str(value or "").strip().replace(",", "")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0 or amount > Decimal("999999999.99"):
        return None
    if amount.as_tuple().exponent < -2:
        return None
    return f"{amount:.2f}"


def _choice(value: object, choices: tuple[str, ...]) -> str | None:
    normalized = str(value or "").strip().upper().replace(" ", "_")
    return normalized if normalized in choices else None


def _invalid(reason_codes: list[str], normalized: dict[str, str]) -> IntakeValidation:
    return IntakeValidation(
        "INVALID",
        tuple(sorted(set(reason_codes))),
        MappingProxyType(dict(normalized)),
        _WARNINGS,
    )


def validate_intake(
    answers: Mapping[str, object],
    *,
    evidence_scan_statuses: Mapping[str, str] | None = None,
    as_of: date | None = None,
) -> IntakeValidation:
    """Validate facts and route risks without deciding section 138 eligibility."""

    if not isinstance(answers, Mapping):
        return _invalid(["INTAKE_OBJECT_REQUIRED"], {})
    if any(
        not isinstance(key, str) or key not in _ALLOWED_ANSWER_FIELDS
        for key in answers
    ):
        return _invalid(["UNEXPECTED_INTAKE_FIELD"], {})
    normalized: dict[str, str] = {}
    invalid: list[str] = []

    choices = {
        "claimant_scope": ("YES", "NO", "UNSURE"),
        "instrument_scope": ("YES", "NO", "UNSURE"),
        "liability_scope": ("YES", "NO", "UNSURE"),
        "conflict_scope": ("YES", "NO", "UNSURE"),
        "drawer_alternate_address_present": ("YES", "NO"),
        "evidence_checklist": ("YES", "NO", "UNSURE"),
        "post_issue_change": ("YES", "NO", "UNSURE"),
        "prior_demand_or_notice": ("YES", "NO", "UNSURE"),
        "existing_proceeding": ("YES", "NO", "UNSURE"),
        "facts_confirmed": ("CONFIRM", "EDIT"),
        "review_consent": ("YES", "NO"),
        "contact_permission": ("WHATSAPP", "PHONE", "BOTH"),
    }
    for field, allowed in choices.items():
        value = _choice(answers.get(field), allowed)
        if value is None:
            invalid.append(f"INVALID_{field.upper()}")
        else:
            normalized[field] = value

    for field in ("payee_full_name", "drawer_full_name", "payee_name_on_cheque"):
        value = str(answers.get(field) or "").strip()
        if not _NAME.fullmatch(value):
            invalid.append(f"INVALID_{field.upper()}")
        else:
            normalized[field] = value

    for field in ("payee_notice_address", "drawer_service_address"):
        value = _text(answers.get(field), minimum=10, maximum=500)
        if value is None or _PIN.search(value) is None:
            invalid.append(f"INVALID_{field.upper()}")
        else:
            normalized[field] = value
    if normalized.get("drawer_alternate_address_present") == "YES":
        value = _text(
            answers.get("drawer_alternate_address"),
            minimum=10,
            maximum=500,
        )
        if value is None or _PIN.search(value) is None:
            invalid.append("INVALID_DRAWER_ALTERNATE_ADDRESS")
        else:
            normalized["drawer_alternate_address"] = value

    category = _choice(
        answers.get("liability_category"),
        ("PERSONAL_LOAN", "GOODS", "SERVICES", "RENT_FEE", "REFUND", "OTHER"),
    )
    if category is None:
        invalid.append("INVALID_LIABILITY_CATEGORY")
    else:
        normalized["liability_category"] = category
    summary = _text(answers.get("liability_summary"), minimum=20, maximum=800)
    if summary is None:
        invalid.append("INVALID_LIABILITY_SUMMARY")
    else:
        normalized["liability_summary"] = summary

    for field in (
        "liability_due_date",
        "cheque_date",
        "presented_on",
        "return_memo_date",
        "dishonour_information_received_on",
    ):
        value = _date(answers.get(field))
        if value is None:
            invalid.append(f"INVALID_{field.upper()}")
        else:
            normalized[field] = value

    cheque_number = str(answers.get("cheque_number") or "").strip()
    if not _CHEQUE_NUMBER.fullmatch(cheque_number):
        invalid.append("INVALID_CHEQUE_NUMBER")
    else:
        normalized["cheque_number"] = cheque_number
    for field in ("cheque_amount_inr", "cheque_amount_confirmation_inr"):
        value = _amount(answers.get(field))
        if value is None:
            invalid.append(f"INVALID_{field.upper()}")
        else:
            normalized[field] = value
    for field in (
        "drawer_bank_name",
        "drawer_bank_branch",
        "return_bank_name",
        "return_reason_exact",
    ):
        value = _text(answers.get(field), minimum=2, maximum=160)
        if value is None:
            invalid.append(f"INVALID_{field.upper()}")
        else:
            normalized[field] = value

    consent_version = str(answers.get("review_consent_version") or "").strip()
    if consent_version != _REVIEW_CONSENT_VERSION:
        invalid.append("INVALID_REVIEW_CONSENT_VERSION")
    else:
        normalized["review_consent_version"] = consent_version
    if invalid:
        return _invalid(invalid, normalized)
    if normalized["cheque_amount_inr"] != normalized["cheque_amount_confirmation_inr"]:
        return _invalid(["CHEQUE_AMOUNT_CONFIRMATION_MISMATCH"], normalized)

    route_reasons: list[str] = []
    for field, reason in (
        ("claimant_scope", "CLAIMANT_SCOPE_UNSUPPORTED"),
        ("instrument_scope", "INSTRUMENT_SCOPE_UNSUPPORTED"),
        ("liability_scope", "LIABILITY_SCOPE_UNSUPPORTED"),
        ("conflict_scope", "CONFLICT_SCOPE_UNSUPPORTED"),
    ):
        if normalized[field] != "YES":
            route_reasons.append(reason)
    if normalized["liability_category"] not in SUPPORTED_LIABILITY_CATEGORIES:
        route_reasons.append("LIABILITY_CATEGORY_UNSUPPORTED")
    if normalized["return_reason_exact"].upper() not in SUPPORTED_RETURN_REASONS:
        route_reasons.append("RETURN_REASON_REQUIRES_REVIEW")
    for field, reason in (
        ("post_issue_change", "POST_ISSUE_CHANGE_REQUIRES_REVIEW"),
        ("prior_demand_or_notice", "PRIOR_NOTICE_REQUIRES_REVIEW"),
        ("existing_proceeding", "EXISTING_PROCEEDING_REQUIRES_REVIEW"),
    ):
        if normalized[field] != "NO":
            route_reasons.append(reason)
    if _ACCUSATION.search(normalized["liability_summary"]):
        route_reasons.append("ACCUSATION_REQUIRES_ADVOCATE_REVIEW")
    if normalized["facts_confirmed"] != "CONFIRM":
        route_reasons.append("FACTS_NOT_CONFIRMED")
    if normalized["review_consent"] != "YES":
        route_reasons.append("ADVOCATE_REVIEW_CONSENT_MISSING")

    dates = {
        field: datetime.strptime(normalized[field], "%Y-%m-%d").date()
        for field in (
            "cheque_date",
            "presented_on",
            "return_memo_date",
            "dishonour_information_received_on",
        )
    }
    if not (
        dates["cheque_date"]
        <= dates["presented_on"]
        <= dates["return_memo_date"]
        <= dates["dishonour_information_received_on"]
    ):
        route_reasons.append("DATE_SEQUENCE_REQUIRES_REVIEW")
    if max(dates.values()) > (as_of or date.today()):
        route_reasons.append("FUTURE_EVENT_DATE_REQUIRES_REVIEW")
    if route_reasons:
        return IntakeValidation(
            "ROUTED_OUT",
            tuple(sorted(set(route_reasons))),
            MappingProxyType(dict(normalized)),
            _WARNINGS,
        )

    evidence_reasons: list[str] = []
    statuses = {
        str(key).strip().upper(): str(value).strip().upper()
        for key, value in (evidence_scan_statuses or {}).items()
    }
    if normalized["evidence_checklist"] != "YES":
        evidence_reasons.append("MANDATORY_EVIDENCE_NOT_CONFIRMED")
    for kind in MANDATORY_EVIDENCE_KINDS:
        status = statuses.get(kind)
        if status is None:
            evidence_reasons.append(f"EVIDENCE_MISSING_{kind}")
        elif status != "CLEAN":
            evidence_reasons.append(f"EVIDENCE_NOT_CLEAN_{kind}")
    if evidence_reasons:
        return IntakeValidation(
            "EVIDENCE_PENDING",
            tuple(sorted(set(evidence_reasons))),
            MappingProxyType(dict(normalized)),
            _WARNINGS,
        )
    return IntakeValidation(
        "READY_FOR_ADVOCATE_TRIAGE",
        (),
        MappingProxyType(dict(normalized)),
        _WARNINGS,
    )


def golden_artifact_hashes(product) -> dict[str, str]:
    """Render the two classification-specific golden review artifacts."""

    from services.cheque_notice_renderer import render_golden_artifacts

    return render_golden_artifacts(product, golden_answers())
