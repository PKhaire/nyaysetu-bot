import os
import json
import logging
import random
import string
from datetime import datetime

from flask import Flask, request, jsonify

# --- DB & Models ---
from db import create_all, SessionLocal
from models import User, Booking, Rating

# --- Config ---
from config import (
    WHATSAPP_VERIFY_TOKEN,
    MAX_FREE_MESSAGES,
    TYPING_DELAY_SECONDS,
    ADMIN_TOKEN,
)

# --- Services ---
from services.whatsapp_service import (
    send_text,
    send_buttons,
    send_typing_on,
    send_typing_off,
    send_list_picker,
)

from services.openai_service import ai_reply

from services.booking_service import (
    generate_dates_calendar,
    generate_slots_calendar,
    create_booking_temp,
    confirm_booking_after_payment,
    mark_booking_completed,
    ask_rating_buttons,
)

# -------------------------------------------------------------------
# Flask & Logging
# -------------------------------------------------------------------
app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger("app")

# -------------------------------------------------------------------
# Conversation States
# -------------------------------------------------------------------
NORMAL = "NORMAL"
SUGGEST_CONSULT = "SUGGEST_CONSULT"

ASK_NAME = "ASK_NAME"
ASK_CITY = "ASK_CITY"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"
ASK_RATING = "ASK_RATING"

# -------------------------------------------------------------------
# Helper: DB session per request
# -------------------------------------------------------------------
def get_db_session():
    """
    Returns a fresh SQLAlchemy session.
    Call db.close() in finally.
    """
    return SessionLocal()

# -------------------------------------------------------------------
# Helper: Case ID generator
# -------------------------------------------------------------------
def generate_case_id(length: int = 6) -> str:
    suffix = "".join(random.choices(string.hexdigits.upper(), k=length))
    return f"NS-{suffix}"

