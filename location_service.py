import json
import os

# ===============================
# COMMON ALIASES (REAL WORLD)
# ===============================

# ===============================
# COMMON DISTRICT / CITY ALIASES
# (REAL-WORLD USER INPUTS)
# ===============================

ALIASES = {
    # --------------------
    # Maharashtra
    # --------------------
    "mum": "Mumbai",
    "mumbai": "Mumbai",
    "bombay": "Mumbai",
    "new bombay": "Mumbai",
    "navi mumbai": "Mumbai",

    "pn": "Pune",
    "pune": "Pune",

    "nsk": "Nashik",
    "nashik": "Nashik",

    "ngp": "Nagpur",
    "nagpur": "Nagpur",

    "aur": "Aurangabad",
    "aurangabad": "Aurangabad",
    "sambhajinagar": "Aurangabad",

    "thn": "Thane",
    "thane": "Thane",

    "klg": "Kolhapur",
    "kolhapur": "Kolhapur",

    "slp": "Solapur",
    "solapur": "Solapur",

    "ahm": "Ahmednagar",
    "ahmednagar": "Ahmednagar",

    # --------------------
    # Karnataka
    # --------------------
    "blr": "Bengaluru",
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "blore": "Bengaluru",

    "mys": "Mysuru",
    "mysore": "Mysuru",
    "mysuru": "Mysuru",

    "hub": "Hubballi",
    "hubli": "Hubballi",
    "hubballi": "Hubballi",

    # --------------------
    # Delhi / NCR
    # --------------------
    "dl": "Delhi",
    "delhi": "Delhi",

    "nd": "New Delhi",
    "new delhi": "New Delhi",

    "ggn": "Gurugram",
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",

    "noida": "Gautam Buddha Nagar",
    "gbn": "Gautam Buddha Nagar",

    "fbd": "Faridabad",
    "faridabad": "Faridabad",

    "ghz": "Ghaziabad",
    "ghaziabad": "Ghaziabad",

    # --------------------
    # Telangana
    # --------------------
    "hyd": "Hyderabad",
    "hyderabad": "Hyderabad",

    "sec": "Hyderabad",
    "secunderabad": "Hyderabad",

    # --------------------
    # Tamil Nadu
    # --------------------
    "chn": "Chennai",
    "chennai": "Chennai",
    "madras": "Chennai",

    "cbe": "Coimbatore",
    "coimbatore": "Coimbatore",

    "trichy": "Tiruchirappalli",
    "tiruchirappalli": "Tiruchirappalli",

    "mdr": "Madurai",
    "madurai": "Madurai",

    # --------------------
    # West Bengal
    # --------------------
    "kol": "Kolkata",
    "kolkata": "Kolkata",
    "calcutta": "Kolkata",

    "hwh": "Howrah",
    "howrah": "Howrah",

    # --------------------
    # Gujarat
    # --------------------
    "amd": "Ahmedabad",
    "ahm": "Ahmedabad",
    "ahmedabad": "Ahmedabad",

    "srt": "Surat",
    "surat": "Surat",

    "bdq": "Vadodara",
    "vadodara": "Vadodara",
    "baroda": "Vadodara",

    # --------------------
    # Rajasthan
    # --------------------
    "jp": "Jaipur",
    "jaipur": "Jaipur",

    "jodh": "Jodhpur",
    "jodhpur": "Jodhpur",

    "udaipur": "Udaipur",

    # --------------------
    # Madhya Pradesh
    # --------------------
    "ind": "Indore",
    "indore": "Indore",

    "bhp": "Bhopal",
    "bhopal": "Bhopal",

    "gwl": "Gwalior",
    "gwalior": "Gwalior",

    # --------------------
    # Uttar Pradesh
    # --------------------
    "lko": "Lucknow",
    "lucknow": "Lucknow",

    "knp": "Kanpur",
    "kanpur": "Kanpur",

    "agr": "Agra",
    "agra": "Agra",

    "vns": "Varanasi",
    "varanasi": "Varanasi",
    "banaras": "Varanasi",

    # --------------------
    # Punjab / Haryana
    # --------------------
    "chd": "Chandigarh",
    "chandigarh": "Chandigarh",

    "ldh": "Ludhiana",
    "ludhiana": "Ludhiana",

    "amb": "Ambala",
    "ambala": "Ambala",

    # --------------------
    # Bihar
    # --------------------
    "ptn": "Patna",
    "patna": "Patna",

    "gaya": "Gaya",

    # --------------------
    # Odisha
    # --------------------
    "bbsr": "Khordha",
    "bhubaneswar": "Khordha",

    "ctc": "Cuttack",
    "cuttack": "Cuttack",

    # --------------------
    # Kerala
    # --------------------
    "tvm": "Thiruvananthapuram",
    "trivandrum": "Thiruvananthapuram",
    "thiruvananthapuram": "Thiruvananthapuram",

    "ekm": "Ernakulam",
    "kochi": "Ernakulam",
    "ernakulam": "Ernakulam",
}

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

# Reverse lookup for alias resolution
DISTRICT_TO_STATE = {}

for key, entries in DISTRICT_INDEX.items():
    for district, state in entries:
        DISTRICT_TO_STATE[district.lower()] = state

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
    
    # -------------------------------
    # ALIAS SHORT-CIRCUIT (FAST PATH)
    # -------------------------------
    if text in ALIASES:
        district = ALIASES[text]
        state = DISTRICT_TO_STATE.get(district.lower())
        if state:
            return district, state, "HIGH"

    scores = []
    
    for district_key, entries in DISTRICT_INDEX.items():
        if district_key.startswith(text):
            score = 100
        elif text in district_key:
            score = 80
        else:
            continue
    
        for district, state in entries:
            scores.append((score, district, state))

    if not scores:
        return None, None, "LOW"
    
    scores.sort(reverse=True, key=lambda x: x[0])
    
    top_score = scores[0][0]
    top_matches = [s for s in scores if s[0] == top_score]
    
    if len(top_matches) > 1:
        return top_matches, None, "MULTIPLE"
    
    _, district, state = top_matches[0]
    return district, state, "HIGH"

