"""Deterministic internal renderers for the cheque-notice legal package."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal

from services.cheque_notice_product import (
    MANDATORY_EVIDENCE_KINDS,
    validate_intake,
)
from services.document_renderer import (
    MAX_ARTIFACT_BYTES,
    RenderedArtifact,
    format_whole_inr_words,
    render_markdown_pdf,
)


_TOKEN = re.compile(r"\[([a-z_]+)\]")
_ADVOCATE_FIELDS = (
    "notice_date",
    "advocate_practice_name",
    "advocate_full_name",
    "advocate_enrolment_ref",
    "advocate_service_address",
)
_GOLDEN_ADVOCATE_CONTEXT = {
    "notice_date": "2026-09-11",
    "advocate_practice_name": "Synthetic Review Practice",
    "advocate_full_name": "Synthetic Review Advocate",
    "advocate_enrolment_ref": "SYNTHETIC-NOT-AN-ENROLMENT",
    "advocate_service_address": "3 Review Street, Mumbai, Maharashtra 400001",
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _amount_words(value: str) -> str:
    amount = Decimal(value)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    words = format_whole_inr_words(rupees)
    if not paise:
        return words
    paise_words = format_whole_inr_words(paise).replace(
        " rupees only",
        " paise only",
    )
    return words.removesuffix(" only") + " and " + paise_words


def _date_value(value: str) -> str | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _validated_answers(answers: dict[str, object]) -> dict[str, str]:
    result = validate_intake(
        answers,
        evidence_scan_statuses={kind: "CLEAN" for kind in MANDATORY_EVIDENCE_KINDS},
    )
    if result.status != "READY_FOR_ADVOCATE_TRIAGE":
        reasons = ",".join(result.reason_codes)
        raise ValueError(f"cheque_notice_intake_not_renderable:{reasons}")
    return dict(result.normalized_answers)


def _artifact(
    product,
    answers: dict[str, str],
    kind: str,
    markdown: str,
    *,
    advocate_context: dict[str, str] | None = None,
) -> RenderedArtifact:
    content = render_markdown_pdf(
        markdown,
        preview=False,
        renderer_version=product.renderer_version,
        title=(
            "NyaySetu Confirmed Cheque Facts"
            if kind == "FACTUAL_SUMMARY_PDF"
            else "Section 138 Notice Package Review"
        ),
        author="NyaySetu Draft Studio",
    )
    if not content or len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("document_artifact_size_invalid")
    content_hash = _sha256(content)
    manifest = {
        "answers_hash": _sha256(
            json.dumps(
                answers,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ),
        "artifact_hash": content_hash,
        "artifact_kind": kind,
        "renderer_version": product.renderer_version,
        "schema_hash": product.schema_hash,
        "template_hash": product.template_hash,
        "template_version": product.template_version,
    }
    if advocate_context is not None:
        manifest["advocate_context_hash"] = _sha256(
            json.dumps(
                advocate_context,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
    manifest_hash = _sha256(
        json.dumps(
            manifest,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    return RenderedArtifact(
        kind=kind,
        content=content,
        content_type="application/pdf",
        extension="pdf",
        content_hash=content_hash,
        manifest_hash=manifest_hash,
        renderer_version=product.renderer_version,
    )


def render_factual_summary(product, answers: dict[str, object]) -> RenderedArtifact:
    """Render customer-confirmed facts without producing statutory notice text."""

    values = _validated_answers(answers)
    markdown = f"""## Confirmed factual summary - not a legal notice

This summary records customer-provided facts for an assigned advocate. It does
not confirm legal eligibility, a deadline, service, liability or any remedy.

## Parties and addresses

Payee: {values['payee_full_name']}  
Payee address: {values['payee_notice_address']}  
Drawer: {values['drawer_full_name']}  
Primary service address: {values['drawer_service_address']}

## Stated liability and cheque

Category: {values['liability_category']}  
Stated due date: {values['liability_due_date']}  
Customer summary: {values['liability_summary']}  
Cheque number: {values['cheque_number']}  
Cheque date: {values['cheque_date']}  
Exact cheque amount: INR {values['cheque_amount_inr']}  
Payee text on cheque: {values['payee_name_on_cheque']}  
Drawer bank and branch: {values['drawer_bank_name']}, {values['drawer_bank_branch']}

## Presentation and return

Presented on: {values['presented_on']}  
Return memo date: {values['return_memo_date']}  
Bank information received on: {values['dishonour_information_received_on']}  
Exact recorded return reason: {values['return_reason_exact']}  
Communicating bank: {values['return_bank_name']}

> Evidence, legal scope, timing and notice wording require assigned-advocate review. No payment entitlement or issued notice is created by this summary.
"""
    return _artifact(product, values, "FACTUAL_SUMMARY_PDF", markdown)


def render_notice_for_advocate(
    product,
    answers: dict[str, object],
    advocate_context: dict[str, object],
) -> RenderedArtifact:
    """Render the exact package text for internal advocate approval/signing."""

    values = _validated_answers(answers)
    context = {
        key: str(advocate_context.get(key) or "").strip()
        for key in _ADVOCATE_FIELDS
    }
    if (
        any(
            not value
            or len(value) > 500
            or re.search(r"[<>\x00-\x08\x0b\x0c\x0e-\x1f]", value)
            for value in context.values()
        )
        or _date_value(context["notice_date"]) is None
    ):
        raise ValueError("advocate_notice_context_required")
    tokens = {
        **values,
        **context,
        "cheque_amount_words": _amount_words(values["cheque_amount_inr"]),
    }
    source = product.template_path.read_text(encoding="utf-8")
    marker = "## Candidate notice output"
    if marker not in source:
        raise ValueError("cheque_notice_template_marker_missing")
    source = source.split(marker, 1)[1].strip()
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = tokens.get(key)
        if not value:
            missing.add(key)
            return ""
        return value

    markdown = _TOKEN.sub(replace, source)
    if missing:
        raise ValueError("missing_cheque_notice_tokens:" + ",".join(sorted(missing)))
    return _artifact(
        product,
        values,
        "NOTICE_REVIEW_PDF",
        markdown,
        advocate_context=context,
    )


def render_golden_artifacts(product, answers: dict[str, object]) -> dict[str, str]:
    """Return hashes for the exact synthetic package review pair."""

    return {
        "FACTUAL_SUMMARY_PDF": render_factual_summary(product, answers).content_hash,
        "NOTICE_REVIEW_PDF": render_notice_for_advocate(
            product,
            answers,
            _GOLDEN_ADVOCATE_CONTEXT,
        ).content_hash,
    }
