"""Regression tests for customer-facing locale coverage."""

from __future__ import annotations

import string
from types import SimpleNamespace

from models import DocumentOrder
from services.document_studio_rc9_service import (
    current_question,
    edit_section_rows,
    landing_rows,
)
from translations import TRANSLATIONS
from utils.i18n import t


def _placeholders(value: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(value)
        if field_name
    }


def _user(language: str):
    return SimpleNamespace(language=language)


def test_all_locales_have_the_same_keys_and_placeholder_contracts():
    english_keys = set(TRANSLATIONS["en"])
    for language in ("hi", "mr"):
        assert set(TRANSLATIONS[language]) == english_keys
        for key in english_keys:
            assert _placeholders(TRANSLATIONS[language][key]) == (
                _placeholders(TRANSLATIONS["en"][key])
            ), key


def test_customer_visible_translation_fallbacks_are_explicitly_localized():
    keys = {
        key
        for key in TRANSLATIONS["en"]
        if key.startswith(("document_", "brief_"))
    }
    intentionally_shared = {
        "document_studio",
        "document_landing_header",
    }
    for language in ("hi", "mr"):
        untranslated = {
            key
            for key in keys - intentionally_shared
            if TRANSLATIONS[language][key] == TRANSLATIONS["en"][key]
        }
        assert untranslated == set()


def test_only_brand_names_are_shared_verbatim_across_locales():
    intentionally_shared = {
        "document_studio",
        "document_landing_header",
    }
    for language in ("hi", "mr"):
        shared = {
            key
            for key, value in TRANSLATIONS[language].items()
            if value == TRANSLATIONS["en"][key]
        }
        assert shared == intentionally_shared


def test_marathi_document_and_brief_copy_uses_devanagari():
    for key, value in TRANSLATIONS["mr"].items():
        if not key.startswith(("document_", "brief_")):
            continue
        if key in {"document_studio", "document_landing_header"}:
            continue
        assert any("\u0900" <= character <= "\u097f" for character in value), key


def test_document_studio_landing_and_edit_rows_are_localized():
    marathi_user = _user("mr")
    rows = landing_rows(marathi_user, t)
    assert rows[0]["title"] == "दस्तऐवज तयार करा"
    assert rows[1]["description"] == "जतन केलेली उत्तरे पुन्हा सुरू करा"

    edit_rows = edit_section_rows(marathi_user, t)
    assert edit_rows[0]["title"] == "पात्रता"
    assert edit_rows[0]["description"] == "फक्त हा विभाग बदला"


def test_document_question_presentation_is_localized_without_schema_changes():
    order = DocumentOrder(
        current_step="property_eligibility",
        draft_answers_json="{}",
    )

    question = current_question(order, _user("mr"), t)

    assert question["prompt"].startswith("खालील तिन्ही बाबींची पुष्टी करा")
    assert question["section_title"] == "पात्रता"
    assert question["options"] == (("YES", "होय"), ("NO", "नाही"))

