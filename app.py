import os
import time
import uuid
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from db import Base, engine, SessionLocal
from models import User, Conversation, Booking
from services.whatsapp_service import send_text, send_buttons, send_typing_on, send_typing_off
from services.openai_service import detect_language, detect_category, generate_legal_reply
from services.booking_service import create_booking_for_user
from config import WHATSAPP_VERIFY_TOKEN, MAX_FREE_MESSAGES, TYPING_DELAY_SECONDS, ADMIN_PASSWORD

# ---------------- APP INIT ----------------
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
Base.metadata.create_all(bind=engine)
db = SessionLocal()

TYPING_DELAY = TYPING_DELAY_SECONDS

# --------------- DYNAMIC PRICING ---------------
CATEGORY_PRICE = {
    "police": 199,
    "property": 349,
    "money": 299,
    "family": 249,
    "business": 399,
    "other": 199,
}

# --------------- SMART DISCOUNTS ---------------
DISCOUNT_CODES = {"FAST10": 0.10, "HELP50": 50}
AFFORDABILITY_WORDS = {
    "discount", "too expensive", "costly", "less price",
    "can't afford", "bohot mehenga", "kharcha jast", "mehenga",
}

LANGUAGE_BUTTONS = [
    {"id": "lang_en", "title": "English"},
    {"id": "lang_hinglish", "title": "Hinglish"},
    {"id": "lang_mar", "title": "मराठी (Marathi)"},
]

pending_booking_state = {}

# ---------------- HELPERS ----------------
def generate_case_id():
    return f"NS-{uuid.uuid4().hex[:6].upper()}"

def get_or_create_user(wa):
    user = db.query(User).filter_by(whatsapp_id=wa).first()
    if user:
        return user
    user = User(whatsapp_id=wa, case_id=generate_case_id(), language="English")
    db.add(user); db.commit(); db.refresh(user)
    return user

def log_msg(wa, direction, text):
    db.add(Conversation(user_whatsapp_id=wa, direction=direction, text=text)); db.commit()

# ---------------- FREE LIMIT ----------------
def count_real_questions(wa):
    msgs = db.query(Conversation).filter_by(user_whatsapp_id=wa, direction="user").all()
    ignore = {"hi", "hello", "hey", "namaste", "book", "call", "consult"}
    total = 0
    for m in msgs:
        t = (m.text or "").lower().strip()
        if not t or t in ignore:
            continue
        total += 1
    return total

# ---------------- WEBHOOK VERIFY ----------------
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Forbidden", 403

# ---------------- MAIN WHATSAPP WEBHOOK ----------------
@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    logging.info(f"Incoming payload: {payload}")

    value = payload["entry"][0]["changes"][0]["value"]
    if "statuses" in value and not value.get("messages"):  # ignore delivery/read
        return jsonify({"status": "ok"}), 200

    msg = value.get("messages", [{}])[0]
    wa_id = value.get("contacts", [{}])[0].get("wa_id")
    text = ""
    if msg.get("type") == "interactive":
        i = msg.get("interactive")
        if i.get("type") == "button_reply":
            text = i["button_reply"]["id"]
        elif i.get("type") == "list_reply":
            text = i["list_reply"]["id"]
    elif msg.get("type") == "text":
        text = msg["text"].get("body", "")

    text = text.strip()
    user = get_or_create_user(wa_id)
    log_msg(wa_id, "user", text)

    # New user or greeting
    if count_real_questions(wa_id) == 0 or text.lower() in {"hi", "hello", "hey", "start"}:
        send_text(wa_id, f"👋 Welcome to NyaySetu! Your Case ID: {user.case_id}")
        send_buttons(wa_id, "Select your preferred language 👇", LANGUAGE_BUTTONS)
        return jsonify({"status": "welcome"}), 200

    # ---------------- LANGUAGE SELECTION ----------------
    if text.startswith("lang_"):
        new_lang = {"lang_en": "English", "lang_hinglish": "Hinglish", "lang_mar": "Marathi"}[text]
        user.language = new_lang; db.commit()
        send_text(wa_id, f"Language updated to {new_lang}. Please type your legal issue.")
        return jsonify({"status": "language"}), 200

    # ---------------- BOOKING FLOW ----------------
    state = pending_booking_state.get(wa_id)
    if state:
        fee = state.get("fee")
        coupon = state.get("coupon")
        # Time selection
        if state["step"] == "await_time":
            preferred_time = text
            final_fee = max(fee - 50, 99) if coupon == "HELP50" else fee
            booking = create_booking_for_user(wa_id, preferred_time, final_fee, coupon)
            pending_booking_state.pop(wa_id, None)
            send_text(wa_id, f"💳 Please complete payment to confirm:\n{booking.payment_link}")
            return jsonify({"status": "payment_sent"}), 200

    # ---------------- DISCOUNT TRIGGER ----------------
    if any(w in text.lower() for w in AFFORDABILITY_WORDS):
        category = detect_category(text)
        fee = CATEGORY_PRICE.get(category, 199)
        pending_booking_state[wa_id] = {"step": "await_time", "fee": fee, "coupon": "HELP50"}
        send_text(wa_id, f"💙 I can offer a ₹50 discount for support.\nCoupon: HELP50\nShall I proceed?")
        return jsonify({"status": "coupon_offer"}), 200

    # ---------------- LIMIT CHECK ----------------
    if count_real_questions(wa_id) >= MAX_FREE_MESSAGES:
        category = detect_category(text)
        fee = CATEGORY_PRICE.get(category, 199)
        send_text(wa_id, "You’ve reached your free answer limit 🙏")
        pending_booking_state[wa_id] = {"step": "await_time", "fee": fee}
        send_text(wa_id, f"📞 Talk to a lawyer — ₹{fee}. Shall I book a call?")
        return jsonify({"status": "limit_reached"}), 200

    # ---------------- LEGAL AI REPLY ----------------
    send_text(wa_id, "⏳ One moment…")
    send_typing_on(wa_id); time.sleep(TYPING_DELAY)

    lang = user.language
    category = detect_category(text)
    reply = generate_legal_reply(text, lang, category)

    send_typing_off(wa_id)
    send_text(wa_id, reply)
    log_msg(wa_id, "bot", reply)

    # Booking prompt after legal answer (conversion)
    fee = CATEGORY_PRICE.get(category, 199)
    send_text(wa_id, f"📞 Want to speak with a lawyer? Price: ₹{fee}")
    pending_booking_state[wa_id] = {"step": "await_time", "fee": fee}

    return jsonify({"status": "answered"}), 200


# ---------------- PAYMENT WEBHOOK (AUTO-CONFIRM) ----------------
@app.route("/payment/webhook", methods=["POST"])
def payment_webhook():
    data = request.get_json(silent=True) or {}
    wa = data.get("case"); status = data.get("status")
    if not wa or status not in {"paid", "success", "captured"}:
        return jsonify({"status": "ignored"}), 200
    booking = db.query(Booking).filter_by(user_whatsapp_id=wa).order_by(Booking.created_at.desc()).first()
    if booking:
        booking.confirmed = True; db.commit()
        send_text(wa, "🎉 Payment received! Your consultation is confirmed.\nThe lawyer will call you at the scheduled time.")
    return jsonify({"status": "ok"}), 200


# ---------------- ADMIN PANEL ----------------
@app.route("/", methods=["GET"])
def index():
    return "NyaySetu WhatsApp Bot — OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
