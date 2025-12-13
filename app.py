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
    BOOKING_CUTOFF_HOURS,
)

# SERVICES
from services.whatsapp_service import (
    send_text, send_typing_on, send_typing_off, send_list_picker, send_buttons
)
from services.openai_service import ai_reply
from services.location_service import (
    detect_state, detect_district, list_states, list_districts
)
from services.booking_service import (
    generate_dates_calendar,
    generate_slots_calendar,
    create_booking_temp,
    confirm_booking_after_payment,
    SLOT_MAP
)

# Logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Conversation states
NORMAL = "NORMAL"
SUGGEST_CONSULT = "SUGGEST_CONSULT"
ASK_NAME = "ASK_NAME"
ASK_STATE = "ASK_STATE"
ASK_DISTRICT = "ASK_DISTRICT"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"


# -------------------------------------------------------------------------
# DB session helper
# -------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    return SessionLocal()


# -------------------------------------------------------------------------
# Create or fetch user
# -------------------------------------------------------------------------
def make_case_id():
    import random, string
    return "NS-" + "".join(random.choices(string.hexdigits.upper(), k=6))


def get_or_create_user(db, wa_id):
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if not user:
        user = User(
            whatsapp_id=wa_id,
            case_id=make_case_id(),
            language="English",
            state=NORMAL,
            query_count=0,
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user {wa_id} → case_id {user.case_id}")
    return user


def save_state(db, user, state):
    user.state = state
    db.add(user)
    db.commit()


# -------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return "NyaySetu backend is running.", 200


# -------------------------------------------------------------------------
# WhatsApp verification
# -------------------------------------------------------------------------
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403


# -------------------------------------------------------------------------
# Main WhatsApp message handler
# -------------------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(force=True, silent=True) or {}
    logger.info("INCOMING WHATSAPP PAYLOAD: %s", json.dumps(payload))

    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]["value"]
    except Exception:
        logger.error("Malformed payload")
        return jsonify({"status": "ignored"}), 200

    messages = change.get("messages")
    if not messages:
        logger.info("No user message — system event ignored")
        return jsonify({"status": "ignored"}), 200

    message = messages[0]
    wa_id = change["contacts"][0]["wa_id"]

    db = get_db_session()
    try:
        user = get_or_create_user(db, wa_id)

        msg_type = message.get("type")
        text_body = ""
        interactive_id = None

        # Extract text
        if msg_type == "text":
            text_body = message["text"]["body"].strip()
        elif msg_type == "interactive":
            itype = message["interactive"]["type"]
            if itype == "button_reply":
                interactive_id = message["interactive"]["button_reply"]["id"]
                text_body = interactive_id
            else:
                interactive_id = message["interactive"]["list_reply"]["id"]
                text_body = interactive_id
        else:
            send_text(wa_id, "Sorry, I support only text and quick replies.")
            return jsonify({"ok": True})

        logger.info(f"Parsed → text_body='{text_body}', id='{interactive_id}', state={user.state}")


        # ---------------------------------------------------------------------
        # BOOKING FLOW
        # ---------------------------------------------------------------------

        # Step 1: Ask Name
        if user.state == ASK_NAME:
            user.name = text_body
            db.commit()
            save_state(db, user, ASK_STATE)
            send_text(wa_id, "Thanks! 🙏\nWhich *state* are you from?")
            return jsonify({"ok": True})

        # Step 2: Ask State
        if user.state == ASK_STATE:
            detected = detect_state(text_body)

            if detected:
                user.state_name = detected
                db.commit()
                save_state(db, user, ASK_DISTRICT)

                districts = list_districts(detected)
                send_list_picker(
                    wa_id,
                    header=f"Select district in {detected}",
                    body="Choose district",
                    rows=districts,
                    section_title=f"{detected} districts",
                )
                return jsonify({"ok": True})

            # Fallback: show all states
            send_list_picker(
                wa_id,
                header="Select your State",
                body="Choose from list",
                rows=list_states(),
                section_title="Indian States"
            )
            return jsonify({"ok": True})

        # Step 3: District selection from picker
        if user.state == ASK_DISTRICT:
            if interactive_id and interactive_id.startswith("district_"):
                parts = interactive_id.split("_")
                state = parts[1]
                district = parts[2]

                user.state_name = state
                user.district_name = district
                db.commit()

                save_state(db, user, ASK_CATEGORY)
                send_text(wa_id, "Got it 👍\nNow select your *legal issue category* (FIR, Police, Property, Family, Job, Business, Other).")
                return jsonify({"ok": True})

            # Auto-detect district if typed
            detected = detect_district(user.state_name, text_body)
            if detected:
                user.district_name = detected
                db.commit()
                save_state(db, user, ASK_CATEGORY)

                send_text(wa_id, "Great 👍\nPlease tell your *legal issue category*.")
                return jsonify({"ok": True})

            # Re-ask district
            send_list_picker(
                wa_id,
                header=f"Select district in {user.state_name}",
                body="Choose from list",
                rows=list_districts(user.state_name),
                section_title=f"{user.state_name} Districts",
            )
            return jsonify({"ok": True})

        # Step 4: Category → Ask Date
        if user.state == ASK_CATEGORY:
            user.category = text_body
            db.commit()
            save_state(db, user, ASK_DATE)

            rows = generate_dates_calendar()
            send_list_picker(
                wa_id,
                header="Select appointment date 👇",
                body="Available Dates",
                rows=rows,
                section_title="Next 7 days"
            )
            return jsonify({"ok": True})

        # Step 5: Date → Ask Slot
        if user.state == ASK_DATE:
            if interactive_id and interactive_id.startswith("date_"):
                user.temp_date = interactive_id.replace("date_", "")
                db.commit()

                rows = generate_slots_calendar(user.temp_date)
                save_state(db, user, ASK_SLOT)

                send_list_picker(
                    wa_id,
                    header=f"Select time slot for {user.temp_date}",
                    body="Available time slots (IST)",
                    rows=rows,
                    section_title="Time Slots"
                )
                return jsonify({"ok": True})

            send_text(wa_id, "Please select a date from the list.")
            return jsonify({"ok": True})

        # Step 6: Slot → Payment
        if user.state == ASK_SLOT:
            if interactive_id and interactive_id.startswith("slot_"):
                slot_code = interactive_id.replace("slot_", "")

                booking, result = create_booking_temp(
                    db,
                    user,
                    user.name,
                    user.state_name,
                    user.district_name,
                    user.category,
                    user.temp_date,
                    slot_code
                )

                if not booking:
                    send_text(wa_id, f"⚠️ {result}")
                    return jsonify({"ok": True})

                # Success → show payment link
                payment_link = result
                user.last_payment_link = payment_link
                db.commit()
                save_state(db, user, WAITING_PAYMENT)

                send_text(
                    wa_id,
                    "✅ *Your appointment details:*\n"
                    f"*Name:* {user.name}\n"
                    f"*State:* {user.state_name}\n"
                    f"*District:* {user.district_name}\n"
                    f"*Category:* {user.category}\n"
                    f"*Date:* {user.temp_date}\n"
                    f"*Slot:* {SLOT_MAP.get(slot_code)}\n"
                    f"*Fees:* ₹{BOOKING_PRICE}\n\n"
                    f"Please complete payment:\n{payment_link}"
                )
                return jsonify({"ok": True})

            send_text(wa_id, "Please select a slot from the list.")
            return jsonify({"ok": True})

        # Step 7: Waiting for payment
        if user.state == WAITING_PAYMENT:
            send_text(wa_id, f"💳 Your payment link is still active:\n{user.last_payment_link}")
            return jsonify({"ok": True})

        # ---------------------------------------------------------------------
        # DEFAULT → AI NATURAL CHAT
        # ---------------------------------------------------------------------
        send_typing_on(wa_id)
        reply = ai_reply(text_body, user)
        send_typing_off(wa_id)
        send_text(wa_id, reply)
        return jsonify({"ok": True})

    except Exception as e:
        logger.exception("Error in webhook")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# -------------------------------------------------------------------------
# PAYMENT WEBHOOK
# -------------------------------------------------------------------------
@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    data = request.get_json(force=True, silent=True) or {}
    token = data.get("token") or data.get("payment_token")

    if not token:
        return jsonify({"error": "missing token"}), 400

    db = get_db_session()
    try:
        booking, status = confirm_booking_after_payment(db, token)

        if not booking:
            return jsonify({"error": status}), 404

        # Notify user
        send_text(
            booking.whatsapp_id,
            f"✅ Your booking for {booking.date} at {booking.slot_readable} is confirmed!"
        )
        return jsonify({"status": "confirmed"}), 200

    finally:
        db.close()


# -------------------------------------------------------------------------
# STARTUP — Run migrations
# -------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        try:
            print("🔧 Running DB migrations...")
            create_all()
            print("✅ DB tables ready.")
        except Exception as e:
            print("DB init failed:", e)

    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
