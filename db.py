import json
import os
from datetime import datetime
from threading import Lock

DB_FILE = "users.json"
db_lock = Lock()     # Prevents simultaneous writes (Render safety)


def load_db():
    """Load JSON DB, create file if missing."""
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(data):
    """Store JSON DB safely."""
    with db_lock:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)


def get_user(phone):
    users = load_db()
    return users.get(phone)


def create_user(phone, case_id):
    """Register a new user structure when chat starts."""
    users = load_db()
    users[phone] = {
        "user_id": phone,
        "case_id": case_id,
        "state": "awaiting_language",   # new user always receives language selector first
        "language": None,
        "free_count": 0,
        "messages": []                  # store last 10 chat messages
    }
    save_db(users)
    return users[phone]


def update_user(phone, data: dict):
    """Update multiple fields in user profile."""
    users = load_db()
    if phone not in users:
        return
    users[phone].update(data)
    save_db(users)


def add_message(phone, role, message):
    """
    Adds one chat record:
    role = "user" or "bot"
    Only last 10 messages are retained.
    """
    users = load_db()
    user = users.get(phone)
    if not user:
        return

    if "messages" not in user:
        user["messages"] = []

    user["messages"].append({
        "role": role,
        "message": message,
        "timestamp": datetime.utcnow().isoformat()
    })

    user["messages"] = user["messages"][-10:]   # keep only last 10

    save_db(users)
