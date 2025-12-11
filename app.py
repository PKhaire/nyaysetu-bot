# app.py (full)
import os
import json
import logging
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort

# DB & models
from db import create_all, SessionLocal
from models import User, Booking  # your models.py must define these

# Config - make sure config.py exposes needed variables
from config import (
    WHATSAPP_VERIFY_TOKEN,
    WHATSAPP_TOKEN,
    WHATSAPP_PHONE_ID,
    WHATSAPP_API_URL,
    OPENAI_API_KEY,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    ADMIN_TOKEN,
)

# Services (assumed present)
from services.whatsapp_service import (
    send_text,
    send_buttons,
    send_typing_on,
    send_typing_off,
    send_list_picker,
)
from services.openai_service import ai_reply

# Booking service (the file above)
import booking_service as bs

# Razorpay client (optional)
try:
    import razorpay
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
except Exception:
    razorpay_client = None

# Scheduler
from apscheduler.schedulers.background import BackgroundScheduler

# Flask & logging
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

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

# Helper DB session
def get_db_session():
    return SessionLocal()

# create DB tables at startup
with app.app_context():
    try:
        logger.info("🔧 Running DB migrations...")
        create_all()
        logger.info("✅ DB tables ready.")
    except Exception as e:
        logger.exception("DB migration failed: %s", e)

# Scheduler jobs: auto-cancel + reminders
scheduler = BackgroundScheduler()
scheduler.start()

def job_auto_cancel_and_remind():
    db = get_db_session()
    try:
        # auto cancel unpaid older than 15 minutes
        canceled = bs.auto_cancel_unpaid_bookings(db)
        if canceled:
            logger.info("Auto-cancelled %d unpaid bookings", canceled)

        # reminders: simple approach - check confirmed bookings for near times
        now = datetime.now()
        three_hours = now + timedelta(hours=3)
        thirty_mins = now + timedelta(minutes=30)

        confirmed = db.query(Booking).filter(Booking.status == "CONFIRMED").all()
        for b in confirmed:
            slot_dt = bs.parse_slot_to_datetime(b.date_str, b.slot_str)
            if not slot_dt:
                continue
            # 3 hours window
            if 0 <= (slot_dt - three_hours).total_seconds() < 120:
                # notify user
                u = db.query(User).filter(User.id == b.user_id).first()
                if u:
                    send_text(u.whatsapp_id, f"⏰ Reminder: Your consultation is in ~3 hours ({b.date_str} {b.slot_str}).")
            # 30 minutes window
            if 0 <= (slot_dt - thirty_mins).total_seconds() < 120:
                u = db.query(User).filter(User.id == b.user_id).first()
                if u:
                    send_text(u.whatsapp_id, f"⏰ Reminder: Your consultation is in ~30 minutes ({b.date_str} {b.slot_str}).")
    except Exception:
        logger.exception("Error in scheduler job")
    finally:
        db.close()

# schedule every 2 minutes for reminders + every 5 minutes for cancels: combined function above
scheduler.add_job(job_auto_cancel_and_remind, "interval", minutes=2)

