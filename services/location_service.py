# services/location_service.py
"""
Location Service
----------------
Handles India State & District logic:
- Loads india_districts.json once (cached)
- Detects state/district from free text
- Builds WhatsApp list picker rows
"""

import json
import os
import re
from typing import Dict, List, Optional, Tuple

# Cache (loaded once)
_INDIA_DATA: Dict[str, List[str]] | None = None


def _load_india_data() -> Dict[str, List[str]]:
    """
    Load india_districts.json only once and cache it.
    """
    global _INDIA_DATA
    if _INDIA_DATA is not None:
        return _INDIA_DATA

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_dir, "data", "india_districts.json")
    
    with open(json_path, "r", encoding="utf-8") as f:
        _INDIA_DATA = json.load(f)

    return _INDIA_DATA


# ----------------------------
# Public helpers
# ----------------------------

def get_all_states() -> List[str]:
    data = _load_india_data()
    return sorted(data.keys())


def get_districts_for_state(state: str) -> List[str]:
    data = _load_india_data()
    return sorted(data.get(state, []))


def detect_state_from_text(text: str) -> Optional[str]:
    """
    Try to detect state from free text.
    Example: "I am from Maharashtra"
    """
    text = text.lower()
    data = _load_india_data()

    for state in data.keys():
        if state.lower() in text:
            return state
    return None


def detect_district_from_text(text: str) -> Optional[Tuple[str, str]]:
    """
    Try to detect district and infer state.
    Returns (state, district) if found.
    """
    text = text.lower()
    data = _load_india_data()

    for state, districts in data.items():
        for district in districts:
            if district.lower() in text:
                return state, district
    return None


# ----------------------------
# WhatsApp UI helpers
# ----------------------------

def build_state_list_rows(limit: int = 10) -> List[dict]:
    """
    WhatsApp list picker rows for states.
    """
    states = get_all_states()[:limit]
    rows = []

    for state in states:
        rows.append({
            "id": f"state_{state}",
            "title": state,
            "description": ""
        })
    return rows


def build_district_list_rows(state: str, limit: int = 20) -> List[dict]:
    """
    WhatsApp list picker rows for districts of a state.
    """
    districts = get_districts_for_state(state)[:limit]
    rows = []

    for district in districts:
        rows.append({
            "id": f"district_{state}_{district}",
            "title": district,
            "description": ""
        })
    return rows
