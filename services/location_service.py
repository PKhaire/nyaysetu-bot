"""
Location Service
----------------
✔ State & District detection
✔ Alias support (MH, DL, etc.)
✔ Fuzzy matching (maha → Maharashtra)
✔ Typo tolerance (maharastra)
✔ Pagination (WhatsApp safe)
✔ Remember & prioritize last state/district
✔ Country detect from phone
"""

import json
import os
import difflib
from typing import Dict, List, Optional, Tuple

# -------------------------------------------------
# Cache
# -------------------------------------------------
_INDIA_DATA: Dict[str, List[str]] | None = None


# -------------------------------------------------
# State aliases
# -------------------------------------------------
STATE_ALIASES = {
    "mh": "Maharashtra",
    "dl": "Delhi",
    "ka": "Karnataka",
    "tn": "Tamil Nadu",
    "up": "Uttar Pradesh",
    "rj": "Rajasthan",
    "gj": "Gujarat",
    "mp": "Madhya Pradesh",
    "wb": "West Bengal",
    "pb": "Punjab",
    "hr": "Haryana",
    "jk": "Jammu and Kashmir",
}

STATE_SHORT_NAMES = {
    "Andaman and Nicobar Islands": "Andaman & Nicobar",
    "Dadra and Nagar Haveli and Daman and Diu": "DNH & Daman-Diu",
    "Jammu and Kashmir": "Jammu & Kashmir",
}


# -------------------------------------------------
# Load JSON
# -------------------------------------------------
def _load_india_data() -> Dict[str, List[str]]:
    global _INDIA_DATA
    if _INDIA_DATA is not None:
        return _INDIA_DATA

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_dir, "data", "india_districts.json")

    with open(json_path, "r", encoding="utf-8") as f:
        _INDIA_DATA = json.load(f)

    return _INDIA_DATA


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def detect_country_from_wa_id(wa_id: str) -> str:
    return "IN" if wa_id.startswith("91") else "UNKNOWN"


def get_all_states() -> List[str]:
    return sorted(_load_india_data().keys())


def get_districts_for_state(state: str) -> List[str]:
    return sorted(_load_india_data().get(state, []))


def _prioritize(items: List[str], preferred: Optional[str]) -> List[str]:
    if not preferred:
        return items

    preferred = preferred.lower().strip()
    for i, item in enumerate(items):
        if item.lower() == preferred:
            return [item] + items[:i] + items[i + 1 :]
    return items


def _fuzzy_match(text: str, choices: List[str], cutoff: float = 0.6) -> Optional[str]:
    matches = difflib.get_close_matches(text, choices, n=1, cutoff=cutoff)
    return matches[0] if matches else None


# -------------------------------------------------
# STATE DETECTION
# -------------------------------------------------
def detect_state_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    text = text.lower().strip()
    data = _load_india_data()

    if text in STATE_ALIASES:
        return STATE_ALIASES[text]

    for state in data.keys():
        if state.lower() in text:
            return state

    return _fuzzy_match(text, list(data.keys()))


# -------------------------------------------------
# DISTRICT DETECTION
# -------------------------------------------------
def detect_district_from_text(text: str) -> Optional[Tuple[str, str]]:
    if not text:
        return None

    text = text.lower().strip()
    data = _load_india_data()

    for state, districts in data.items():
        for district in districts:
            if district.lower() in text:
                return state, district

        match = _fuzzy_match(text, districts)
        if match:
            return state, match

    return None


# -------------------------------------------------
# STATE LIST (Paginated + prioritized)
# -------------------------------------------------
def build_state_list_rows(
    page: int = 1,
    page_size: int = 9,
    preferred_state: Optional[str] = None,
):
    states = _prioritize(get_all_states(), preferred_state)

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

    if end < len(states):
        rows.append({
            "id": f"state_page_{page + 1}",
            "title": "More states…",
            "description": ""
        })

    return rows


# -------------------------------------------------
# DISTRICT LIST (Paginated + prioritized)
# -------------------------------------------------
def build_district_list_rows(
    state: str,
    page: int = 1,
    page_size: int = 9,
    preferred_district: Optional[str] = None,
):
    districts = _prioritize(
        get_districts_for_state(state),
        preferred_district
    )

    start = (page - 1) * page_size
    end = start + page_size

    rows = []

    for district in districts[start:end]:
        rows.append({
            "id": f"district_{district}",
            "title": district[:24],
            "description": ""
        })

    if end < len(districts):
        rows.append({
            "id": f"district_page_{page + 1}",
            "title": "More districts…",
            "description": ""
        })

    return rows
