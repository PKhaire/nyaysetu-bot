# app.py
from flask import Flask, request, jsonify, render_template_string
import time
import logging

from config import WHATSAPP_VERIFY_TOKEN, MAX_FREE_MESSAGES, TYPING_DELAY_SECONDS, ADMIN_PASSWORD
from services.whatsapp_service import send_text, send_typing_on, send_typing_off, send_buttons
from services.openai_service import detect_language, detect_category, generate_legal_reply
from services.booking_service import create_booking_for_user, verify_booking_otp
from utils import register_user_if_missing, store_message, user_message_count
from db import Base, engine
from models import User, Booking

# ensure tables created
Base.metadata.create_all(bind=engine)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# final welcome text template (user provided)
WELCOME_TEMPLATE = (
    "👋 Welcome to NyaySetu — The Bridge To Justice.\n\n"
    "Your Case ID: {case_id}\n"
    "I’m your NyaySetu Legal Assistant.\n\n"
    "Please tell me your legal issue.\n"
    "I will guide you clearly, safely, and confidentially."
)

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # Verification
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            return challenge, 200
        return "Verification failed", 403

    payload = request.get_json(force=True, silent=True) or {}
    logging.info("Incoming payload: %s", payload)

    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", []) or []
        if not messages:
            return jsonify({"status": "no_messages"}), 200

        msg = messages[0]
        wa_from = msg.get("from")
        wa_type = msg.get("type")
        text_body = msg.get("text", {}).get("body", "")
        profile = msg.get("profile", {}) or {}
        display_name = profile.get("name")

        # register user if missing
        user = register_user_if_missing(wa_from, name=display_name)

        # store user message
        store_message(wa_from, "user", text_body or f"<{wa_type}>")

        # If first or early message -> welcome
        conv_count = user_message_count(wa_from)
        if conv_count <= 1:
            # detect language from message or default
            lang = detect_language(text_body or display_name or "Hello")
            # update user language
            user.language = lang
            # send welcome
            send_typing_on(wa_from)
            time.sleep(TYPING_DELAY_SECONDS)
            welcome_text = WELCOME_TEMPLATE.format(case_id=user.case_id)
            send_text(wa_from, welcome_text)
            send_typing_off(wa_from)
            # quick category buttons
            send_buttons(wa_from, "Choose a category to help me understand:", [
                {"id": "property", "title": "🏠 Property"},
                {"id": "police", "title": "🚨 Police / FIR"},
                {"id": "family", "title": "👪 Family"},
                {"id": "business", "title": "💼 Business"},
                {"id": "money", "title": "💰 Money/Recovery"},
            ])
            return jsonify({"status": "welcome_sent"}), 200

        # booking commands
        if text_body.strip().upper() == "BOOK":
            send_text(wa_from, "📅 Sure — Please reply with your preferred time (e.g., Tomorrow Morning / Today Evening).")
            return jsonify({"status": "asked_preferred_time"}), 200

        # booking preferred times (simple set)
        if text_body.strip().lower() in ("morning", "today morning", "tomorrow morning", "afternoon", "evening", "today evening", "tomorrow evening"):
            booking = create_booking_for_user(wa_from, text_body.strip())
            send_text(wa_from, "✅ Thanks. We’ve created a tentative booking. Your OTP is sent via WhatsApp for confirmation.")
            # For demo we send OTP on chat (in prod use SMS/email)
            send_text(wa_from, f"🔐 OTP: {booking.otp} (valid 10 minutes)\nTo confirm, reply: CONFIRM <OTP>\nOr pay to confirm: {booking.payment_link}")
            return jsonify({"status": "booking_created"}), 200

        # confirm booking via OTP
        if text_body.strip().upper().startswith("CONFIRM"):
            parts = text_body.strip().split()
            if len(parts) >= 2:
                otp_candidate = parts[1]
                ok, res = verify_booking_otp(wa_from, otp_candidate)
                if ok:
                    send_text(wa_from, f"🎉 Booking confirmed for {res.preferred_time}. Lawyer will call you at booked time.")
                    # assign lawyer stub
                    send_text(wa_from, "A verified lawyer will contact you. Thank you.")
                    return jsonify({"status": "booking_confirmed"}), 200
                else:
                    send_text(wa_from, f"OTP verification failed: {res}")
                    return jsonify({"status": "otp_failed"}), 200

        # free message quota check
        user_msgs_count = user_message_count(wa_from)
        if user_msgs_count > MAX_FREE_MESSAGES:
            send_text(wa_from, "You have used your free answers. For a detailed consultation, please book a paid consultation.\nReply BOOK to start booking.")
            return jsonify({"status": "limit_reached"}), 200

        # Normal flow: detect language, category, generate reply
        lang = detect_language(text_body)
        category = detect_category(text_body)
        logging.info("Detected lang=%s category=%s", lang, category)

        send_typing_on(wa_from)
        time.sleep(TYPING_DELAY_SECONDS)
        ai_reply = generate_legal_reply(text_body, language=lang, category=category)
        send_text(wa_from, ai_reply)
        send_typing_off(wa_from)

        store_message(wa_from, "bot", ai_reply)

        # Follow-up buttons
        send_buttons(wa_from, "Choose what you'd like next:", [
            {"id": "book", "title": "📅 Book Consultation"},
            {"id": "draft", "title": "📄 Get Draft Notice"},
            {"id": "call", "title": "📞 Lawyer Call"},
        ])

        return jsonify({"status": "replied"}), 200

    except Exception as e:
        logging.exception("Webhook processing error")
        return jsonify({"status": "error", "error": str(e)}), 500

# Simple health check
@app.route("/health")
def health():
    return jsonify({"status": "ok"})
