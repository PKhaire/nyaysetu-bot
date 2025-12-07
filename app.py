import os
import json
import logging
from datetime import datetime

from flask import Flask, request, jsonify

from db import create_all, get_db, SessionLocal
from config import (
    WHATSAPP_VERIFY_TOKEN,
    MAX_FREE_MESSAGES,
    TYPING_DELAY_SECONDS,
    ADMIN_TOKEN
)
from models import User, Booking
from services.whatsapp_service import (
    send_text, send_buttons, send_typing_on, send_typing_off,
    send_list_picker
)
from services.openai_service import ai_reply
from services.booking_service import (
    generate_dates_calendar,
    generate_slots,
    start_booking_flow as booking_start_flow,
    handle_date_selection,
    handle_slot_selection,
    confirm_booking_after_payment,
    mark_booking_completed,
    ask_rating_buttons,
)

# Run DB migrations once at startup
logging.basicConfig(level=logging.INFO)
logging.info("🔧 Running DB migrations...")
create_all()
logging.info("✅ DB tables ready.")

app = Flask(__name__)

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
    "Other",
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
        state=NORMAL_CHAT,
    )
    db.add(user)
    db.commit()
    return user


def save_and_close_state(user, state):
    """
    Safely update user.state even if user came from another session.
    """
    db = SessionLocal()
    try:
        user.state = state
        db.merge(user)  # merge handles objects from other sessions
        db.commit()
    finally:
        db.close()


def handle_language_change(user, wa_id, message):
    language_map = {
        "lang_en": "English",
        "lang_hinglish": "Hinglish",
        "lang_mar": "Marathi",
    }

    if message in language_map:
        db = SessionLocal()
        try:
            # refresh user in this session
            db_user = db.query(User).filter_by(id=user.id).first()
            if not db_user:
                return False
            db_user.language = language_map[message]
            db_user.state = NORMAL_CHAT
            db.commit()
        finally:
            db.close()

        send_text(
            wa_id,
            f"Language updated to {language_map[message]}. Please type your legal issue.",
        )
        return True
    return False


def should_offer_booking(user, ai_msg):
    keywords = [
        "speak to lawyer",
        "talk to lawyer",
        "call lawyer",
        "book lawyer",
        "consult",
        "appointment",
        "advocate",
    ]
    msg = ai_msg.lower()
    return any(k in msg for k in keywords)


def start_booking_flow(user, wa_id):
    send_text(
        wa_id,
        "Before we schedule your consultation call, please share your full name.",
    )
    save_and_close_state(user, ASK_NAME)


