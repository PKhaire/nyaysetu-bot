# app.py
import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from db import create_all, SessionLocal

from models import User, Booking, Rating
from config import (
    WHATSAPP_VERIFY_TOKEN,
    BOOKING_PRICE,
    ADMIN_TOKEN,
    BOOKING_CUTOFF_HOURS,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
)
from services.whatsapp_service import (
    send_text, send_buttons, send_typing_on, send_typing_off, send_list_picker
)
from services.openai_service import ai_reply
from services.booking_service import (
    generate_dates_calendar,
    generate_slots_calendar,
    create_booking_temp,
    confirm_booking_after_payment,
    SLOT_MAP,
    load_states
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
with app.app_context():
    try:
        print("🔧 Running DB migrations...")
        create_all()
        print("✅ DB tables ready.")
    except Exception as e:
        print("⚠️ DB migration failed:", e)
# Conversation states
NORMAL = "NORMAL"
SUGGEST_CONSULT = "SUGGEST_CONSULT"
ASK_NAME = "ASK_NAME"
ASK_CITY = "ASK_CITY"
ASK_STATE = "ASK_STATE"
ASK_DISTRICT = "ASK_DISTRICT"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"
ASK_RATING = "ASK_RATING"

def get_db_session():
    return SessionLocal()

def generate_case_id(length=6):
    import random, string
    suffix = "".join(random.choices(string.hexdigits.upper(), k=length))
    return f"NS-{suffix}"

def get_or_create_user(db, wa_id: str) -> User:
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if not user:
        user = User(
            whatsapp_id=wa_id,
            case_id=generate_case_id(),
            language="English",
            query_count=0,
            state=NORMAL,
            created_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user {wa_id} with case_id={user.case_id}")
    return user

def save_state(db, user: User, state: str):
    user.state = state
    db.add(user)
    db.commit()

CONSULT_KEYWORDS = [
    "fir", "police", "zero fir", "e-fir", "efir",
    "domestic", "violence", "harassment",
    "theft", "stolen", "robbery",
    "dowry", "498a",
    "custody", "divorce", "maintenance",
    "property", "sale deed", "agreement", "possession",
    "fraud", "cheated", "scam",
    "arrest", "bail", "charge sheet",
]

YES_WORDS = {"yes", "y", "ok", "okay", "sure", "book", "book now", "book call", "need lawyer", "want lawyer", "talk to lawyer", "consult now", "help me"}
NO_WORDS = {"no", "not now", "later", "dont want", "don't want", "no thanks"}

def maybe_suggest_consult(db, user: User, wa_id: str, text: str):
    lower = text.lower()
    if user.state != NORMAL:
        return
    if any(word in lower for word in CONSULT_KEYWORDS):
        save_state(db, user, SUGGEST_CONSULT)
        send_buttons(
            wa_id,
            "Your issue looks important. I can connect you to a qualified lawyer on call for a single session. Would you like to book?",
            [
                {"id": "book_consult_now", "title": "Yes — Book Call"},
                {"id": "consult_later", "title": "Not now"},
            ],
        )

@app.route("/", methods=["GET"])
def index():
    return "NyaySetu backend is running.", 200

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified successfully.")
        return challenge, 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(force=True, silent=True) or {}
    logger.info("INCOMING WHATSAPP PAYLOAD: %s", json.dumps(payload))
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
    except Exception:
        logger.error("Malformed payload")
        return jsonify({"status": "ignored"}), 200

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
            send_text(wa_id, "Sorry, I currently support text and simple button/list replies only.")
            return jsonify({"status": "ok"}), 200

        logger.info("Parsed text_body='%s', interactive_id='%s', state=%s", text_body, interactive_id, user.state)

        # Language
        if interactive_id and interactive_id.startswith("lang_"):
            lang_map = {"lang_en":"English","lang_hinglish":"Hinglish","lang_mar":"Marathi"}
            if interactive_id in lang_map:
                user.language = lang_map[interactive_id]
                save_state(db, user, NORMAL)
                send_text(wa_id, f"Language updated to *{user.language}*.\n\nPlease type your legal issue.")
                return jsonify({"status":"ok"}), 200

        # suggestion buttons
        if interactive_id == "book_consult_now":
            save_state(db, user, ASK_NAME)
            send_text(wa_id, "Great! Let's schedule your legal consultation call.\n\nFirst, please tell me your *full name*.")
            return jsonify({"status":"ok"}), 200
        if interactive_id == "consult_later":
            save_state(db, user, NORMAL)
            send_text(wa_id, "No problem 👍 You can type *Book Consultation* anytime.")
            return jsonify({"status":"ok"}), 200

        lower_text = (text_body or "").lower()
        if user.state in [NORMAL, SUGGEST_CONSULT] and any(kw in lower_text for kw in ["book", "consultation", "lawyer call", "appointment"]):
            save_state(db, user, ASK_NAME)
            send_text(wa_id, "Great! Let's schedule your legal consultation call.\n\nFirst, please tell me your *full name*.")
            return jsonify({"status":"ok"}), 200

        # Booking flow
        if user.state == ASK_NAME:
            user.name = text_body.strip()
            db.add(user); db.commit()
            save_state(db, user, ASK_STATE)
            send_text(wa_id, "Thanks! 🙏\nWhich *state* are you in? (e.g., Maharashtra)")
            return jsonify({"status":"ok"}), 200

        if user.state == ASK_STATE:
            # Accept free text state and offer district list
            state_text = text_body.strip()
            states = load_states()
            matched = None
            for s in states:
                if s.lower() == state_text.lower() or state_text.lower() in s.lower():
                    matched = s; break
            if not matched:
                # try fuzzy contains
                for s in states:
                    if state_text.lower() in s.lower():
                        matched = s; break
            if not matched:
                # fallback: ask again with suggestions
                sample = list(states.keys())[:6]
                send_text(wa_id, f"Couldn't detect state. Example states: {', '.join(sample)}. Please type the full state name.")
                return jsonify({"status":"ok"}), 200
            user.city = None  # clear city for district flow
            user.category = None
            user.temp_date = None
            user.temp_slot = None
            user.state = ASK_DISTRICT
            db.add(user); db.commit()
            # prepare district list
            districts = states.get(matched, [])[:20]
            rows = [{"id": f"district_{matched}_{d}", "title": d, "description": ""} for d in districts]
            send_list_picker(wa_id, header=f"Select district in {matched}", body="Choose district", rows=rows, section_title=f"{matched} districts")
            return jsonify({"status":"ok"}), 200

        if user.state == ASK_DISTRICT:
            if interactive_id and interactive_id.startswith("district_"):
                # id like district_{State}_{District}
                parts = interactive_id.split("_", 2)
                if len(parts) >= 3:
                    district = parts[2]
                else:
                    district = text_body
                user.city = district
                db.add(user); db.commit()
                save_state(db, user, ASK_CATEGORY)
                send_text(wa_id, "Got it 👍\nPlease choose your *legal issue category* (FIR, Police, Property, Family, Job, Business, Other).")
                return jsonify({"status":"ok"}), 200
            else:
                # free text fallback
                user.city = text_body.strip()
                db.add(user); db.commit()
                save_state(db, user, ASK_CATEGORY)
                send_text(wa_id, "Got it 👍\nPlease choose your *legal issue category* (FIR, Police, Property, Family, Job, Business, Other).")
                return jsonify({"status":"ok"}), 200

        if user.state == ASK_CATEGORY:
            user.category = text_body.strip()
            db.add(user); db.commit()
            rows = generate_dates_calendar()
            save_state(db, user, ASK_DATE)
            send_list_picker(wa_id, header="Select appointment date 👇", body="Available Dates", rows=rows, section_title="Next 7 days")
            return jsonify({"status":"ok"}), 200

        if user.state == ASK_DATE:
            if interactive_id and interactive_id.startswith("date_"):
                user.temp_date = interactive_id.replace("date_", "", 1)
                db.add(user); db.commit()
                rows = generate_slots_calendar(user.temp_date)
                save_state(db, user, ASK_SLOT)
                send_list_picker(wa_id, header=f"Select time slot for {user.temp_date}", body="Available time slots (IST)", rows=rows, section_title="Time Slots")
            else:
                send_text(wa_id, "Please select a date from the list I sent. If you didn't receive it, type *Book Consultation* to restart booking.")
            return jsonify({"status":"ok"}), 200

        if user.state == ASK_SLOT:
            if interactive_id and interactive_id.startswith("slot_"):
                user.temp_slot = interactive_id.replace("slot_", "", 1)
                db.add(user); db.commit()

                name = user.name or "Client"
                city = user.city or "NA"
                category = user.category or "General"
                date = user.temp_date
                slot_code = user.temp_slot

                booking, result = create_booking_temp(db, user, name, city, category, date, slot_code)
                if not booking:
                    send_text(wa_id, f"⚠️ {result}")
                    return jsonify({"status":"ok"}), 200

                payment_link = result
                user.last_payment_link = payment_link
                save_state(db, user, WAITING_PAYMENT)

                send_text(wa_id,
                          "✅ *Your appointment details:*\n"
                          f"*Name:* {name}\n"
                          f"*City:* {city}\n"
                          f"*Category:* {category}\n"
                          f"*Date:* {date}\n"
                          f"*Slot:* {SLOT_MAP.get(slot_code, slot_code)}\n"
                          f"*Fees:* ₹{BOOKING_PRICE} (one-time session) 🙂\n\n"
                          f"Please complete payment using this link:\n{payment_link}"
                          )
            else:
                send_text(wa_id, "Please select a time slot from the list I sent. If you didn't receive it, type *Book Consultation* to restart booking.")
            return jsonify({"status":"ok"}), 200

        if user.state == WAITING_PAYMENT:
            send_text(wa_id, f"💳 Your payment link is still active: {user.last_payment_link or 'not found'}")
            return jsonify({"status":"ok"}), 200

        if user.state == SUGGEST_CONSULT:
            if lower_text in YES_WORDS:
                save_state(db, user, ASK_NAME)
                send_text(wa_id, "Great — first, please tell your full name.")
                return jsonify({"status":"ok"}), 200
            if lower_text in NO_WORDS:
                save_state(db, user, NORMAL)
                send_text(wa_id, "Sure. You can type anything to continue chatting.")
                return jsonify({"status":"ok"}), 200

        # Normal chat
        send_typing_on(wa_id)
        reply = ai_reply(text_body, user)
        send_typing_off(wa_id)
        send_text(wa_id, reply)
        maybe_suggest_consult(db, user, wa_id, text_body)
        return jsonify({"status":"ok"}), 200

    except Exception as e:
        logger.exception("Error handling webhook")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# Payment webhook: confirm booking after payment provider posts back token
@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    data = request.get_json(force=True, silent=True) or {}
    token = data.get("payment_token") or data.get("token") or ""
    if not token:
        return jsonify({"error": "missing token"}), 400

    db = get_db_session()
    try:
        booking, status = confirm_booking_after_payment(db, token)
        if not booking:
            return jsonify({"error": status}), 404
        send_text(booking.whatsapp_id, f"✅ Your booking for {booking.date} {booking.slot_readable} is confirmed. See you then 🙂")
        return jsonify({"status": "confirmed", "booking_id": booking.id}), 200
    finally:
        db.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