# -------------------------------------------------------------------
# DB: get or create user
# -------------------------------------------------------------------
def get_or_create_user(db, wa_id: str) -> User:
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if not user:
        user = User(
            whatsapp_id=wa_id,
            case_id=generate_case_id(),
            language="English",
            query_count=0,
            state=NORMAL,
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user {wa_id} with case_id={user.case_id}")
    return user

# -------------------------------------------------------------------
# State helper
# -------------------------------------------------------------------
def save_state(db, user: User, state: str):
    user.state = state
    db.add(user)
    db.commit()

# -------------------------------------------------------------------
# Language helper
# -------------------------------------------------------------------
def handle_language_change(db, user: User, wa_id: str, msg_id: str) -> bool:
    """
    Returns True if this message was a language button and handled.
    """
    language_map = {
        "lang_en": "English",
        "lang_hinglish": "Hinglish",
        "lang_mar": "Marathi",
    }

    new_lang = language_map.get(msg_id)
    if not new_lang:
        return False

    user.language = new_lang
    save_state(db, user, NORMAL)

    send_text(
        wa_id,
        f"Language updated to *{user.language}*.\n\nPlease type your legal issue."
    )
    return True

# -------------------------------------------------------------------
# Booking: start & booking flow
# -------------------------------------------------------------------
def start_booking_flow(db, user: User, wa_id: str):
    """
    Move user into ASK_NAME and start the call-booking journey.
    """
    save_state(db, user, ASK_NAME)
    send_text(
        wa_id,
        "Great! Let's schedule your legal consultation call (₹499).\n\n"
        "First, please tell me your *full name*."
    )

def handle_booking_flow(
    db,
    user: User,
    wa_id: str,
    text: str,
    interactive_id: str | None
):
    """
    State machine for the booking flow.
    """
    t = (text or "").strip()

    # 1) Ask for name
    if user.state == ASK_NAME:
        # Store temporary fields just on the object (no schema change needed)
        user.temp_name = t
        db.add(user)
        db.commit()

        save_state(db, user, ASK_CITY)
        send_text(wa_id, "Thanks! 🙏\nNow please tell me your *city*.")
        return

    # 2) Ask for city
    if user.state == ASK_CITY:
        user.temp_city = t
        db.add(user)
        db.commit()

        save_state(db, user, ASK_CATEGORY)
        send_text(
            wa_id,
            "Got it 👍\nPlease choose your *legal issue category* "
            "(e.g., FIR, Police, Property, Family, Job, Business, Other)."
        )
        return

    # 3) Ask for category
    if user.state == ASK_CATEGORY:
        user.temp_category = t
        db.add(user)
        db.commit()

        # Show date list (next 7 days)
        rows = generate_dates_calendar()
        save_state(db, user, ASK_DATE)
        send_list_picker(
            wa_id,
            header="Select appointment date 👇",
            body="Available Dates",
            rows=rows,
            section_title="Next 7 days",
        )
        return

    # 4) Ask for date (interactive list reply)
    if user.state == ASK_DATE:
        if interactive_id and interactive_id.startswith("date_"):
            user.temp_date = interactive_id.replace("date_", "", 1)
            db.add(user)
            db.commit()

            rows = generate_slots_calendar(user.temp_date)
            save_state(db, user, ASK_SLOT)
            send_list_picker(
                wa_id,
                header=f"Select time slot for {user.temp_date}",
                body="Available time slots (IST)",
                rows=rows,
                section_title="Time Slots",
            )
        else:
            send_text(
                wa_id,
                "Please select a date from the list I sent. "
                "If you didn't receive it, type *Book Consultation* to restart booking."
            )
        return

    # 5) Ask for slot (interactive list reply)
    if user.state == ASK_SLOT:
        if interactive_id and interactive_id.startswith("slot_"):
            user.temp_slot = interactive_id.replace("slot_", "", 1)
            db.add(user)
            db.commit()

            name = getattr(user, "temp_name", "Client")
            city = getattr(user, "temp_city", "NA")
            category = getattr(user, "temp_category", "General")
            date_str = getattr(user, "temp_date", "")
            slot_str = getattr(user, "temp_slot", "")

            booking, payment_link = create_booking_temp(
                db=db,
                user=user,
                name=name,
                city=city,
                category=category,
                date=date_str,
                slot=slot_str,
                price=499,
            )

            user.last_payment_link = payment_link
            save_state(db, user, WAITING_PAYMENT)

            send_text(
                wa_id,
                "✅ *Your appointment details:*\n"
                f"*Name:* {name}\n"
                f"*City:* {city}\n"
                f"*Category:* {category}\n"
                f"*Date:* {date_str}\n"
                f"*Slot:* {slot_str}\n"
                f"*Fees:* ₹499 (one-time)\n\n"
                f"Please complete payment using this link:\n{payment_link}"
            )
        else:
            send_text(
                wa_id,
                "Please select a time slot from the list I sent. "
                "If you didn't receive it, type *Book Consultation* to restart booking."
            )
        return

    # 6) Waiting payment – soft reminder
    if user.state == WAITING_PAYMENT:
        send_text(
            wa_id,
            "💳 Your consultation booking is almost done.\n\n"
            "Once payment is completed, our team will confirm your consultation slot.\n\n"
            f"If you lost the payment link, here it is again:\n"
            f"{user.last_payment_link or 'Link not found, type *Book Consultation* to restart.'}"
        )
        return

    # 7) Rating flow
    if user.state == ASK_RATING:
        try:
            rating_val = int(t)
            if 1 <= rating_val <= 5:
                rating = Rating(
                    whatsapp_id=user.whatsapp_id,
                    score=rating_val,
                    created_at=datetime.utcnow(),
                )
                db.add(rating)
                db.commit()
                save_state(db, user, NORMAL)
                send_text(
                    wa_id,
                    "🙏 Thank you for your feedback! It helps us improve NyaySetu for everyone."
                )
            else:
                send_text(wa_id, "Please rate between 1 and 5 🌟.")
        except ValueError:
            send_text(wa_id, "Please send a number between 1 and 5 for rating 🌟.")
        return

# -------------------------------------------------------------------
# Hybrid AI + Smart consult suggestion
# -------------------------------------------------------------------
# Topics where a lawyer is often needed
CONSULT_KEYWORDS = [
    "fir", "zero fir", "e-fir", "efir",
    "police", "complaint",
    "domestic violence", "violence", "harassment",
    "theft", "stolen", "robbery",
    "dowry", "498a",
    "custody", "divorce", "maintenance",
    "property", "sale deed", "agreement", "possession",
    "fraud", "cheated", "scam",
    "arrest", "bail", "charge sheet",
    "lawyer", "advocate", "legal notice",
]

# Direct “yes I want a lawyer” words
YES_WORDS = {
    "yes", "y", "ok", "okay", "sure",
    "book", "book now", "book call",
    "need lawyer", "want lawyer", "talk to lawyer",
    "speak to lawyer", "consult now", "help me",
}

NO_WORDS = {
    "no", "not now", "later", "dont want", "don't want", "no thanks",
}

# Strong explicit booking triggers (user text)
BOOK_KEYWORDS = [
    "book consultation",
    "book consult",
    "book call",
    "book lawyer",
    "lawyer call",
    "call lawyer",
    "talk to a lawyer",
    "talk to lawyer",
    "speak to a lawyer",
    "speak to lawyer",
    "need a lawyer",
    "need lawyer",
    "want a lawyer",
    "want lawyer",
    "book appointment",
    "legal consultation",
]

def maybe_suggest_consult(db, user: User, wa_id: str, text: str):
    """
    After giving AI answer, check if we should push consult offer.
    Triggers only when in NORMAL state and message contains problem keywords.
    """
    lower = (text or "").lower()
    if user.state != NORMAL:
        return

    if any(word in lower for word in CONSULT_KEYWORDS):
        save_state(db, user, SUGGEST_CONSULT)
        send_buttons(
            wa_id,
            "Your issue looks important. I can connect you to a qualified lawyer on call for *₹499*.\n\n"
            "Would you like to book a consultation?",
            [
                {"id": "book_consult_now", "title": "Yes — Book Call"},
                {"id": "consult_later", "title": "Not now"},
            ],
        )

# -------------------------------------------------------------------
# Flask routes
# -------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return "NyaySetu backend is running.", 200

# --- Webhook verification (GET) ---
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified successfully.")
        return challenge, 200

    logger.warning("Webhook verification failed.")
    return "Verification failed", 403

# --- Main webhook (POST) ---
@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(force=True, silent=True) or {}
    logger.info(f"INCOMING WHATSAPP PAYLOAD: {json.dumps(payload)}")

    # Standard WhatsApp structure
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
    except (KeyError, IndexError):
        logger.error("Malformed payload")
        return jsonify({"status": "ignored"}), 200

    # Ignore pure status updates (no messages)
    messages = value.get("messages")
    if not messages:
        logger.info("No user message — system event ignored")
        return jsonify({"status": "ignored"}), 200

    message = messages[0]
    wa_id = value["contacts"][0]["wa_id"]

    db = get_db_session()
    try:
        user = get_or_create_user(db, wa_id)

        msg_type = message.get("type")
        text_body = ""
        interactive_id = None

        if msg_type == "text":
            text_body = message["text"]["body"]
        elif msg_type == "interactive":
            itype = message["interactive"]["type"]
            if itype == "button_reply":
                interactive_id = message["interactive"]["button_reply"]["id"]
                text_body = interactive_id
            elif itype == "list_reply":
                interactive_id = message["interactive"]["list_reply"]["id"]
                text_body = interactive_id
        else:
            send_text(
                wa_id,
                "Sorry, I currently support text and simple button/list replies only."
            )
            return jsonify({"status": "ok"}), 200

        logger.info(
            f"Parsed text_body='{text_body}', "
            f"interactive_id='{interactive_id}', state={user.state}"
        )

        lower_text = (text_body or "").lower()

        # 1) Language change buttons
        if interactive_id and interactive_id.startswith("lang_"):
            if handle_language_change(db, user, wa_id, interactive_id):
                return jsonify({"status": "ok"}), 200

        # 2) Consultation button from suggestion
        if interactive_id == "book_consult_now":
            start_booking_flow(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        if interactive_id == "consult_later":
            save_state(db, user, NORMAL)
            send_text(
                wa_id,
                "No problem 👍 You can type *Book Consultation* anytime to speak with a lawyer."
            )
            return jsonify({"status": "ok"}), 200

        # 3) Explicit booking keywords in plain text (strong intent)
        if user.state in [NORMAL, SUGGEST_CONSULT] and any(
            kw in lower_text for kw in BOOK_KEYWORDS
        ):
            start_booking_flow(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        # 4) If we are in booking states, route to booking flow
        if user.state in {
            ASK_NAME,
            ASK_CITY,
            ASK_CATEGORY,
            ASK_DATE,
            ASK_SLOT,
            WAITING_PAYMENT,
            ASK_RATING,
        }:
            handle_booking_flow(db, user, wa_id, text_body, interactive_id)
            return jsonify({"status": "ok"}), 200

        # 5) If we are in SUGGEST_CONSULT and user replies yes/no in text
        if user.state == SUGGEST_CONSULT:
            if lower_text in YES_WORDS:
                start_booking_flow(db, user, wa_id)
                return jsonify({"status": "ok"}), 200
            if lower_text in NO_WORDS:
                save_state(db, user, NORMAL)
                send_text(
                    wa_id,
                    "Sure, we can continue chatting. Ask me anything related to law."
                )
                return jsonify({"status": "ok"}), 200

        # 6) Normal AI chat + smart consult suggestion
        send_typing_on(wa_id)
        reply = ai_reply(text_body, user)
        send_typing_off(wa_id)

        send_text(wa_id, reply)

        # After AI reply, maybe suggest consult
        maybe_suggest_consult(db, user, wa_id, text_body)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error("Error:", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# -------------------------------------------------------------------
# DB migrations at startup
# -------------------------------------------------------------------
with app.app_context():
    try:
        print("🔧 Running DB migrations...")
        create_all()
        print("✅ DB tables ready.")
    except Exception as e:
        print("⚠️ DB migration failed:", e)

# -------------------------------------------------------------------
if __name__ == "__main__":
    # For local testing; Render uses gunicorn
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
