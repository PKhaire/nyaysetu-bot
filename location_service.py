import json
import os


# ===============================
# NORMALIZATION
# ===============================

def normalize(text: str) -> str:
    return (
        text.lower()
        .strip()
        .replace(".", "")
        .replace("-", " ")
    )


# ===============================
# LOAD INDIA DISTRICTS (ONCE)
# ===============================

BASE_DIR = os.path.dirname(__file__)
DISTRICTS_PATH = os.path.join(BASE_DIR, "data", "india_districts.json")

with open(DISTRICTS_PATH, "r", encoding="utf-8") as f:
    INDIA_DISTRICTS = json.load(f)


# ===============================
# BUILD DISTRICT → STATE INDEX
# ===============================

def build_district_index(india_districts: dict):
    """
    Builds:
    {
        "mumbai city": [("Mumbai City", "Maharashtra")],
        "bilaspur": [
            ("Bilaspur", "Chhattisgarh"),
            ("Bilaspur", "Himachal Pradesh")
        ]
    }
    """
    index = {}
    for state, districts in india_districts.items():
        for district in districts:
            key = normalize(district)
            index.setdefault(key, []).append((district, state))
    return index


DISTRICT_INDEX = build_district_index(INDIA_DISTRICTS)


# ===============================
# DETECTION LOGIC
# ===============================

def detect_district_and_state(text: str):
    """
    Returns:
      (district, state, confidence)

    confidence:
      - "HIGH"       → single strong match
      - "MULTIPLE"   → multiple states
      - "LOW"        → no confident match
    """
    if not text:
        return None, None, "LOW"

    text = normalize(text)

    if len(text) < 3:
        return None, None, "LOW"

    matches = []

    for district_key, entries in DISTRICT_INDEX.items():
        if text in district_key:
            matches.extend(entries)

    if not matches:
        return None, None, "LOW"

    if len(matches) > 1:
        return matches, None, "MULTIPLE"

    district, state = matches[0]
    return district, state, "HIGH"
