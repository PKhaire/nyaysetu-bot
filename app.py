import os
import uuid
import time
import logging
from flask import Flask, request, jsonify

from db import SessionLocal
from models import User, Conversation, Booking
from services.whatsapp_service import send_text, send_buttons, send_typing_on, send_typing_off
from services.openai_service import detect_language, detect_category, generate_legal_reply
from services.booking_service import create_booking_for_user
from config import WHATSAPP_VERIFY_TOKEN, MAX_FREE_MESSAGES, ADMIN_TOKEN, TYPING_DELAY_SECONDS


app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TYPING_DELAY = TYPING_DELAY_SECONDS

CATEGORY_PRICE = {
    "police": 199,
    "property": 349,
    "money": 299,
    "family": 249,
    "business": 399,
    "other": 199,
}

CATEGORY_LABELS = {
    "police": "Police / FIR / Crime",
    "property": "Property / Land / Rental",
    "money": "Money / Loan / Fraud",
    "family": "Family / Divorce",
    "business": "Business / Contracts",
    "other": "Other legal issues",
}

LANGUAGE_BUTTONS = [
    {"id": "lang_en", "title": "English"},
    {"id": "lang_hinglish", "title": "Hinglish"},
    {"id": "lang_mar", "title": "मराठी (Marathi)"},
]

BOOKING_KEYWORDS = [
    "speak to lawyer", "call lawyer", "consult lawyer", "book call",
    "book consultation", "yes", "ok", "okay", "book", "call", "consult", "lawyer"
]

STATE_PORTALS = {
    "maharashtra": "https://mhpolice.maharashtra.gov.in",
    "delhi": "https://delhipolice.gov.in",
    "karnataka": "https://ksp.karnataka.gov.in",
    "uttar pradesh": "https://uppolice.gov.in",
    "tamil nadu": "https://eservices.tnpolice.gov.in",
    "telangana": "https://tspolice.gov.in",
}

pending_booking_state = {}
pending_rating_state = {}
followup_sent = set()


def generate_case_id():
    return f"NS-{uuid.uuid4().hex[:6].upper()}"


def get_or_create_user(wa_id):
    db = SessionLocal()
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if not user:
        user = User(whatsapp_id=wa_id, case_id=generate_case_id(), language="English", query_count=0)
        db.add(user)
        db.commit()
    db.close()
    return user


def log_msg(wa_id, direction, text):
    db = SessionLocal()
    db.add(Conversation(user_whatsapp_id=wa_id, direction=direction, text=text))
    db.commit()
    db.close()


def count_real_questions(wa_id):
    ignore = {"hi", "hello", "hey", "book", "call", "consult", "speak to lawyer"}
    db = SessionLocal()
    msgs = db.query(Conversation).filter_by(user_whatsapp_id=wa_id, direction="user").all()
    db.close()
    return sum(1 for m in msgs if (m.text or "").lower().strip() not in ignore)


def count_bot(wa_id):
    db = SessionLocal()
    msgs = db.query(Conversation).filter_by(user_whatsapp_id=wa_id, direction="bot").all()
    db.close()
    return len(msgs)


# -------------------- ADMIN: mark booking as completed -> request rating --------------------
@app.post("/booking/mark_completed")
def admin_mark_completed():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return {"error": "invalid token"}, 401

    data = request.get_json(silent=True) or {}
    booking_id = data.get("booking_id")
    if not booking_id:
        return {"error": "booking_id required"}, 400

    db = SessionLocal()
    booking = db.query(Booking).filter_by(id=booking_id).first()
    if not booking:
        db.close()
        return {"error": "not found"}, 404

    booking.status = "completed"
    db.commit()
    pending_rating_state[booking.user_whatsapp_id] = booking_id
    db.close()

    send_text(
        booking.user_whatsapp_id,
        "Thank you for using NyaySetu 🙏\nPlease rate your consultation:\n\n"
        "1️⃣ Very helpful\n"
        "2️⃣ Good\n"
        "3️⃣ Average\n"
        "4️⃣ Not helpful"
    )
    return {"status": "rating_requested"}


# -------------------- VERIFY WEBHOOK --------------------
@app.get("/webhook")
def verify():
    if request.args.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Invalid", 403


