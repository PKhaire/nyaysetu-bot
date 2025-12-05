import logging
import time
import uuid

from flask import Flask, request, jsonify

from config import (
    WHATSAPP_VERIFY_TOKEN,
    MAX_FREE_MESSAGES,
    ADMIN_TOKEN,
    TYPING_DELAY_SECONDS,
)
from db import SessionLocal
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

# -----------------------------------------------------------------------------
# Flask & logging setup
# -----------------------------------------------------------------------------
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TYPING_DELAY = TYPING_DELAY_SECONDS
CONSULTATION_FEE = 499  # fixed price for everyone (your requirement)

# In-memory conversation / booking state
pending_booking_state = {}   # wa_id -> {"step": "confirm"}
pending_rating_state = {}    # wa_id -> booking_id
followup_sent = set()        # wa_ids where upsell already shown

# Language selection buttons
LANGUAGE_BUTTONS = [
    {"id": "lang_en", "title": "English"},
    {"id": "lang_hinglish", "title": "Hinglish"},
    {"id": "lang_mar", "title": "मराठी (Marathi)"},
]

# Keywords that trigger booking intent
BOOKING_KEYWORDS = [
    "speak to lawyer",
    "speak with lawyer",
    "talk to lawyer",
    "consult lawyer",
    "book call",
    "book consultation",
    "lawyer call",
    "advocate",
    "call lawyer",
]

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def generate_case_id():
    return f"NS-{uuid.uuid4().hex[:6].upper()}"


