import os
import time
import uuid
import logging
from datetime import datetime, timedelta

import requests
from flask import Flask, request, jsonify, render_template_string

from config import (
    WHATSAPP_VERIFY_TOKEN,
    MAX_FREE_MESSAGES,
    TYPING_DELAY_SECONDS,
    ADMIN_PASSWORD,
)

from db import Base, engine, SessionLocal
from models import User, Conversation, Booking

from services.whatsapp_service import (
    send_text,
    send_buttons,
    send_typing_on,
    send_typing_off,
)
from services.openai_service import (
    detect_language,
    detect_category,
    generate_legal_reply,
)
from services.booking_service import create_booking_for_user

# ---------------- APP & LOGGING ----------------

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Make sure tables exist
Base.metadata.create_all(bind=engine)

# Single shared DB session (OK for small app)
db = SessionLocal()

# ---------------- CONSTANTS & TEXTS ----------------

TYPING_DELAY = TYPING_DELAY_SECONDS
CONSULT_FEE_RS = 199  # match PAYMENT_BASE_URL in config.py

WELCOME_BASE = (
    "👋 Welcome to *NyaySetu — The Bridge To Justice*.\n\n"
    "Your Case ID: *{case_id}*\n\n"
    "Please choose your preferred language:"
)

LANGUAGE_BUTTONS = [
    {"id": "lang_en", "title": "English"},
    {"id": "lang_hi", "title": "हिंदी"},
    {"id": "lang_hinglish", "title": "Hinglish"},
]

INTRO_SUGGESTIONS = [
    {"id": "police", "title": "🚨 Police / FIR"},
    {"id": "family", "title": "👪 Family / Marriage"},
    {"id": "property", "title": "🏠 Property / Land"},
    {"id": "money", "title": "💰 Money / Recovery"},
    {"id": "business", "title": "💼 Business / Work"},
]

FREE_LIMIT_TEXT = {
    "English": (
        "You’ve reached your free answer limit. 🙏\n\n"
        "To get more detailed help and speak with a verified lawyer, "
        "please book a consultation call."
    ),
    "Hindi": (
        "Aapne apne free jawab ki seema poori kar li hai. 🙏\n\n"
        "Zyada madad ke liye verified vakil se baat karne ke liye "
        "kripya consultation book karein."
    ),
    "Hinglish": (
        "Aapka free answer limit khatam ho gaya hai. 🙏\n\n"
        "Aage ki madad ke liye ek verified lawyer ke saath consultation book karein."
    ),
    "Marathi": (
        "तुमची मोफत उत्तरांची मर्यादा पूर्ण झाली आहे. 🙏\n\n"
        "पुढील मदतीसाठी कृपया सल्लामसलत बुक करा."
    ),
}

WAIT_MESSAGE = "🧠 Gathering the correct legal information…\nPlease wait a moment."

BOOK_CTA_EN = (
    "📞 *Book a 45-minute call with a verified lawyer* for just "
    f"*₹{CONSULT_FEE_RS}*.\n\n"
    "I’ll first confirm a suitable date & time, then share a secure payment link."
)

TIME_SLOTS = {
    "TIME_morning": ("Morning", "10 AM – 1 PM"),
    "TIME_afternoon": ("Afternoon", "1 PM – 4 PM"),
    "TIME_evening": ("Evening", "4 PM – 7 PM"),
}

GREETING_KEYWORDS = {"hi", "hello", "hey", "namaste", "namaskar", "hi nyaysetu"}
COMMAND_KEYWORDS = {
    "book",
    "book call",
    "consult",
    "consultation",
    "talk to lawyer",
    "call lawyer",
}
TIME_COMMANDS = set(TIME_SLOTS.keys())

# In-memory booking state: {whatsapp_id: {"date": "YYYY-MM-DD", "step": "await_time"}}
pending_booking_state = {}


# ---------------- SMALL HELPERS ----------------

def generate_case_id() -> str:
    """Short, user-friendly Case ID."""
    suffix = uuid.uuid4().hex[:6].upper()
    return f"NS-{suffix}"


