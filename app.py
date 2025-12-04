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

# Single shared DB session (simple pattern, OK for small app on Render)
db = SessionLocal()

# ---------------- CONSTANTS ----------------

TYPING_DELAY = TYPING_DELAY_SECONDS
CONSULT_FEE_RS = 199  # must match your PAYMENT_BASE_URL logic

# Language and flow texts
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

FREE_LIMIT = {
    "English": (
        "You’ve reached your free answer limit. 🙏\n\n"
        "To get more detailed help and speak with a verified lawyer, "
        "please book a consultation."
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

# Booking state in memory: {whatsapp_id: {"date": "YYYY-MM-DD", "step": "awaiting_time"}}
pending_booking_state = {}

TIME_SLOTS = {
    "TIME_morning": ("Morning", "10 AM – 1 PM"),
    "TIME_afternoon": ("Afternoon", "1 PM – 4 PM"),
    "TIME_evening": ("Evening", "4 PM – 7 PM"),
}

GREETING_KEYWORDS = {
    "hi",
    "hello",
    "hey",
    "hola",
    "namaste",
    "namaskar",
    "good morning",
    "good evening",
    "good afternoon",
}

COMMAND_KEYWORDS = {
    "book",
    "booking",
    "consult",
    "consultation",
    "appointment",
    "📅 book consultation",
    "📞 speak to lawyer",
    "📄 get draft notice",
    "call",
    "draft",
    "restart",
    "start",
}

TIME_COMMANDS = {"time_morning", "time_afternoon", "time_evening"}


# ---------------- HELPER FUNCTIONS ----------------

def register_user(wa_id: str) -> User:
    """
    Find or create a user by whatsapp_id.
    """
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if user:
        return user

    case_id = f"NS-{uuid.uuid4().hex[:8].upper()}"
    user = User(
        whatsapp_id=wa_id,
        case_id=case_id,
        language="English",
    )
    db.add(user)
    db.commit()
    logging.info(f"New user registered: {wa_id} → {case_id}")
    return user


def store_message(wa_id: str, direction: str, text: str):
    msg = Conversation(user_whatsapp_id=wa_id, direction=direction, text=text)
    db.add(msg)
    db.commit()


def user_message_count(wa_id: str) -> int:
    return (
        db.query(Conversation)
        .filter_by(user_whatsapp_id=wa_id, direction="user")
        .count()
    )


def get_latest_booking_status(wa_id: str):
    b = (
        db.query(Booking)
        .filter_by(user_whatsapp_id=wa_id)
        .order_by(Booking.created_at.desc())
        .first()
    )
    if not b:
        return None
    return "confirmed" if b.confirmed else "pending"


def count_legal_questions(wa_id: str) -> int:
    """
    Count only 'real' user legal questions:
    - ignore greetings
    - ignore commands (book, call, etc.)
    - ignore DATE_..., TIME_... selections
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
    Convert variants like 'DATE_2025-12-04' or '04 Dec' etc. into 'YYYY-MM-DD'.
    Returns None if parsing fails.
    """
    if not text:
        return None

    text = text.strip()

    # Direct DATE_YYYY-MM-DD format
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
    Uses direct Graph API call (simple helper).
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

    # Status updates (sent, delivered, read) – just ACK quickly
    if value.get("statuses"):
        return jsonify({"status": "ok"}), 200

    messages = value.get("messages") or []
    if not messages:
        return jsonify({"status": "ignored"}), 200

    msg = messages[0]
    wa_from = msg.get("from")
    msg_type = msg.get("type")

    # Extract logical text_body from normal text or interactive reply
    text_body = ""
    if msg_type == "text":
        text_body = (msg.get("text") or {}).get("body", "")
    elif msg_type == "interactive":
        interactive = msg.get("interactive") or {}
        if interactive.get("type") == "button_reply":
            text_body = (interactive.get("button_reply") or {}).get("id", "")
        elif interactive.get("type") == "list_reply":
            text_body = (interactive.get("list_reply") or {}).get("id", "")
    else:
        return jsonify({"status": "ignored_type"}), 200

    text_body = (text_body or "").strip()
    logging.info("Parsed text_body='%s'", text_body)

    try:
        # Ensure user exists
        user = register_user(wa_from)
        lang_for_user = user.language or "English"

        # Store user message
        store_message(wa_from, "user", text_body)

        lowered = text_body.lower()

        # ---------- GREETING / START FLOW ----------
        if lowered in GREETING_KEYWORDS or lowered in {"start", "restart", "hello", "hi"}:
            welcome_text = WELCOME_BASE.format(case_id=user.case_id)
            send_text(wa_from, welcome_text)
            send_buttons(wa_from, "Select your language:", LANGUAGE_BUTTONS)
            return jsonify({"status": "welcome"}), 200

        # ---------- LANGUAGE SELECTION ----------
        if text_body in {"lang_en", "lang_hi", "lang_hinglish"}:
            if text_body == "lang_en":
                user.language = "English"
                body = "Please type your legal issue in English."
            elif text_body == "lang_hi":
                user.language = "Hindi"
                body = "कृपया अपनी कानूनी समस्या हिंदी में लिखें।"
            else:
                user.language = "Hinglish"
                body = "Please type your legal issue in simple Hinglish (Hindi in English letters)."

            db.commit()
            send_text(wa_from, body)

            # Show quick category buttons
            send_buttons(
                wa_from,
                "You can also choose a topic:",
                INTRO_SUGGESTIONS,
            )
            return jsonify({"status": "language_set"}), 200

        # ---------- BOOKING FLOW (BUTTON) ----------
        if lowered in {"book", "book consultation", "📅 book consultation"}:
            pending_booking_state[wa_from] = {"step": "awaiting_date"}
            send_list_dates(wa_from)
            return jsonify({"status": "booking_date_select"}), 200

        # ---------- TIME SELECTION AFTER DATE ----------
        if text_body.startswith("DATE_") or lowered.startswith("date_"):
            date_str = parse_date_from_text(text_body)
            if not date_str:
                send_text(wa_from, "Sorry, I could not understand that date. Please select again.")
                send_list_dates(wa_from)
                return jsonify({"status": "date_error"}), 200

            pending_booking_state[wa_from] = {"step": "awaiting_time", "date": date_str}

            # Time slot buttons
            send_buttons(
                wa_from,
                "Select a convenient time window:",
                [
                    {"id": "TIME_morning", "title": "☀️ Morning (10 AM – 1 PM)"},
                    {"id": "TIME_afternoon", "title": "🌤 Afternoon (1 PM – 4 PM)"},
                    {"id": "TIME_evening", "title": "🌙 Evening (4 PM – 7 PM)"},
                ],
            )
            return jsonify({"status": "time_select"}), 200

        if text_body in TIME_SLOTS:
            state = pending_booking_state.get(wa_from)
            if not state or state.get("step") != "awaiting_time":
                send_text(wa_from, "Please choose a date first so we can schedule properly.")
                send_list_dates(wa_from)
                return jsonify({"status": "missing_date"}), 200

            date_str = state["date"]
            slot_name, slot_window = TIME_SLOTS[text_body]
            preferred_time_text = f"{date_str} — {slot_name} ({slot_window})"

            # Create booking using booking_service
            booking = create_booking_for_user(wa_from, preferred_time_text)
            payment_url = booking.payment_link
            otp = booking.otp

            lang = user.language or "English"
            if lang == "Hindi":
                msg_out = (
                    "📝 धन्यवाद! Aapka session is date/time ke liye note ho gaya hai:\n"
                    f"*{booking.preferred_time}*\n\n"
                    f"💰 45-minute consultation ke liye kripya *₹{CONSULT_FEE_RS}* pay karein.\n"
                    f"🔗 Payment Link: {payment_url}\n"
                    f"🔐 OTP: *{otp}* (verify karne ke liye use ho sakta hai)\n\n"
                    "Payment complete hote hi aapka appointment confirm ho jayega."
                )
            elif lang == "Hinglish":
                msg_out = (
                    "📝 Thank you! Aapka session is time ke liye note ho gaya hai:\n"
                    f"*{booking.preferred_time}*\n\n"
                    f"💰 45-minute legal consultation ke liye kripya *₹{CONSULT_FEE_RS}* pay karein.\n"
                    f"🔗 Payment Link: {payment_url}\n"
                    f"🔐 OTP: *{otp}*\n\n"
                    "Payment complete hote hi aapka appointment confirm ho jayega."
                )
            else:
                msg_out = (
                    "📝 Thank you. We’ve scheduled your session for:\n"
                    f"*{booking.preferred_time}*\n\n"
                    f"💰 To confirm your 45-minute legal expert call, please pay *₹{CONSULT_FEE_RS}*.\n"
                    f"🔗 Payment Link: {payment_url}\n"
                    f"🔐 OTP: *{otp}*\n\n"
                    "Once payment is completed, your appointment will be confirmed "
                    "and a verified legal expert will call you within that window."
                )

            send_text(wa_from, msg_out)
            pending_booking_state.pop(wa_from, None)
            return jsonify({"status": "booking_created"}), 200

        # ---------- FREE MESSAGE LIMIT ----------
        booking_status = get_latest_booking_status(wa_from)
        legal_q_count = count_legal_questions(wa_from)

        if booking_status != "confirmed" and legal_q_count >= MAX_FREE_MESSAGES:
            limit_msg = FREE_LIMIT.get(lang_for_user, FREE_LIMIT["English"])
            send_text(wa_from, limit_msg)
            return jsonify({"status": "limit_reached"}), 200

        # ---------- NORMAL LEGAL AI REPLY ----------
        detected_lang = detect_language(text_body)
        category = detect_category(text_body)
        logging.info("Lang=%s, Category=%s", detected_lang, category)

        # Show typing & wait message
        send_typing_on(wa_from)
        send_text(wa_from, WAIT_MESSAGE)
        time.sleep(TYPING_DELAY)

        reply = generate_legal_reply(text_body, detected_lang, category)
        send_typing_off(wa_from)

        send_text(wa_from, reply)
        store_message(wa_from, "bot", reply)

        # Suggest next steps (if still in free range and not confirmed booking)
        if booking_status != "confirmed" and legal_q_count < MAX_FREE_MESSAGES:
            if detected_lang == "Marathi":
                btn_body = "पुढे काय करायचे ते निवडा:"
            elif detected_lang == "Hinglish":
                btn_body = "Aap agla step choose kar sakte hain:"
            elif detected_lang == "Hindi":
                btn_body = "Aap agla step chun sakte hain:"
            else:
                btn_body = "You can also choose what to do next:"

            send_buttons(
                wa_from,
                btn_body,
                [
                    {"id": "book", "title": "📅 Book Consultation"},
                    {"id": "call", "title": "📞 Speak to Lawyer"},
                    {"id": "draft", "title": "📄 Get Draft Notice"},
                ],
            )

        return jsonify({"status": "answered"}), 200

    except Exception as e:
        logging.exception("Webhook error")
        return jsonify({"status": "error", "error": str(e)}), 500


# ---------------- SIMPLE ADMIN DASHBOARD ----------------

ADMIN_HTML = """
<html>
<head>
  <title>NyaySetu Admin</title>
  <style>
    body { font-family: Arial; padding: 30px; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 40px; }
    th, td { border: 1px solid #555; padding: 10px; font-size: 14px; }
    th { background-color: #eee; }
    h1 { margin-bottom: 30px; }
  </style>
</head>
<body>
  <h1>NyaySetu — Admin Dashboard</h1>

  <h2>Users</h2>
  <table>
    <tr><th>WhatsApp</th><th>Case ID</th><th>Language</th><th>Created</th></tr>
    {% for u in users %}
    <tr>
      <td>{{u.whatsapp_id}}</td>
      <td>{{u.case_id}}</td>
      <td>{{u.language}}</td>
      <td>{{u.created_at}}</td>
    </tr>
    {% endfor %}
  </table>

  <h2>Bookings</h2>
  <table>
    <tr><th>WhatsApp</th><th>Preferred Time</th><th>Confirmed</th><th>Created</th></tr>
    {% for b in bookings %}
    <tr>
      <td>{{b.user_whatsapp_id}}</td>
      <td>{{b.preferred_time}}</td>
      <td>{{"Yes" if b.confirmed else "No"}}</td>
      <td>{{b.created_at}}</td>
    </tr>
    {% endfor %}
  </table>
</body>
</html>
"""


@app.route("/admin")
def admin_dashboard():
    pwd = request.args.get("pwd", "")
    if pwd != ADMIN_PASSWORD:
        return "Forbidden", 403

    users = db.query(User).order_by(User.created_at.desc()).limit(200).all()
    bookings = db.query(Booking).order_by(Booking.created_at.desc()).limit(200).all()
    return render_template_string(ADMIN_HTML, users=users, bookings=bookings)


# ---------------- HEALTH CHECK ----------------

@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


# ---------------- LOCAL DEV RUN ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting NyaySetu app on port {port}")
    app.run(host="0.0.0.0", port=port)
