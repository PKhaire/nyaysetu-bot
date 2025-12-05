import os
import json
import logging
from datetime import datetime
from db import create_all
print("🔧 Running DB migrations...")
create_all()
print("✅ DB tables ready.")

from flask import Flask, request, jsonify
from config import (
    WHATSAPP_VERIFY_TOKEN,
    MAX_FREE_MESSAGES,
    TYPING_DELAY_SECONDS,
    ADMIN_TOKEN
)

from db import get_db
from models import User, Booking
from services.whatsapp_service import (
    send_text, send_buttons, send_typing_on, send_typing_off,
    send_list_picker
)
from services.openai_service import ai_reply
from services.booking_service import (
    generate_dates_calendar,
    generate_slots,
    start_booking_flow,
    handle_date_selection,
    handle_slot_selection,
    confirm_booking_after_payment,
    mark_booking_completed
)


app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Chat states
ASK_NAME = "ASK_NAME"
ASK_CITY = "ASK_CITY"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"
ASK_RATING = "ASK_RATING"
NORMAL_CHAT = "NORMAL_CHAT"

LEGAL_CATEGORIES = [
    "Criminal",
    "Property",
    "Family / Divorce",
    "Cyber",
    "Consumer",
    "Employment",
    "Motor Accident",
    "Other"
]

def get_or_create_user(wa_id):
    db = next(get_db())
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if user:
        return user

    case_id = f"NS-{os.urandom(3).hex().upper()}"
    user = User(
        whatsapp_id=wa_id,
        case_id=case_id,
        language="English",
        query_count=0,
        state=NORMAL_CHAT
    )
    db.add(user)
    db.commit()
    return user

def save_and_close_state(user, state):
    db = next(get_db())
    user.state = state
    db.add(user)
    db.commit()
def handle_language_change(user, wa_id, message):
    language_map = {
        "lang_en": "English",
        "lang_hinglish": "Hinglish",
        "lang_mar": "Marathi"
    }

    if message in language_map:
        db = next(get_db())
        user.language = language_map[message]
        user.state = NORMAL_CHAT
        db.add(user)
        db.commit()
        send_text(wa_id, f"Language updated to {user.language}. Please type your legal issue.")
        return True
    return False


def should_offer_booking(user, ai_msg):
    keywords = ["speak to lawyer", "talk to lawyer", "call lawyer", "book lawyer", "consult", "appointment", "advocate"]
    msg = ai_msg.lower()
    return any(k in msg for k in keywords)


def start_booking_flow(user, wa_id):
    send_text(wa_id, "Before we schedule your consultation call, please share your full name.")
    save_and_close_state(user, ASK_NAME)