def get_or_create_user(wa_id: str) -> User:
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if user:
        return user
    user = User(
        whatsapp_id=wa_id,
        case_id=generate_case_id(),
        language="English",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def log_message(wa_id: str, direction: str, text: str):
    conv = Conversation(
        user_whatsapp_id=wa_id,
        direction=direction,
        text=text,
    )
    db.add(conv)
    db.commit()


def user_message_count(wa_id: str) -> int:
    return (
        db.query(Conversation)
        .filter_by(user_whatsapp_id=wa_id, direction="user")
        .count()
    )


def count_legal_questions(wa_id: str) -> int:
    """
    Count only 'real' legal questions:
    - ignore greetings
    - ignore booking commands
    - ignore date/time selections
    """
    msgs = (
        db.query(Conversation)
        .filter_by(user_whatsapp_id=wa_id, direction="user")
        .order_by(Conversation.timestamp.asc())
        .all()
    )

    total = 0
    for m in msgs:
        body = (m.text or "").strip().lower()
        if not body:
            continue
        if body in GREETING_KEYWORDS:
            continue
        if body in COMMAND_KEYWORDS:
            continue
        if body.startswith("date_"):
            continue
        if body in TIME_COMMANDS:
            continue
        total += 1
    return total


def parse_date_from_text(text: str):
    """
    Convert values like 'DATE_2025-12-04' or '04 Dec' into 'YYYY-MM-DD'.
    """
    if not text:
        return None

    text = text.strip()

    # Direct format: DATE_YYYY-MM-DD
    if text.upper().startswith("DATE_"):
        return text[5:]

    now = datetime.now()

    candidates = [text, text.replace(",", "")]
    formats = [
        "%a %d %b",       # Thu 04 Dec
        "%a %d %b %Y",    # Thu 04 Dec 2025
        "%d %b",          # 04 Dec
        "%d %b %Y",       # 04 Dec 2025
        "%d-%m-%Y",       # 04-12-2025
        "%d/%m/%Y",       # 04/12/2025
        "%Y-%m-%d",       # 2025-12-04
    ]

    for cand in candidates:
        for fmt in formats:
            try:
                dt = datetime.strptime(cand, fmt)
                if "%Y" not in fmt:
                    dt = dt.replace(year=now.year)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

    return None


def send_list_dates(to, days=7):
    """
    Send WhatsApp interactive list for next `days` days.
    """
    from config import WHATSAPP_PHONE_ID, WHATSAPP_ACCESS_TOKEN

    today = datetime.now()
    rows = []
    for i in range(days):
        d = today + timedelta(days=i)
        rows.append(
            {
                "id": d.strftime("DATE_%Y-%m-%d"),
                "title": d.strftime("%a, %d %b"),
                "description": "",
            }
        )

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": "📅 Please select a convenient date for your consultation:"
            },
            "action": {
                "button": "Select Date",
                "sections": [{"title": "Available Dates", "rows": rows}],
            },
        },
    }

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(
            f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages",
            json=payload,
            headers=headers,
            timeout=10,
        )
        logging.info("WhatsApp send_list_dates %s %s", r.status_code, r.text)
    except Exception as e:
        logging.error("Error sending date list: %s", e)


def language_from_id(btn_id: str) -> str:
    if btn_id == "lang_hi":
        return "Hindi"
    if btn_id == "lang_hinglish":
        return "Hinglish"
    return "English"


def get_free_limit_text(lang: str) -> str:
    return FREE_LIMIT_TEXT.get(lang, FREE_LIMIT_TEXT["English"])


# ---------------- WEBHOOK VERIFY (GET) ----------------

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        logging.info("Webhook verified successfully.")
        return challenge, 200

    logging.warning("Webhook verification failed.")
    return "Forbidden", 403


# ---------------- MAIN WHATSAPP WEBHOOK (POST) ----------------

