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
        assert field_names == expected
        assert set(form["init-values"]) == expected
        footer = next(item for item in children if item["type"] == "Footer")
        action = footer["on-click-action"]
        assert action["name"] == "data_exchange"
        payload_fields = set(action["payload"])
        assert payload_fields == expected

    review_form, review_children = _components(screens["REVIEW_HANDOVER"])
    assert "edit_section" not in review_form["init-values"]
    confirmation = next(
        item for item in review_children if item.get("name") == "facts_confirmed"
    )
    assert confirmation["data-source"] == [{"id": "CONFIRM", "title": "Confirm"}]

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


def test_flow_routes_forward_from_one_entry_and_number_bindings_are_numeric():
    """Mirror the Flow Builder constraints reported by Meta's validator."""

    flow = json.loads(FLOW_ASSET.read_text(encoding="utf-8"))
    screens = {screen["id"]: screen for screen in flow["screens"]}
    screen_order = {screen_id: index for index, screen_id in enumerate(screens)}
    inbound = {screen_id: 0 for screen_id in screens}

    for source, targets in flow["routing_model"].items():
        for target in targets:
            inbound[target] += 1
            assert screen_order[target] > screen_order[source]

    assert [screen_id for screen_id, count in inbound.items() if count == 0] == [
        "SUITABILITY"
    ]

    for screen_id, field in (
        ("DEBT_CHEQUE", "cheque_amount_inr"),
        ("REVIEW_HANDOVER", "cheque_amount_confirmation_inr"),
    ):
        form, children = _components(screens[screen_id])
        component = next(item for item in children if item.get("name") == field)
        assert component["input-type"] == "number"
        assert screens[screen_id]["data"][field]["type"] == "number"
        assert isinstance(screens[screen_id]["data"][field]["__example__"], (int, float))
        assert form["init-values"][field] == f"${{data.{field}}}"
