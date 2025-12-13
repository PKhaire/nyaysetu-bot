# services/location_service.py

import json
import re
from functools import lru_cache

# Path to JSON
JSON_PATH = "data/india_districts.json"


@lru_cache(maxsize=1)
def load_locations():
    """Loads states and districts from JSON only once (cached)."""
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    states = list(data.keys())

    # Flatten district mapping
    district_map = {}
    for state, districts in data.items():
        for d in districts:
            district_map[d.lower()] = state

    return data, states, district_map


# -------------------------------------------------------------------
# STATE DETECTION
# -------------------------------------------------------------------
def detect_state(text):
    """AI-like fuzzy detection of state from user text."""
    text = text.lower().strip()
    _, states, district_map = load_locations()

    # direct match
    for s in states:
        if s.lower() == text:
            return s

    # match inside sentence (e.g., "I live in Maharashtra")
    for s in states:
        if s.lower() in text:
            return s

    # district-based detection (user typed district only)
    for district_lower, state in district_map.items():
        if district_lower in text:
            return state

    return None


# -------------------------------------------------------------------
# DISTRICT DETECTION
# -------------------------------------------------------------------
def detect_district(state, text):
    """Detect district within a state."""
    text = text.lower().strip()
    data, _, _ = load_locations()
    
    if state not in data:
        return None

    for d in data[state]:
        if d.lower() == text:
            return d
        if d.lower() in text:
            return d

    return None


# -------------------------------------------------------------------
# LIST PICKER HELPERS
# -------------------------------------------------------------------
def list_states():
    """WhatsApp-friendly list picker rows for states."""
    _, states, _ = load_locations()
    return [
        {
            "id": f"state_{s}",
            "title": s,
            "description": ""
        }
        for s in states
    ]


def list_districts(state):
    """List picker rows for districts of a given state."""
    data, _, _ = load_locations()

    if state not in data:
        return []

    return [
        {
            "id": f"district_{state}_{d}",
            "title": d,
            "description": ""
        }
        for d in data[state]
    ]
