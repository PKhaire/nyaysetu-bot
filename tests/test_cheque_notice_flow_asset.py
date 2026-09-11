"""Contract tests for the Meta-hosted cheque-notice Flow asset."""

from __future__ import annotations

import json
from pathlib import Path

from services.cheque_notice_intake_service import FLOW_SCREENS, SCREEN_FIELDS
from services.cheque_notice_product import QUESTION_DEFINITIONS


FLOW_ASSET = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "document-studio"
    / "flows"
    / "cheque-notice-intake-v1.json"
)


def _components(screen):
    children = screen["layout"]["children"]
    form = next(item for item in children if item["type"] == "Form")
    return form, form["children"]


def test_flow_asset_matches_the_approved_six_section_schema():
    flow = json.loads(FLOW_ASSET.read_text(encoding="utf-8"))
    screens = {screen["id"]: screen for screen in flow["screens"]}

    assert flow["version"] == "7.3"
    assert flow["data_api_version"] == "3.0"
    assert tuple(screens) == (*FLOW_SCREENS, "SUCCESS")
    assert set(flow["routing_model"]) == set(screens)
    assert flow["routing_model"]["SUCCESS"] == []

    for screen_id in FLOW_SCREENS:
        form, children = _components(screens[screen_id])
        field_names = {
            item["name"] for item in children if "name" in item
        }
        expected = set(SCREEN_FIELDS[screen_id])
        if screen_id == "REVIEW_HANDOVER":
            field_names.remove("edit_section")
        assert field_names == expected
        assert set(form["init-values"]) == expected
        footer = next(item for item in children if item["type"] == "Footer")
        action = footer["on-click-action"]
        assert action["name"] == "data_exchange"
        payload_fields = set(action["payload"])
        if screen_id == "REVIEW_HANDOVER":
            payload_fields.remove("edit_section")
        assert payload_fields == expected

    rendered_asset = FLOW_ASSET.read_text(encoding="utf-8")
    for question in QUESTION_DEFINITIONS:
        assert question.prompt in rendered_asset


def test_flow_terminal_screen_discloses_the_staging_boundary():
    flow = json.loads(FLOW_ASSET.read_text(encoding="utf-8"))
    terminal = next(screen for screen in flow["screens"] if screen["id"] == "SUCCESS")
    text = json.dumps(terminal)

    assert terminal["terminal"] is True
    assert terminal["success"] is True
    assert "staging" in text.lower()
    assert "no payment" in text.lower()
    assert "no notice" in text.lower()