@app.route("/webhook", methods=["GET"])
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    return (challenge, 200) if token == WHATSAPP_VERIFY_TOKEN else ("Invalid", 403)


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

    # ==========================
    # BOOKING STATE MACHINE
    # ==========================

    # ASK_NAME
    if user.state == ASK_NAME:
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(id=user.id).first()
            if db_user:
                db_user.temp_name = text
                db_user.state = ASK_CITY
                db.commit()
        finally:
            db.close()

        send_text(wa_id, "Please confirm your city.")
        return jsonify({"status": "ok"}), 200

    # ASK_CITY
    if user.state == ASK_CITY:
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(id=user.id).first()
            if db_user:
                db_user.temp_city = text
                db_user.state = ASK_CATEGORY
                db.commit()
        finally:
            db.close()

        # Build legal category list as WhatsApp-compliant list
        rows = [{"id": f"cat_{c}", "title": c} for c in LEGAL_CATEGORIES]
        sections = [{"title": "Legal categories", "rows": rows}]
        send_list_picker(
            wa_id,
            "Select legal category 👇",
            "Choose one",
            sections,
        )
        return jsonify({"status": "ok"}), 200

    # ASK_CATEGORY
    if user.state == ASK_CATEGORY:
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(id=user.id).first()
            if db_user:
                db_user.temp_category = text
                db_user.state = ASK_DATE
                db.commit()
        finally:
            db.close()

        raw_dates = generate_dates_calendar()
        date_rows = []
        for d in raw_dates:
            if isinstance(d, (list, tuple)) and len(d) >= 2:
                date_id, date_title = d[0], d[1]
            elif isinstance(d, dict):
                date_id = d.get("id") or d.get("value") or d.get("title")
                date_title = d.get("title") or d.get("label") or date_id
            else:
                date_id = str(d)
                date_title = str(d)
            date_rows.append({"id": date_id, "title": date_title})

        sections = [{"title": "Available dates", "rows": date_rows}]
        send_list_picker(
            wa_id,
            "Select appointment date 👇",
            "Available Dates",
            sections,
        )
        return jsonify({"status": "ok"}), 200

    # ASK_DATE
    if user.state == ASK_DATE:
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(id=user.id).first()
            if db_user:
                db_user.temp_date = text
                db_user.state = ASK_SLOT
                db.commit()
        finally:
            db.close()

        raw_slots = generate_slots(text)
        slot_rows = []
        for s in raw_slots:
            if isinstance(s, (list, tuple)) and len(s) >= 2:
                slot_id, slot_title = s[0], s[1]
            elif isinstance(s, dict):
                slot_id = s.get("id") or s.get("value") or s.get("title")
                slot_title = s.get("title") or s.get("label") or slot_id
            else:
                slot_id = str(s)
                slot_title = str(s)
            slot_rows.append({"id": slot_id, "title": slot_title})

        sections = [{"title": "Available slots", "rows": slot_rows}]
        send_list_picker(
            wa_id,
            "Choose time slot 👇",
            "Available Slots",
            sections,
        )
        return jsonify({"status": "ok"}), 200

    # ASK_SLOT
    if user.state == ASK_SLOT:
        # temp_slot + create booking + payment link
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(id=user.id).first()
            if not db_user:
                send_text(wa_id, "Something went wrong while saving your slot.")
                return jsonify({"status": "ok"}), 200

            db_user.temp_slot = text
            db.commit()

            payment_url = confirm_booking_after_payment(
                db_user, None, preview_only=True
            ) if hasattr(confirm_booking_after_payment, "preview_only") else None

            if not payment_url:
                # fallback: use booking_service temp booking creator if you have it
                from services.booking_service import create_booking_temp
                payment_url = create_booking_temp(db_user)

            db_user.state = WAITING_PAYMENT
            db_user.last_payment_link = payment_url
            db.commit()
        finally:
            db.close()

        send_buttons(
            wa_id,
            "Consultation fee: ₹499\nPress below to pay & confirm your call.",
            [("Pay ₹499", payment_url)],
        )
        return jsonify({"status": "ok"}), 200

    # ASK_RATING
    if user.state == ASK_RATING:
        try:
            rating = int(text)
            if 1 <= rating <= 5:
                db = SessionLocal()
                try:
                    booking = (
                        db.query(Booking)
                        .filter_by(user_id=user.id, rating=None)
                        .order_by(Booking.id.desc())
                        .first()
                    )
                    if booking:
                        booking.rating = rating
                        booking.user.state = NORMAL_CHAT
                        db.commit()
                        send_text(wa_id, "Thank you for your feedback! 🙏")
                        return jsonify({"status": "ok"}), 200
                finally:
                    db.close()
        except Exception:
            pass

        send_text(wa_id, "Please rate from 1 to 5 ⭐")
        return jsonify({"status": "ok"}), 200

    # ==========================
    # FREE MESSAGE LIMIT
    # ==========================
    if user.query_count >= MAX_FREE_MESSAGES and user.state == NORMAL_CHAT:
        send_buttons(
            wa_id,
            "You've reached the free message limit.\nTo continue, book a consultation call with a lawyer 👇",
            [("📞 Book Lawyer – ₹499", "start_booking")],
        )
        return jsonify({"status": "ok"}), 200

    # Detect explicit request to book
    if text.lower() in [
        "book",
        "book lawyer",
        "consult",
        "speak to lawyer",
        "call lawyer",
        "appointment",
    ]:
        start_booking_flow(user, wa_id)
        return jsonify({"status": "ok"}), 200

    # If waiting for payment, ignore casual messages
    if user.state == WAITING_PAYMENT:
        db = next(get_db())
        db_user = db.query(User).filter_by(id=user.id).first()
        link = db_user.last_payment_link if db_user else user.last_payment_link
        send_buttons(
            wa_id,
            "Kindly complete the payment to confirm your consultation call 👇",
            [("Pay ₹499", link)],
        )
        return jsonify({"status": "ok"}), 200

    # Smart: returning user → go straight to calendar if text indicates booking intent
    if user.state == NORMAL_CHAT and should_offer_booking(user, text):
        raw_dates = generate_dates_calendar()
        date_rows = []
        for d in raw_dates:
            if isinstance(d, (list, tuple)) and len(d) >= 2:
                date_id, date_title = d[0], d[1]
            elif isinstance(d, dict):
                date_id = d.get("id") or d.get("value") or d.get("title")
                date_title = d.get("title") or d.get("label") or date_id
            else:
                date_id = str(d)
                date_title = str(d)
            date_rows.append({"id": date_id, "title": date_title})
        sections = [{"title": "Available dates", "rows": date_rows}]
        send_list_picker(
            wa_id,
            "Select appointment date 👇",
            "Available Dates",
            sections,
        )
        save_and_close_state(user, ASK_DATE)
        return jsonify({"status": "ok"}), 200

    # ==========================
    # NORMAL AI REPLY
    # ==========================
    send_typing_on(wa_id)
    reply = ai_reply(text, user.language)
    send_typing_off(wa_id)
    send_text(wa_id, reply)

    # Increment message count safely
    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(id=user.id).first()
        if db_user:
            db_user.query_count += 1
            db.commit()
    finally:
        db.close()

    # After reply → offer lawyer only when relevant
    if should_offer_booking(user, reply):
        send_buttons(
            wa_id,
            "📞 Want to speak to a lawyer for personalised help?\nConsultation fee: ₹499",
            [("Book Consultation", "start_booking")],
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
        f"If you need anything before your call, just text here.",
    )

    return jsonify({"status": "ok"}), 200


@app.route("/booking/mark_completed", methods=["POST"])
def mark_completed_api():
    token = request.args.get("token")
    booking_id = request.json.get("booking_id")

    if token != ADMIN_TOKEN:
        return jsonify({"status": "unauthorized"}), 401

    # Mark as completed in service
    mark_booking_completed(booking_id)

    # Re-fetch booking & user in this session
    db = next(get_db())
    booking = db.query(Booking).get(booking_id)
    if not booking:
        return jsonify({"status": "failed", "error": "booking_not_found"}), 404

    wa_id = booking.user.whatsapp_id

    # Ask for rating automatically
    ask_rating_buttons(wa_id)
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
    return jsonify(
        {
            "status": "running",
            "service": "NyaySetu WhatsApp Legal AI",
            "version": "3.0",
        }
    ), 200


@app.errorhandler(Exception)
def error_handler(e):
    logging.error("Error:", exc_info=e)
    return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