@app.route("/webhook", methods=["POST"])
def handle_whatsapp():
    payload = request.get_json(silent=True) or {}
    logging.info("Incoming payload: %s", payload)

    entry = (payload.get("entry") or [None])[0] or {}
    changes = (entry.get("changes") or [None])[0] or {}
    value = changes.get("value") or {}

    # Handle status callbacks (delivered, read, etc.) – ignore for now
    if "statuses" in value and not value.get("messages"):
        return jsonify({"status": "ok"}), 200

    messages = value.get("messages") or []
    if not messages:
        return jsonify({"status": "no_messages"}), 200

    msg = messages[0]
    wa_id = None
    text_body = None

    contacts = value.get("contacts") or []
    if contacts:
        wa_id = contacts[0].get("wa_id")

    # Interactive button or list reply
    if msg.get("type") == "interactive":
        interactive = msg.get("interactive", {})
        itype = interactive.get("type")
        if itype == "button_reply":
            button_reply = interactive.get("button_reply", {})
            text_body = button_reply.get("id") or button_reply.get("title")
        elif itype == "list_reply":
            list_reply = interactive.get("list_reply", {})
            text_body = list_reply.get("id") or list_reply.get("title")
    elif msg.get("type") == "text":
        text_body = (msg.get("text") or {}).get("body")

    text_body = (text_body or "").strip()
    logging.info("Parsed text_body='%s'", text_body)

    if not wa_id:
        return jsonify({"status": "missing_wa_id"}), 200

    user = get_or_create_user(wa_id)
    log_message(wa_id, "user", text_body)

    # ---------------- GREETING & ONBOARDING ----------------

    lower = text_body.lower()

    is_new_user = user_message_count(wa_id) <= 1
    if is_new_user or lower in GREETING_KEYWORDS or lower in {"start", "restart"}:
        welcome = WELCOME_BASE.format(case_id=user.case_id)
        send_text(wa_id, welcome)
        send_buttons(wa_id, "Select your language:", LANGUAGE_BUTTONS)
        return jsonify({"status": "welcome"}), 200

    # ---------------- LANGUAGE SELECTION ----------------

    if text_body.startswith("lang_"):
        lang = language_from_id(text_body)
        user.language = lang
        db.commit()

        # Short confirmation + ask for issue with light suggestions
        if lang == "Hindi":
            msg = (
                "✅ भाषा चुनी गई: हिंदी.\n\n"
                "कृपया अपना कानूनी सवाल हिंदी में लिखिए.\n"
                "उदाहरण: FIR, परिवार, संपत्ति, पैसा, बिज़नेस…"
            )
        elif lang == "Hinglish":
            msg = (
                "✅ Language set: Hinglish.\n\n"
                "Apna legal sawal Hinglish mein likhiye.\n"
                "Example: FIR, family, property, money, business…"
            )
        else:
            msg = (
                "✅ Language set: English.\n\n"
                "Please type your legal issue in English.\n"
                "Example: FIR, family, property, money, business…"
            )

        send_text(wa_id, msg)
        return jsonify({"status": "language_set"}), 200

    # ---------------- BOOKING FLOW ----------------

    # If user is currently in booking state
    state = pending_booking_state.get(wa_id)

    # Step 1: user selects DATE (from list or manually)
    if state and state.get("step") == "await_date":
        chosen_date = parse_date_from_text(text_body)
        if not chosen_date:
            send_text(
                wa_id,
                "❗ I couldn't understand this date. Please select from the list "
                "or type in format like '04 Dec' or '2025-12-04'.",
            )
            send_list_dates(wa_id)
            return jsonify({"status": "booking_date_invalid"}), 200

        pending_booking_state[wa_id]["date"] = chosen_date
        pending_booking_state[wa_id]["step"] = "await_time"

        # Ask for time slot
        send_buttons(
            wa_id,
            f"📅 Selected date: *{chosen_date}*\n\n"
            "Please select a convenient time slot:",
            [
                {"id": "TIME_morning", "title": "☀️ Morning (10 AM – 1 PM)"},
                {"id": "TIME_afternoon", "title": "🌤 Afternoon (1 PM – 4 PM)"},
                {"id": "TIME_evening", "title": "🌙 Evening (4 PM – 7 PM)"},
            ],
        )
        return jsonify({"status": "booking_time_requested"}), 200

    # Step 2: user selects TIME slot
    if state and state.get("step") == "await_time" and text_body in TIME_SLOTS:
        chosen_date = state.get("date")
        slot_name, slot_window = TIME_SLOTS[text_body]

        preferred_time = f"{chosen_date} — {slot_name} ({slot_window})"

        # Finalize booking (creates OTP + payment link)
        booking = create_booking_for_user(wa_id, preferred_time)

        # Clear pending state
        pending_booking_state.pop(wa_id, None)

        # Send OTP + payment link
        reply = (
            "✅ Your consultation request is *almost confirmed*.\n\n"
            f"📅 *Date & Time*: {preferred_time}\n"
            f"💰 *Fees*: ₹{CONSULT_FEE_RS}\n"
            f"🔐 *OTP for confirmation*: {booking.otp}\n\n"
            f"💳 Please complete the payment using this secure link:\n{booking.payment_link}\n\n"
            "After payment, our team will confirm the booking on WhatsApp.\n"
            "You will also receive a reminder before the call. 📲"
        )
        send_text(wa_id, reply)
        return jsonify({"status": "booking_created"}), 200

    # If user explicitly asks to book now
    if lower in COMMAND_KEYWORDS or "consultation" in lower or "advocate" in lower:
        send_text(wa_id, BOOK_CTA_EN)
        pending_booking_state[wa_id] = {"step": "await_date"}
        send_list_dates(wa_id)
        return jsonify({"status": "booking_flow_started"}), 200

    # ---------------- FREE LIMIT CHECK ----------------

    legal_count = count_legal_questions(wa_id)
    if legal_count >= MAX_FREE_MESSAGES:
        # Free limit reached → show booking CTA
        free_msg = get_free_limit_text(user.language)
        send_text(wa_id, free_msg)
        send_text(wa_id, BOOK_CTA_EN)
        pending_booking_state[wa_id] = {"step": "await_date"}
        send_list_dates(wa_id)
        return jsonify({"status": "free_limit_reached"}), 200

    # ---------------- NORMAL LEGAL ANSWER FLOW ----------------

    # Show wait message + typing indicator
    send_text(wa_id, WAIT_MESSAGE)
    send_typing_on(wa_id)
    time.sleep(TYPING_DELAY)

    # Language & category detection
    lang = user.language or "English"
    try:
        detected_lang = detect_language(text_body)
        if detected_lang:
            lang = detected_lang
            user.language = lang
            db.commit()
    except Exception as e:
        logging.error("Language detection failed: %s", e)

    try:
        category = detect_category(text_body)
    except Exception as e:
        logging.error("Category detection failed: %s", e)
        category = "other"

    # Get legal reply from OpenAI
    reply = generate_legal_reply(text_body, language=lang, category=category)

    send_typing_off(wa_id)
    send_text(wa_id, reply)
    log_message(wa_id, "bot", reply)

    return jsonify({"status": "answered", "language": lang, "category": category}), 200


# ---------------- SIMPLE HEALTH / DEBUG ROUTES ----------------

@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        """
        <h1>NyaySetu WhatsApp Bot</h1>
        <p>Status: <b>OK</b></p>
        <p>DB URL: {{ db_url }}</p>
        """,
        db_url=os.getenv("DATABASE_URL", "sqlite:///nyaysetu.db"),
    )


@app.route("/admin/conversations", methods=["GET"])
def admin_conversations():
    password = request.args.get("password")
    if password != ADMIN_PASSWORD:
        return "Forbidden", 403

    rows = (
        db.query(Conversation)
        .order_by(Conversation.timestamp.desc())
        .limit(100)
        .all()
    )

    html_rows = ""
    for r in rows:
        html_rows += (
            f"<tr><td>{r.timestamp}</td>"
            f"<td>{r.user_whatsapp_id}</td>"
            f"<td>{r.direction}</td>"
            f"<td>{r.text}</td></tr>"
        )

    html = f"""
    <h1>Last 100 Conversations</h1>
    <table border="1" cellpadding="4">
      <tr>
        <th>Time</th><th>WhatsApp ID</th><th>Direction</th><th>Text</th>
      </tr>
      {html_rows}
    </table>
    """
    return html


# ---------------- MAIN ----------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
