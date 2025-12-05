import os
import time
import uuid
import logging
from flask import Flask, request
from db import SessionLocal
from models import User, Conversation, Booking
from services.whatsapp_service import send_text, send_buttons, send_typing_on, send_typing_off
from services.openai_service import detect_language, detect_category, generate_legal_reply
from services.booking_service import create_booking_for_user
from config import WHATSAPP_VERIFY_TOKEN, MAX_FREE_MESSAGES, TYPING_DELAY_SECONDS

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TYPING_DELAY = TYPING_DELAY_SECONDS

CATEGORY_PRICE = {
    "police": 199, "property": 349, "money": 299,
    "family": 249, "business": 399, "other": 199
}

LANGUAGE_BUTTONS = [
    {"id": "lang_en", "title": "English"},
    {"id": "lang_hinglish", "title": "Hinglish"},
    {"id": "lang_mar", "title": "मराठी (Marathi)"}
]

BOOKING_KEYWORDS = [
    "speak", "book", "lawyer", "call", "consult", "talk", "advocate",
    "yes", "ok", "okey", "haan"
]

pending_booking_state = {}
def generate_case_id():
    return f"NS-{uuid.uuid4().hex[:6].upper()}"

def get_or_create_user(wa):
    db = SessionLocal()
    user = db.query(User).filter_by(whatsapp_id=wa).first()
    if user:
        return user
    user = User(whatsapp_id=wa, case_id=generate_case_id(), language="English")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def log_msg(wa, direction, text):
    db = SessionLocal()
    db.add(Conversation(user_whatsapp_id=wa, direction=direction, text=text))
    db.commit()

def count_real_questions(wa):
    ignore = {"hi", "hello", "hey", "book", "call", "consult", "speak to lawyer"}
    db = SessionLocal()
    rows = db.query(Conversation).filter_by(user_whatsapp_id=wa, direction="user").all()
    return sum(1 for r in rows if (r.text or "").lower().strip() not in ignore)
@app.get("/webhook")
def verify():
    if request.args.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Invalid", 403
@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    value = payload["entry"][0]["changes"][0]["value"]
    msg = value.get("messages", [{}])[0]
    wa = value.get("contacts", [{}])[0].get("wa_id")

    text = ""
    if msg.get("type") == "interactive":
        i = msg["interactive"]
        text = i.get("button_reply", {}).get("id") or i.get("list_reply", {}).get("id", "")
    elif msg.get("type") == "text":
        text = msg["text"].get("body", "")
    text = (text or "").strip()

    user = get_or_create_user(wa)
    log_msg(wa, "user", text)
    if count_real_questions(wa) == 0 or text.lower() in {"hi", "hello", "hey"}:
        send_text(wa, f"👋 Welcome to NyaySetu! Your Case ID: {user.case_id}")
        send_buttons(wa, "Select your preferred language 👇", LANGUAGE_BUTTONS)
        return {"status": "welcome"}

    if text.startswith("lang_"):
        user.language = {"lang_en": "English", "lang_hinglish": "Hinglish", "lang_mar": "Marathi"}[text]
        SessionLocal().commit()
        send_text(wa, f"Language updated to {user.language}. Please type your legal issue.")
        return {"status": "language_set"}
    # User already approved booking — waiting for preferred time
    state = pending_booking_state.get(wa)
    if state and state["step"] == "await_time":
        preferred_time = text
        fee = state["fee"]
        booking = create_booking_for_user(wa, preferred_time, fee)
        send_text(wa, f"💳 Payment link to confirm consultation:\n{booking.payment_link}")
        pending_booking_state.pop(wa, None)
        return {"status": "payment_sent"}

    # User expresses intention to speak with lawyer
    if any(k in text.lower() for k in BOOKING_KEYWORDS):
        cat = detect_category(text)
        fee = CATEGORY_PRICE.get(cat, 199)
        pending_booking_state[wa] = {"step": "await_time", "fee": fee}
        send_text(wa, "🕒 Sure — what time should I schedule your call?")
        return {"status": "await_time"}

    # FREE LIMIT reached — offer only once
    if count_real_questions(wa) >= MAX_FREE_MESSAGES:
        cat = detect_category(text)
        fee = CATEGORY_PRICE.get(cat, 199)
        pending_booking_state[wa] = {"step": "await_time", "fee": fee}
        send_text(
            wa,
            f"📞 Your free limit is completed.\n"
            f"A lawyer can guide you directly on call.\n"
            f"Price: ₹{fee}\n⏳ What time should I schedule the call?"
        )
        return {"status": "offer_once"}
    # AI reply (smooth typing effect, no "One moment...")
    send_typing_on(wa)
    time.sleep(TYPING_DELAY)
    reply = generate_legal_reply(text, user.language, detect_category(text))
    send_typing_off(wa)
    send_text(wa, reply)
    log_msg(wa, "bot", reply)

    return {"status": "answered"}
@app.get("/")
def index():
    return "NyaySetu Bot Running ✔", 200