# -------------------- MAIN WHATSAPP BOT --------------------
@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    logging.info("INCOMING WHATSAPP PAYLOAD: %s", payload)

    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
    except Exception:
        return jsonify({"status": "ignored"}), 200

    # ⛔ ignore system events (delivery/read receipts etc)
    if not value.get("messages"):
        logging.info("No user message — system event ignored")
        return jsonify({"status": "ignored"}), 200

    msg = value["messages"][0]
    contacts = value.get("contacts", [{}])
    wa_id = contacts[0].get("wa_id")

    if not wa_id:
        logging.info("Missing wa_id — ignored")
        return jsonify({"status": "ignored"}), 200

    # extract message text
    if msg.get("type") == "interactive":
        inter = msg["interactive"]
        text = inter.get("button_reply", {}).get("id") or inter.get("list_reply", {}).get("id", "")
    else:
        text = msg.get("text", {}).get("body", "")
    text = (text or "").strip()

    user = get_or_create_user(wa_id)
    log_msg(wa_id, "user", text)

    # ⭐ RATING MODE
    if wa_id in pending_rating_state:
        booking_id = pending_rating_state[wa_id]
        if text not in {"1", "2", "3", "4"}:
            send_text(wa_id, "Please reply with 1, 2, 3 or 4.")
            return {"status": "rating_wait"}

        db = SessionLocal()
        booking = db.query(Booking).filter_by(id=booking_id).first()
        if booking:
            booking.rating = int(text)
            db.commit()
        db.close()
        pending_rating_state.pop(wa_id, None)

        if text in {"1", "2", "3"}:
            send_text(wa_id, "Thank you very much for your feedback 🙏")
        else:
            send_text(
                wa_id,
                "We’re sorry the experience was not great 🙏\nWould you like to speak to a different lawyer at NO extra cost?\nReply YES to continue."
            )
        return {"status": "rating_done"}

    # ⭐ Free replacement lawyer request
    if text.lower() == "yes" and wa_id not in pending_booking_state:
        send_text(wa_id, "Sure — please reply with your preferred call time slot.")
        pending_booking_state[wa_id] = {"step": "await_time", "fee": 0, "category": "other"}
        return {"status": "rebook_free"}

    # ⭐ First message — show language buttons
    if count_bot(wa_id) == 0:
        send_text(wa_id, f"👋 Welcome to NyaySetu! Your Case ID: {user.case_id}")
        send_buttons(wa_id, "Select your preferred language 👇", LANGUAGE_BUTTONS)
        return {"status": "lang_select"}

    # ⭐ Language change
    if text.startswith("lang_"):
        lang = "English" if text == "lang_en" else ("Hinglish" if text == "lang_hinglish" else "Marathi")
        db = SessionLocal()
        db.query(User).filter_by(whatsapp_id=wa_id).update({"language": lang})
        db.commit()
        db.close()
        send_text(wa_id, f"Language updated to {lang}. Please type your legal issue.")
        return {"status": "lang_set"}

    # ⭐ User asks for lawyer
    if any(k in text.lower() for k in BOOKING_KEYWORDS) and count_real_questions(wa_id) >= 1:
        buttons = [{"id": c, "title": CATEGORY_LABELS[c]} for c in CATEGORY_LABELS]
        send_buttons(wa_id, "Please select your legal category 👇", buttons)
        pending_booking_state[wa_id] = {"step": "choose_category"}
        return {"status": "category_asked"}

    # ⭐ Category selected
    if wa_id in pending_booking_state and pending_booking_state[wa_id]["step"] == "choose_category":
        if text not in CATEGORY_PRICE:
            send_text(wa_id, "Please select a valid category.")
            return {"status": "invalid_category"}
        pending_booking_state[wa_id] = {
            "step": "await_time",
            "fee": CATEGORY_PRICE[text],
            "category": text
        }
        send_text(wa_id, f"Consultation fee: ₹{CATEGORY_PRICE[text]}\nPlease share preferred call time.")
        return {"status": "await_time"}

    # ⭐ Time provided — booking created
    if wa_id in pending_booking_state and pending_booking_state[wa_id]["step"] == "await_time":
        slot = text
        fee = pending_booking_state[wa_id]["fee"]
        category = pending_booking_state[wa_id]["category"]

        booking = create_booking_for_user(wa_id, fee, slot)
        send_text(
            wa_id,
            f"📞 Booking created!\nAmount: ₹{fee}\nTime: {slot}\n\n"
            f"Click below to complete secure payment:\n{booking.payment_link}"
        )
        pending_booking_state.pop(wa_id, None)
        return {"status": "booking_done"}

    # ⭐ AI assistance
    lang = user.language
    category = detect_category(text)
    reply = generate_legal_reply(text, lang)

    send_typing_on(wa_id)
    time.sleep(TYPING_DELAY)
    send_typing_off(wa_id)

    send_text(wa_id, reply)
    log_msg(wa_id, "bot", reply)

    # Soft upsell only once
    if count_real_questions(wa_id) >= 2 and wa_id not in followup_sent:
        price = CATEGORY_PRICE.get(category, 199)
        send_buttons(
            wa_id,
            f"📞 Want to speak with a lawyer?\nConsultation fee: ₹{price}",
            [{"id": "speak_lawyer", "title": "Yes"}]
        )
        followup_sent.add(wa_id)

    return jsonify({"status": "replied"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
