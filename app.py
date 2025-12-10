# app.py
import os
import json
import logging
import random
import string
from datetime import datetime

from flask import Flask, request, jsonify, abort

# DB & Models
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from models import Base, User, Booking

# Services (assume these exist)
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

# Config (expect these env vars)
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "") or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
PAYMENT_WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", "")
PAY_BASE_URL = os.getenv("PAY_BASE_URL", "https://pay.nyaysetu.in")

# DB setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nyaysetu.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# Flask & logging
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("nyaysetu")

# Conversation states
NORMAL = "NORMAL"
SUGGEST_CONSULT = "SUGGEST_CONSULT"
ASK_NAME = "ASK_NAME"
ASK_CITY = "ASK_CITY"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"
ASK_RATING = "ASK_RATING"

def create_all():
    Base.metadata.create_all(bind=engine)

# helper: case id
def generate_case_id(length=6):
    suffix = "".join(random.choices(string.hexdigits.upper(), k=length))
    return f"NS-{suffix}"

# get or create user
def get_or_create_user(db, wa_id: str):
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

# language change
def handle_language_change(db, user: User, wa_id: str, msg_id: str) -> bool:
    language_map = {
        "lang_en": "English",
        "lang_hinglish": "Hinglish",
        "lang_mar": "Marathi",
    }
    if msg_id not in language_map:
        return False
    user.language = language_map[msg_id]
    save_state(db, user, NORMAL)
    send_text(wa_id, f"Language updated to *{user.language}*.\n\nPlease type your legal issue.")
    return True

# booking flow helpers
def start_booking_flow(db, user: User, wa_id: str):
    save_state(db, user, ASK_NAME)
    send_text(wa_id, "Great! Let's schedule your legal consultation call (₹499).\n\nFirst, please tell me your *full name*.")

def handle_booking_flow(db, user: User, wa_id: str, text: str, interactive_id: str | None):
    t = (text or "").strip()

    # 1) Ask for name
    if user.state == ASK_NAME:
        user.temp_name = t
        db.add(user); db.commit(); db.refresh(user)
        save_state(db, user, ASK_CITY)
        send_text(wa_id, "Thanks! 🙏\nNow please tell me your *city*.")
        return

    # 2) city
    if user.state == ASK_CITY:
        user.temp_city = t
        db.add(user); db.commit(); db.refresh(user)
        save_state(db, user, ASK_CATEGORY)
        send_text(wa_id, "Got it 👍\nPlease choose your *legal issue category* (e.g., FIR, Police, Property, Family, Job, Business, Other).")
        return

    # 3) category
    if user.state == ASK_CATEGORY:
        user.temp_category = t
        db.add(user); db.commit(); db.refresh(user)
        # Send date list
        rows = generate_dates_calendar()
        save_state(db, user, ASK_DATE)
        send_list_picker(
            wa_id,
            header="Select appointment date 👇",
            body="Available Dates",
            rows=rows,
            section_title="Next 7 days"
        )
        return

    # 4) Ask for date
    if user.state == ASK_DATE:
        if interactive_id and interactive_id.startswith("date_"):
            user.temp_date = interactive_id.replace("date_", "", 1)
            db.add(user); db.commit(); db.refresh(user)

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
            send_text(wa_id, "Please select a date from the list I sent. If you didn't receive it, type *Book Consultation* to restart booking.")
        return

    # 5) Ask for slot
    if user.state == ASK_SLOT:
        if interactive_id and interactive_id.startswith("slot_"):
            # store raw code as temp_slot (slot_code without prefix)
            slot_code = interactive_id.replace("slot_", "", 1)
            user.temp_slot = slot_code
            db.add(user); db.commit(); db.refresh(user)

            # read persisted fields
            name = user.temp_name or "Client"
            city = user.temp_city or "NA"
            category = user.temp_category or "General"
            date_str = user.temp_date or ""
            slot_code_readable = slot_code

            # convert to readable
            slot_map = {
                "10_11": "10:00 AM – 11:00 AM",
                "12_1": "12:00 PM – 1:00 PM",
                "3_4": "3:00 PM – 4:00 PM",
                "6_7": "6:00 PM – 7:00 PM",
                "8_9": "8:00 PM – 9:00 PM",
            }
            slot_readable = slot_map.get(slot_code_readable, slot_code_readable)

            # Create booking entry and get a payment link
            booking, payment_link = create_booking_temp(
                db=db,
                user=user,
                name=name,
                city=city,
                category=category,
                date=date_str,
                slot=interactive_id,  # keep full id (create_booking_temp will normalize)
                price=499.0,
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
                f"*Slot:* {slot_readable}\n"
                f"*Fees:* ₹499 (single session only) 🙂\n\n"
                f"Please complete payment using this link:\n{payment_link}"
            )
        else:
            send_text(wa_id, "Please select a time slot from the list I sent. If you didn't receive it, type *Book Consultation* to restart booking.")
        return

    # 6) waiting payment
    if user.state == WAITING_PAYMENT:
        send_text(wa_id, "💳 Your payment link is still active. Once payment is done, our team will confirm your consultation. If lost, type *Book Consultation*.")
        return

    # 7) rating
    if user.state == ASK_RATING:
        try:
            rating_val = int(t)
            if 1 <= rating_val <= 5:
                # For brevity, just thank
                save_state(db, user, NORMAL)
                send_text(wa_id, "🙏 Thank you for your feedback! 🙂")
            else:
                send_text(wa_id, "Please rate between 1 and 5 🌟.")
        except Exception:
            send_text(wa_id, "Please send a number between 1 and 5 for rating 🌟.")
        return

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
    lower = (text or "").lower()
    if user.state != NORMAL:
        return
    if any(word in lower for word in CONSULT_KEYWORDS):
        save_state(db, user, SUGGEST_CONSULT)
        send_buttons(
            wa_id,
            "Your issue looks important. I can connect you to a qualified lawyer on call for *₹499*.\n\nWould you like to book a consultation?",
            [
                {"id": "book_consult_now", "title": "Yes — Book Call"},
                {"id": "consult_later", "title": "Not now"},
            ],
        )

