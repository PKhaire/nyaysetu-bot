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
STATE_SHORT_NAMES = {
    "Andaman and Nicobar Islands": "Andaman & Nicobar",
    "Dadra and Nagar Haveli and Daman and Diu": "Diu and Daman",
    "Jammu and Kashmir": "Jammu & Kashmir",
}

def build_state_list_rows(page: int = 1, page_size: int = 9):
    """
    Returns max 10 rows:
    - 9 states
    - 1 'More states…' if remaining
    """
    states = get_all_states()
    start = (page - 1) * page_size
    end = start + page_size

    rows = []

    for state in states[start:end]:
        title = STATE_SHORT_NAMES.get(state, state)[:24]
        rows.append({
            "id": f"state_{state}",
            "title": title,
            "description": ""
        })

    # Add "More states…" button if remaining
    if end < len(states):
        rows.append({
            "id": f"state_page_{page + 1}",
            "title": "More states…",
            "description": ""
        })

    return rows

def build_district_list_rows(state: str, page: int = 1, page_size: int = 9):
    """
    WhatsApp-safe paginated district list.
    - Max 10 rows
    - Max 24 chars title
    """
    districts = get_districts_for_state(state)

    start = (page - 1) * page_size
    end = start + page_size

    rows = []

    for district in districts[start:end]:
        rows.append({
            "id": f"district_{district}",
            "title": district[:24],   # WhatsApp limit
            "description": ""
        })

    # Add pagination row if more districts exist
    if end < len(districts):
        rows.append({
            "id": f"district_page_{page + 1}",
            "title": "More districts…",
            "description": ""
        })

    return rows