# ---------------------------
# Helper functions used inside webhook
# ---------------------------
def get_or_create_user(db, wa_id: str) -> User:
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if not user:
        user = User(
            whatsapp_id=wa_id,
            name=None,
            city=None,
            category=None,
            state=NORMAL,
            created_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user {wa_id} id={user.id}")
    return user

def save_state(db, user: User, state: str):
    user.state = state
    db.add(user)
    db.commit()

# language handler stub
def handle_language_change(db, user, wa_id, msg_id):
    return False

# start booking flow
def start_booking_flow(db, user, wa_id):
    # Rule 4: prevent double booking
    if bs.user_has_active_booking(db, user.id):
        send_text(wa_id, "⚠️ You already have an active booking. Type *cancel booking* to cancel it or *change date* to reschedule.")
        return
    # Rule 12: anti spam unpaid
    if bs.user_unpaid_count_last_24h(db, user.id) >= 2:
        send_text(wa_id, "⚠️ You have too many unpaid bookings. Please complete payment for previous booking(s) or try after 24 hours.")
        return
    save_state(db, user, ASK_NAME)
    send_text(wa_id, "Great! Let's schedule your legal consultation call (₹499).\n\nFirst, please tell me your *full name*.")

# booking state machine
def handle_booking_flow(db, user, wa_id, text, interactive_id):
    t = (text or "").strip()

    if user.state == ASK_NAME:
        user.name = t or user.name or "Client"
        db.add(user); db.commit()
        save_state(db, user, ASK_CITY)
        send_text(wa_id, "Thanks! 🙏\nNow please tell me your *city*.")
        return

    if user.state == ASK_CITY:
        user.city = t or user.city or "NA"
        db.add(user); db.commit()
        save_state(db, user, ASK_CATEGORY)
        send_text(wa_id, "Got it 👍\nPlease choose your *legal issue category* (e.g., FIR, Police, Property, Family, Job, Business, Other).")
        return

    if user.state == ASK_CATEGORY:
        user.category = t or user.category or "General"
        db.add(user); db.commit()
        # show dates
        rows = bs.generate_dates_calendar()
        save_state(db, user, ASK_DATE)
        send_list_picker(
            wa_id,
            header="Select appointment date 👇",
            body="Available Dates",
            rows=rows,
            section_title="Next 7 days"
        )
        return

    if user.state == ASK_DATE:
        # interactive list reply expected
        if interactive_id and interactive_id.startswith("date_"):
            date_str = interactive_id.replace("date_", "", 1)
            # validate (Rule 2)
            if not bs.validate_date_str(date_str):
                send_text(wa_id, "⚠️ Invalid date selected. Please pick again.")
                return
            user.temp_date = date_str
            db.add(user); db.commit()

            rows = bs.generate_slots_calendar(user.temp_date)
            if not rows:
                send_text(wa_id, "No slots available for that date. Please pick another date.")
                return
            save_state(db, user, ASK_SLOT)
            send_list_picker(
                wa_id,
                header=f"Select time slot for {user.temp_date}",
                body="Available time slots (IST)",
                rows=rows,
                section_title="Time Slots"
            )
            return
        else:
            send_text(wa_id, "Please select a date from the list I sent. If you didn't receive it, type *Book Consultation* to restart booking.")
            return

    if user.state == ASK_SLOT:
        if interactive_id and interactive_id.startswith("slot_"):
            # save code and readable slot
            slot_code = interactive_id.replace("slot_", "", 1)  # e.g. "8_9"
            slot_readable = bs.slot_code_to_readable(slot_code)
            user.temp_slot = slot_code
            db.add(user); db.commit()

            # Gather details for booking creation
            name = user.name or "Client"
            city = user.city or "NA"
            category = user.category or "General"
            date_str = getattr(user, "temp_date", None)
            if not date_str:
                send_text(wa_id, "Date missing. Please restart booking by typing *Book Consultation*.")
                save_state(db, user, NORMAL)
                return

            # Check again double booking before create (Rule 4)
            if bs.user_has_active_booking(db, user.id):
                send_text(wa_id, "⚠️ You already have an active booking. If you want a new one cancel existing booking first.")
                save_state(db, user, NORMAL)
                return

            # create booking (pending)
            try:
                booking, payment_link = bs.create_booking_temp(
                    db=db,
                    user=user,
                    name=name,
                    city=city,
                    category=category,
                    date=date_str,
                    slot=slot_code,
                    price=499
                )
            except Exception as e:
                logger.exception("Failed to create booking: %s", e)
                send_text(wa_id, "⚠️ Could not create booking. Please try again.")
                save_state(db, user, NORMAL)
                return

            user.last_payment_link = payment_link
            db.add(user); db.commit()
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
            return
        else:
            send_text(wa_id, "Please select a time slot from the list I sent.")
            return

    if user.state == WAITING_PAYMENT:
        send_text(wa_id, "💳 Your payment is still pending. If you completed payment, wait a minute for confirmation. If not, complete it using the last link.")
        return

    if user.state == ASK_RATING:
        try:
            rating_val = int(t)
            if 1 <= rating_val <= 5:
                # create rating model if exists (skipped here)
                save_state(db, user, NORMAL)
                send_text(wa_id, "🙏 Thank you for your feedback! 🙂")
            else:
                send_text(wa_id, "Please rate between 1 and 5 🌟.")
        except Exception:
            send_text(wa_id, "Please send a number between 1 and 5 for rating 🌟.")
        return

# ---------------------------
# Webhook endpoints
# ---------------------------
@app.route("/", methods=["GET"])
def index():
    return "NyaySetu backend running", 200

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified")
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
        logger.warning("Malformed payload")
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
            send_text(wa_id, "Sorry, I support text and simple button/list replies only.")
            return jsonify({"status": "ok"}), 200

        logger.info("Parsed text_body='%s', interactive_id='%s', state=%s", text_body, interactive_id, user.state)

        # intercept commands
        lower = (text_body or "").lower().strip()
        if lower in ["book", "book consultation", "book consultation"]:
            start_booking_flow(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        if lower in ["cancel booking", "cancel"]:
            booking = bs.latest_user_booking(db, user.id)
            if not booking:
                send_text(wa_id, "No active booking to cancel.")
            else:
                booking.status = "CANCELLED"
                db.add(booking); db.commit()
                send_text(wa_id, "Your booking has been cancelled.")
            save_state(db, user, NORMAL)
            return jsonify({"status": "ok"}), 200

        # language change (if interactive_id startswith lang_)
        if interactive_id and interactive_id.startswith("lang_"):
            if handle_language_change(db, user, wa_id, interactive_id):
                return jsonify({"status": "ok"}), 200

        # booking suggestion button handling
        if interactive_id == "book_consult_now":
            start_booking_flow(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        # booking flow states handled
        if user.state in {ASK_NAME, ASK_CITY, ASK_CATEGORY, ASK_DATE, ASK_SLOT, WAITING_PAYMENT, ASK_RATING}:
            handle_booking_flow(db, user, wa_id, text_body, interactive_id)
            return jsonify({"status": "ok"}), 200

        # default: AI reply + maybe suggest consult
        send_typing_on(wa_id)
        reply = ai_reply(text_body, user)
        send_typing_off(wa_id)
        send_text(wa_id, reply)

        # after AI reply, maybe suggest consult
        lower_text = (text_body or "").lower()
        consult_keywords = ["fir", "police", "divorce", "fraud", "arrest", "bail", "custody", "property"]
        if any(k in lower_text for k in consult_keywords):
            send_buttons(
                wa_id,
                "Your issue looks important. I can connect you to a lawyer on call for ₹499. Book now?",
                [
                    {"id": "book_consult_now", "title": "Yes — Book Call"},
                    {"id": "consult_later", "title": "Not now"}
                ]
            )

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.exception("Error in webhook: %s", e)
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# ---------------------------
# Payment webhook to confirm booking (Razorpay example skeleton)
# ---------------------------
@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    """
    Endpoint to be called by payment provider after payment.
    Expecting JSON payload containing 'booking_id' (our DB id) and 'payment_id' or provider signature.
    This is a simple skeleton — adapt to your provider's webhook structure.
    """
    payload = request.get_json(force=True, silent=True) or {}
    logger.info("Payment webhook received: %s", payload)

    # Basic verification placeholder: replace with signature verification for production
    booking_id = payload.get("booking_id")
    payment_id = payload.get("payment_id")
    status = payload.get("status", "paid")

    db = get_db_session()
    try:
        if not booking_id or not payment_id:
            logger.warning("Missing booking_id or payment_id in webhook")
            return jsonify({"ok": False}), 400

        b = db.query(Booking).filter(Booking.id == int(booking_id)).first()
        if not b:
            return jsonify({"ok": False, "reason": "booking_not_found"}), 404

        # Mark booking confirmed if payment succeeded
        if status in ("paid", "successful", "captured"):
            b.status = "CONFIRMED"
            b.payment_id = payment_id
            db.add(b); db.commit()

            # notify user
            u = db.query(User).filter(User.id == b.user_id).first()
            if u:
                send_text(u.whatsapp_id, f"✅ Payment received. Your consultation on {b.date_str} at {bs.slot_code_to_readable(b.slot_str)} is confirmed. 🙂")
            return jsonify({"ok": True}), 200
        else:
            # payment failed
            b.status = "CANCELLED"
            db.add(b); db.commit()
            u = db.query(User).filter(User.id == b.user_id).first()
            if u:
                send_text(u.whatsapp_id, "⚠️ Payment failed or was cancelled. Please try again.")
            return jsonify({"ok": True}), 200
    except Exception:
        logger.exception("Error handling payment webhook")
        return jsonify({"ok": False}), 500
    finally:
        db.close()

# ---------------------------
# run server locally
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
