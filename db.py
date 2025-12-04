import json
import os

DB_FILE = "users.json"

# Ensure DB file exists
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({}, f)


def load_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)


def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_user(user_id: str):
    """Return stored user from DB or None."""
    db = load_db()
    return db.get(user_id)


def create_user(user_id: str):
    """Insert new user and return the created record."""
    db = load_db()
    case_id = generate_case_id()
    user = {
        "user_id": user_id,
        "case_id": case_id,
        "state": "idle",
        "language": None,
        "free_count": 0,
    }
    db[user_id] = user
    save_db(db)
    return user


def update_user(user: dict):
    """Update a stored user row."""
    db = load_db()
    db[user["user_id"]] = user
    save_db(db)
    return user


# ----------- Case ID Generator (short + unique) -----------------

def generate_case_id():
    import random
    import string
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"NS-{suffix}"