def get_or_create_user(wa_id):
    """
    Returns (user, db_session) with the session LEFT OPEN.
    Caller is responsible for db_session.close().
    """
    db = SessionLocal()
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if not user:
        user = User(
            whatsapp_id=wa_id,
            case_id=generate_case_id(),
            language=None,
            query_count=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user, db


def log_message(db, wa_id, direction, text):
    conv = Conversation(user_whatsapp_id=wa_id, direction=direction, text=text)
    db.add(conv)
    db.commit()


def count_real_questions(db, wa_id):
    ignore = {"hi", "hello", "hey", "book", "call", "consult", "speak to lawyer"}
    rows = (
        db.query(Conversation)
        .filter_by(user_whatsapp_id=wa_id, direction="user")
        .all()
    )
    return sum(1 for r in rows if (r.text or "").lower().strip() not in ignore)


def count_bot_replies(db, wa_id):
    rows = (
        db.query(Conversation)
        .filter_by(user_whatsapp_id=wa_id, direction="bot")
        .all()
    )
    return len(rows)


# -----------------------------------------------------------------------------
# Admin endpoint: mark booking completed -> trigger rating
# -----------------------------------------------------------------------------
@app.post("/booking/mark_completed")
def mark_booking_completed():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    booking_id = data.get("booking_id")
    if not booking_id:
        return jsonify({"error": "booking_id required"}), 400

    db = SessionLocal()
    booking = db.query(Booking).filter_by(id=booking_id).first()
    if not booking:
        db.close()
        return jsonify({"error": "Not found"}), 404

    booking.status = "completed"
    db.commit()
    wa_id = booking.user_whatsapp_id
    pending_rating_state[wa_id] = booking.id
    db.close()

    send_text(
        wa_id,
        "Thank you for using NyaySetu 🙏\n"
        "Please rate your consultation:\n\n"
        "1️⃣ Very helpful\n"
        "2️⃣ Good\n"
        "3️⃣ Average\n"
        "4️⃣ Not helpful",
    )
    return jsonify({"status": "rating_requested"}), 200


# -----------------------------------------------------------------------------
# WhatsApp webhook verification
# -----------------------------------------------------------------------------
@app.get("/webhook")
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == WHATSAPP_VERIFY_TOKEN:
        return challenge
    return "Invalid verification token", 403


# -----------------------------------------------------------------------------
# Main WhatsApp webhook
# -----------------------------------------------------------------------------
@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    logging.info("INCOMING WHATSAPP PAYLOAD: %s", payload)

    # Safely extract value/message
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
    except Exception:
        return jsonify({"status": "ignored"}), 200

    # Ignore system events (no user messages)
    if "messages" not in value:
        logging.info("No user message — system event ignored")
        return jsonify({"status": "ignored"}), 200

    msg = value["messages"][0]
    wa_id = msg.get("from") or value.get("contacts", [{}])[0].get("wa_id")
    if not wa_id:
        logging.info("No wa_id — ignored")
        return jsonify({"status": "ignored"}), 200

    msg_type = msg.get("type", "")
    # Extract text / button id
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "")
    elif msg_type == "interactive":
        inter = msg.get("interactive", {})
        text = inter.get("button_reply", {}).get("id") or inter.get(
            "list_reply", {}
        ).get("id", "")
    else:
        return jsonify({"status": "unsupported"}), 200

    text = (text or "").strip()
    lower_text = text.lower()

    user, db = get_or_create_user(wa_id)

    try:
        # Log user message
        log_message(db, wa_id, "user", text)

        # ---------------- RATING FLOW ----------------
        if wa_id in pending_rating_state:
            booking_id = pending_rating_state[wa_id]
            if text not in {"1", "2", "3", "4"}:
                send_text(wa_id, "Please reply with 1, 2, 3 or 4.")
                return jsonify({"status": "rating_wait"}), 200

            booking = db.query(Booking).filter_by(id=booking_id).first()
            if booking:
                booking.rating = int(text)
                db.commit()

            pending_rating_state.pop(wa_id, None)

            if text in {"1", "2", "3"}:
                send_text(
                    wa_id,
                    "Thank you for your feedback 🙏\n"
                    "We’re glad to have supported you.",
                )
            else:
                send_text(
                    wa_id,
                    "We’re sorry the experience wasn’t helpful 🙏\n"
                    "You can always book another call and we’ll do our best "
                    "to match you with a more suitable lawyer.",
                )
            return jsonify({"status": "rating_recorded"}), 200

        # ---------------- MAP PLAIN LANGUAGE TO BUTTON IDs (FIX LOOP) ----------
        language_map = {
            "english": "lang_en",
            "hinglish": "lang_hinglish",
            "marathi": "lang_mar",
            "मराठी": "lang_mar",
        }
        if lower_text in language_map:
            text = language_map[lower_text]

        # ---------------- LANGUAGE SELECTION / ONBOARDING ----------------------
        if user.language is None:
            if text.startswith("lang_"):
                selected = {
                    "lang_en": "English",
                    "lang_hinglish": "Hinglish",
                    "lang_mar": "Marathi",
                }.get(text, "English")

                user.language = selected
                db.commit()

                send_text(
                    wa_id,
                    f"Language updated to {selected}. Please type your legal issue.",
                )
                return jsonify({"status": "language_set"}), 200

            # First-time welcome: do NOT loop on every message
            if count_bot_replies(db, wa_id) == 0:
                send_text(
                    wa_id,
                    f"👋 Welcome to NyaySetu! Your Case ID: {user.case_id}",
                )
                send_buttons(
                    wa_id,
                    "Select your preferred language 👇",
                    LANGUAGE_BUTTONS,
                )
                return jsonify({"status": "welcome_sent"}), 200

            # If we reached here, user still hasn't chosen language
            send_buttons(
                wa_id,
                "Please choose your language to continue 👇",
                LANGUAGE_BUTTONS,
            )
            return jsonify({"status": "language_required"}), 200

        # ---------------- BOOKING FLOW ----------------
        booking_state = pending_booking_state.get(wa_id)

        # Step: user is being asked to CONFIRM booking
        if booking_state and booking_state.get("step") == "confirm":
            if lower_text in {"yes", "y", "haan", "ha", "ok", "okay"}:
                preferred_time = "Next available slot (within a few hours)"
                booking = create_booking_for_user(
                    user_whatsapp_id=wa_id,
                    amount=CONSULTATION_FEE,
                    preferred_time=preferred_time,
                )

                send_text(
                    wa_id,
                    "✅ Your consultation booking has been created!\n\n"
                    f"📅 When: {preferred_time}\n"
                    f"💰 Fee: ₹{CONSULTATION_FEE}\n\n"
                    f"Please complete your secure payment here:\n{booking.payment_link}\n\n"
                    "Once payment is done, our team will connect you with a verified lawyer.",
                )
                pending_booking_state.pop(wa_id, None)
                return jsonify({"status": "booking_created"}), 200

            if lower_text in {"no", "n", "na", "cancel"}:
                pending_booking_state.pop(wa_id, None)
                send_text(
                    wa_id,
                    "No problem 👍\nYou can continue asking questions here, "
                    "and book a call any time if you need deeper help.",
                )
                return jsonify({"status": "booking_cancelled"}), 200

            send_text(
                wa_id,
                "Please reply *YES* to confirm your booking or *NO* to cancel.",
            )
            return jsonify({"status": "booking_confirm_prompt"}), 200

        # If user explicitly asks for lawyer (keywords or button)
        if text == "speak_lawyer" or any(k in lower_text for k in BOOKING_KEYWORDS):
            send_text(
                wa_id,
                "📞 A phone consultation with a verified lawyer costs "
                f"*₹{CONSULTATION_FEE}* for up to 20 minutes.\n\n"
                "We’ll schedule your call for the *next available slot* (usually within a few hours).\n"
                "Reply *YES* to confirm the booking or *NO* to cancel.",
            )
            pending_booking_state[wa_id] = {"step": "confirm"}
            return jsonify({"status": "booking_offer"}), 200

        # ---------------- NORMAL AI ASSIST FLOW ----------------
        # increment query count
        user.query_count = (user.query_count or 0) + 1
        db.commit()

        # Decide language for AI answer
        lang = user.language or detect_language(text)
        category = detect_category(text)

        send_typing_on(wa_id)
        time.sleep(TYPING_DELAY)
        send_typing_off(wa_id)

        reply = generate_legal_reply(text, lang, category)
        send_text(wa_id, reply)
        log_message(db, wa_id, "bot", reply)

        # After some questions, softly offer call (only once)
        if (
            user.query_count >= MAX_FREE_MESSAGES
            and wa_id not in followup_sent
        ):
            followup_sent.add(wa_id)
            send_buttons(
                wa_id,
                f"📞 Want to speak with a lawyer for more personalised advice?\n"
                f"Consultation fee: ₹{CONSULTATION_FEE}",
                [
                    {"id": "speak_lawyer", "title": "Yes, book a call"},
                ],
            )

        return jsonify({"status": "replied"}), 200

    finally:
        db.close()


# -----------------------------------------------------------------------------
# Health / root endpoint
# -----------------------------------------------------------------------------
@app.get("/")
def health():
    return jsonify({"status": "ok", "service": "NyaySetu WhatsApp API"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