@app.route("/webhook", methods=["GET"])
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    return challenge if token == WHATSAPP_VERIFY_TOKEN else "Invalid", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"INCOMING WHATSAPP PAYLOAD: {json.dumps(data)}")

    try:
        value = data["entry"][0]["changes"][0]["value"]
    except Exception:
        return jsonify({"status": "ignored"}), 200

    # System events (sent/read/delivered) → ignore
    if "messages" not in value:
        logging.info("No user message — system event ignored")
        return jsonify({"status": "ignored"}), 200

    message = value["messages"][0]
    wa_id = value["contacts"][0]["wa_id"]
    user = get_or_create_user(wa_id)

    # Extract message content
    if message["type"] == "text":
        text = message["text"]["body"].strip()
    elif message["type"] == "interactive" and message["interactive"]["type"] == "button_reply":
        text = message["interactive"]["button_reply"]["id"]
    elif message["type"] == "interactive" and message["interactive"]["type"] == "list_reply":
        text = message["interactive"]["list_reply"]["id"]
    else:
        send_text(wa_id, "Sorry, I only process text messages currently.")
        return jsonify({"status": "ok"}), 200

    # Handle language selection
    if handle_language_change(user, wa_id, text):
        return jsonify({"status": "ok"}), 200

    # Smart booking state machine
    if user.state == ASK_NAME:
        user.temp_name = text
        save_and_close_state(user, ASK_CITY)
        send_text(wa_id, "Please confirm your city.")
        return jsonify({"status": "ok"}), 200

    if user.state == ASK_CITY:
        user.temp_city = text
        save_and_close_state(user, ASK_CATEGORY)
        send_list_picker(
            wa_id, "Select legal category 👇", "Choose one",
            [(c, c) for c in LEGAL_CATEGORIES]
        )
        return jsonify({"status": "ok"}), 200

    if user.state == ASK_CATEGORY:
        user.temp_category = text
        save_and_close_state(user, ASK_DATE)
        send_list_picker(wa_id, "Select appointment date 👇", "Available Dates", generate_dates_calendar())
        return jsonify({"status": "ok"}), 200

    if user.state == ASK_DATE:
        user.temp_date = text
        save_and_close_state(user, ASK_SLOT)
        send_list_picker(wa_id, "Choose time slot 👇", "Available Slots", generate_slots_calendar(text))
        return jsonify({"status": "ok"}), 200

    if user.state == ASK_SLOT:
        user.temp_slot = text
        payment_url = create_booking_temp(user)
        save_and_close_state(user, WAITING_PAYMENT)
        send_buttons(
            wa_id,
            f"Consultation fee: ₹499\nPress below to pay & confirm your call.",
            [("Pay ₹499", payment_url)]
        )
        return jsonify({"status": "ok"}), 200

    # Rating collection
    if user.state == ASK_RATING:
        try:
            rating = int(text)
            if 1 <= rating <= 5:
                db = next(get_db())
                booking = db.query(Booking).filter_by(user_id=user.id, rating=None).order_by(Booking.id.desc()).first()
                booking.rating = rating
                db.commit()
                send_text(wa_id, "Thank you for your feedback! 🙏")
                user.state = NORMAL_CHAT
                db.commit()
                return jsonify({"status": "ok"}), 200
        except:
            pass
        send_text(wa_id, "Please rate from 1 to 5 ⭐")
        return jsonify({"status": "ok"}), 200
    # Free AI usage limit
    if user.query_count >= MAX_FREE_MESSAGES and user.state == NORMAL_CHAT:
        send_buttons(
            wa_id,
            "You've reached the free message limit.\nTo continue, book a consultation call with a lawyer 👇",
            [("📞 Book Lawyer – ₹499", "start_booking")]
        )
        return jsonify({"status": "ok"}), 200

    # Detect explicit request to book
    if text.lower() in ["book", "book lawyer", "consult", "speak to lawyer", "call lawyer", "appointment"]:
        start_booking_flow(user, wa_id)
        return jsonify({"status": "ok"}), 200

    # If waiting for payment, ignore casual messages
    if user.state == WAITING_PAYMENT:
        send_buttons(
            wa_id,
            "Kindly complete the payment to confirm your consultation call 👇",
            [("Pay ₹499", user.last_payment_link)]
        )
        return jsonify({"status": "ok"}), 200

    # 🔥 Smart: if returning user (Flow-3)
    if user.state == NORMAL_CHAT and should_offer_booking(text, text):
        # Returning users skip details directly to calendar
        send_list_picker(wa_id, "Select appointment date 👇", "Available Dates", generate_dates_calendar())
        save_and_close_state(user, ASK_DATE)
        return jsonify({"status": "ok"}), 200

    # Normal AI reply
    send_typing_on(wa_id)
    reply = ai_reply(text, user.language)
    send_typing_off(wa_id)
    send_text(wa_id, reply)

    # Increment message count
    db = next(get_db())
    user.query_count += 1
    db.commit()

    # After reply → offer lawyer only when relevant
    if should_offer_booking(user, reply):
        send_buttons(
            wa_id,
            "📞 Want to speak to a lawyer for personalised help?\nConsultation fee: ₹499",
            [("Book Consultation", "start_booking")]
        )

    return jsonify({"status": "ok"}), 200
@app.route("/payment/success", methods=["POST"])
def payment_success():
    data = request.get_json()
    wa_id = data.get("wa_id")
    payment_id = data.get("payment_id")

    if not wa_id or not payment_id:
        return jsonify({"status": "failed", "error": "missing_fields"}), 400

    db = next(get_db())
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if not user:
        return jsonify({"status": "failed", "error": "user_not_found"}), 404

    booking = confirm_booking_after_payment(user, payment_id)
    if not booking:
        return jsonify({"status": "failed", "error": "booking_not_found"}), 404

    # Notify user
    send_text(
        wa_id,
        f"🎉 Appointment Confirmed!\n\n"
        f"📅 Date: {booking.date}\n"
        f"⏰ Time: {booking.slot}\n"
        f"📞 The lawyer will call you on your phone number.\n\n"
        f"If you need anything before your call, just text here."
    )

    return jsonify({"status": "ok"}), 200
@app.route("/booking/mark_completed", methods=["POST"])
def mark_completed_api():
    token = request.args.get("token")
    booking_id = request.json.get("booking_id")

    if token != ADMIN_TOKEN:
        return jsonify({"status": "unauthorized"}), 401

    rating_triggered = mark_booking_completed(booking_id)
    if not rating_triggered:
        return jsonify({"status": "failed", "error": "booking_not_found"}), 404

    booking = rating_triggered
    wa_id = booking.user.whatsapp_id

    # Ask for rating automatically
    ask_rating_buttons(wa_id)
    db = next(get_db())
    booking.user.state = ASK_RATING
    db.commit()

    return jsonify({"status": "ok", "rating_request_sent": True}), 200
@app.route("/admin/broadcast", methods=["POST"])
def broadcast():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"status": "unauthorized"}), 401

    msg = request.json.get("message")
    db = next(get_db())
    users = db.query(User).all()

    for u in users:
        try:
            send_text(u.whatsapp_id, msg)
        except Exception as e:
            logging.error(f"Broadcast failed for {u.whatsapp_id}: {e}")

    return jsonify({"status": "ok", "sent": len(users)}), 200


@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "running",
        "service": "NyaySetu WhatsApp Legal AI",
        "version": "3.0"
    }), 200


@app.errorhandler(Exception)
def error_handler(e):
    logging.error("Error:", exc_info=e)
    return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