# Flask routes
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
    logger.warning("Webhook verification failed.")
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(force=True, silent=True) or {}
    logger.info(f"INCOMING WHATSAPP PAYLOAD: {json.dumps(payload)}")

    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
    except (KeyError, IndexError):
        logger.error("Malformed payload")
        return jsonify({"status": "ignored"}), 200

    # messages present?
    messages = value.get("messages")
    if not messages:
        logger.info("No user message — system event ignored")
        return jsonify({"status": "ignored"}), 200

    message = messages[0]
    wa_id = value["contacts"][0]["wa_id"]

    db = SessionLocal()
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

        logger.info(f"Parsed text_body='{text_body}', interactive_id='{interactive_id}', state={user.state}")

        # language change
        if interactive_id and interactive_id.startswith("lang_"):
            if handle_language_change(db, user, wa_id, interactive_id):
                return jsonify({"status": "ok"}), 200

        # book now button
        if interactive_id == "book_consult_now":
            start_booking_flow(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        if interactive_id == "consult_later":
            save_state(db, user, NORMAL)
            send_text(wa_id, "No problem 👍 You can type *Book Consultation* anytime to speak with a lawyer.")
            return jsonify({"status": "ok"}), 200

        # explicit booking keywords
        lower_text = (text_body or "").lower()
        if user.state in [NORMAL, SUGGEST_CONSULT] and any(kw in lower_text for kw in ["book", "consultation", "lawyer call", "appointment"]):
            start_booking_flow(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        # if booking states
        if user.state in {ASK_NAME, ASK_CITY, ASK_CATEGORY, ASK_DATE, ASK_SLOT, WAITING_PAYMENT, ASK_RATING}:
            handle_booking_flow(db, user, wa_id, text_body, interactive_id)
            return jsonify({"status": "ok"}), 200

        # SUGGEST_CONSULT text yes/no
        if user.state == SUGGEST_CONSULT:
            if lower_text in YES_WORDS:
                start_booking_flow(db, user, wa_id)
                return jsonify({"status": "ok"}), 200
            if lower_text in NO_WORDS:
                save_state(db, user, NORMAL)
                send_text(wa_id, "Sure, we can continue chatting. Ask me anything related to law.")
                return jsonify({"status": "ok"}), 200

        # Normal AI chat
        send_typing_on(wa_id)
        reply = ai_reply(text_body, user)
        send_typing_off(wa_id)
        send_text(wa_id, reply)

        maybe_suggest_consult(db, user, wa_id, text_body)
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error("Error:", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# Payment webhook endpoint
# This endpoint is intended to be called by your payment provider (or by admin for testing).
@app.route("/payment/webhook", methods=["POST"])
def payment_webhook():
    """
    Expected JSON (example):
    {
      "booking_ref": "BK-XXXX",
      "status": "PAID",
      "payment_id": "razorpay_order_xxx",
      "secret": "webhook_secret"   # we validate against PAYMENT_WEBHOOK_SECRET
    }
    """
    payload = request.get_json(force=True, silent=True) or {}
    logger.info(f"PAYMENT WEBHOOK: {json.dumps(payload)}")
    secret = payload.get("secret")
    if PAYMENT_WEBHOOK_SECRET and secret != PAYMENT_WEBHOOK_SECRET:
        logger.warning("Payment webhook secret mismatch")
        return jsonify({"error": "unauthorized"}), 403

    booking_ref = payload.get("booking_ref")
    status = payload.get("status")
    payment_id = payload.get("payment_id")

    if not booking_ref:
        return jsonify({"error": "missing booking_ref"}), 400

    db = SessionLocal()
    try:
        if status and status.upper() in ("PAID", "SUCCESS"):
            booking = confirm_booking_after_payment(db, booking_ref, external_payment_id=payment_id)
            if booking:
                # Optionally notify user
                send_text(booking.whatsapp_id, f"✅ Payment received. Your booking {booking.booking_ref} is confirmed. 🙂")
                return jsonify({"status": "ok", "booking_ref": booking_ref}), 200
        # others: just record
        return jsonify({"status": "ignored"}), 200
    except Exception as e:
        logger.exception("Payment webhook error")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# DB init at startup
with app.app_context():
    try:
        logger.info("🔧 Running DB migrations...")
        create_all()
        logger.info("✅ DB tables ready.")
    except Exception as e:
        logger.exception("DB migrations failed")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
