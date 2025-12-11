# app.py
import os
import json
import logging
import difflib
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# DB & models
from db import create_all, SessionLocal
from models import User, Booking, Rating  # ensure User has state_name and district fields

# Config (use safe fallbacks)
from config import (
    WHATSAPP_VERIFY_TOKEN,
    BOOKING_PRICE,
    ADMIN_TOKEN,
    BOOKING_CUTOFF_HOURS,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
)

# Services
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
    SLOT_MAP,
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
ASK_CITY = "ASK_CITY"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"
ASK_RATING = "ASK_RATING"

# DB helper
def get_db_session():
    return SessionLocal()

# Case id helper
def generate_case_id(length=6):
    import random, string
    suffix = "".join(random.choices(string.hexdigits.upper(), k=length))
    return f"NS-{suffix}"

# Load India states & districts with caching
DATA_FILE = os.path.join(os.getcwd(), "india_districts.json")
try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        INDIA_DATA = json.load(f)
        logger.info("Loaded india_districts.json")
except Exception as e:
    INDIA_DATA = {}
    logger.warning("india_districts.json not found or invalid: %s", e)

ALL_STATES = sorted(list(INDIA_DATA.keys()))

# Prebuild cached rows for WhatsApp list pickers
_cached_state_rows = None
_cached_district_rows = {}  # state -> rows

def build_state_rows():
    global _cached_state_rows
    if _cached_state_rows is not None:
        return _cached_state_rows
    rows = []
    for state in ALL_STATES:
        rows.append({"id": f"state_{state}", "title": state, "description": ""})
    _cached_state_rows = [{"title": "India States", "rows": rows}]
    return _cached_state_rows

def build_district_rows(state):
    # cached per state
    if state in _cached_district_rows:
        return _cached_district_rows[state]
    districts = INDIA_DATA.get(state, [])
    rows = []
    for d in districts:
        rows.append({"id": f"dist_{d}", "title": d, "description": ""})
    payload = [{"title": f"Districts of {state}", "rows": rows}]
    _cached_district_rows[state] = payload
    return payload

# Utility: fuzzy match state/district from text
def detect_state_from_text(text, cutoff=0.7):
    if not text or not ALL_STATES:
        return None
    # get close matches (case-insensitive)
    candidates = difflib.get_close_matches(text, ALL_STATES, n=1, cutoff=cutoff)
    if candidates:
        return candidates[0]
    # try word-by-word
    words = [w.strip(",. ") for w in text.split()]
    for w in words:
        match = difflib.get_close_matches(w, ALL_STATES, n=1, cutoff=cutoff)
        if match:
            return match[0]
    return None

def detect_district_from_text(text, state=None, cutoff=0.7):
    districts = []
    if state:
        districts = INDIA_DATA.get(state, [])
    else:
        # flatten all districts
        for s in ALL_STATES:
            districts.extend(INDIA_DATA.get(s, []))
    if not text or not districts:
        return None
    candidates = difflib.get_close_matches(text, districts, n=1, cutoff=cutoff)
    if candidates:
        return candidates[0]
    words = [w.strip(",. ") for w in text.split()]
    for w in words:
        match = difflib.get_close_matches(w, districts, n=1, cutoff=cutoff)
        if match:
            return match[0]
    return None

# DB: get or create user
def get_or_create_user(db, wa_id: str) -> User:
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if not user:
        user = User(
            whatsapp_id=wa_id,
            case_id=generate_case_id(),
            language="English",
            query_count=0,
            state=NORMAL,
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Created new user %s with case_id=%s", wa_id, user.case_id)
    return user

def save_state(db, user: User, state: str):
    user.state = state
    db.add(user)
    db.commit()

# Consult keywords & helper
CONSULT_KEYWORDS = [
    "fir","police","zero fir","e-fir","efir",
    "domestic","violence","harassment",
    "theft","stolen","robbery",
    "dowry","498a",
    "custody","divorce","maintenance",
    "property","sale deed","agreement","possession",
    "fraud","cheated","scam",
    "arrest","bail","charge sheet",
]
YES_WORDS = {"yes","y","ok","okay","sure","book","book now","book call","need lawyer","want lawyer","talk to lawyer","consult now","help me"}
NO_WORDS = {"no","not now","later","dont want","don't want","no thanks"}

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
                {"id":"book_consult_now","title":"Yes — Book Call"},
                {"id":"consult_later","title":"Not now"},
            ],
        )

# Routes
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
    logger.info("INCOMING WHATSAPP PAYLOAD: %s", json.dumps(payload))
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
    except Exception:
        logger.error("Malformed payload")
        return jsonify({"status":"ignored"}), 200

    messages = value.get("messages")
    if not messages:
        logger.info("No user message — system event ignored")
        return jsonify({"status":"ignored"}), 200

    message = messages[0]
    wa_id = value["contacts"][0]["wa_id"]

    db = get_db_session()
    try:
        user = get_or_create_user(db, wa_id)

        msg_type = message.get("type")
        text_body = ""
        interactive_id = None

        # parse incoming
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
            return jsonify({"status":"ok"}), 200

        logger.info("Parsed text_body='%s', interactive_id='%s', state=%s", text_body, interactive_id, user.state)

        # Auto-detect state/district from free text (if user is in early flow or NORMAL)
        # This helps users who type "I am in Maharashtra, Pune" instead of picking lists.
        if text_body and user.state in {NORMAL, ASK_NAME, ASK_STATE, ASK_DISTRICT, ASK_CITY, ASK_CATEGORY}:
            # try detect state
            state_guess = detect_state_from_text(text_body)
            if state_guess and not getattr(user, "state_name", None):
                user.state_name = state_guess
                db.add(user); db.commit()
                logger.info("Auto-detected state %s for %s", state_guess, wa_id)
            # try detect district (prefer state-specific)
            district_guess = detect_district_from_text(text_body, state=user.state_name)
            if district_guess and not getattr(user, "district", None):
                user.district = district_guess
                db.add(user); db.commit()
                logger.info("Auto-detected district %s for %s", district_guess, wa_id)

        # Handle language buttons
        if interactive_id and interactive_id.startswith("lang_"):
            lang_map = {"lang_en":"English","lang_hinglish":"Hinglish","lang_mar":"Marathi"}
            if interactive_id in lang_map:
                user.language = lang_map[interactive_id]
                save_state(db, user, NORMAL)
                send_text(wa_id, f"Language updated to *{user.language}*.\n\nPlease type your legal issue.")
                return jsonify({"status":"ok"}), 200

        # Suggestion buttons
        if interactive_id == "book_consult_now":
            save_state(db, user, ASK_NAME)
            send_text(wa_id, "Great! Let's schedule your legal consultation call (₹499).\n\nFirst, please tell me your *full name*.")
            return jsonify({"status":"ok"}), 200
        if interactive_id == "consult_later":
            save_state(db, user, NORMAL)
            send_text(wa_id, "No problem 👍 You can type *Book Consultation* anytime.")
            return jsonify({"status":"ok"}), 200

        # Explicit booking keywords
        lower_text = (text_body or "").lower()
        if user.state in [NORMAL, SUGGEST_CONSULT] and any(kw in lower_text for kw in ["book", "consultation", "lawyer call", "appointment"]):
            save_state(db, user, ASK_NAME)
            send_text(wa_id, "Great! Let's schedule your legal consultation call (₹499).\n\nFirst, please tell me your *full name*.")
            return jsonify({"status":"ok"}), 200

        # Booking flow
        if user.state == ASK_NAME:
            user.name = (text_body or "").strip()
            db.add(user); db.commit()

            # If we already auto-detected state/district, skip to category; otherwise ask state
            if getattr(user, "state_name", None) and getattr(user, "district", None):
                save_state(db, user, ASK_CATEGORY)
                send_text(wa_id, "Great 👍 Now choose your *legal issue category* (e.g., FIR, Property, Family, Business, Other).")
            else:
                save_state(db, user, ASK_STATE)
                send_list_picker(
                    wa_id,
                    header="Select your State",
                    body="Choose your State from the list",
                    rows=build_state_rows(),
                    section_title="States of India",
                )
            return jsonify({"status":"ok"}), 200

        if user.state == ASK_STATE:
            # either interactive or try from text
            if interactive_id and interactive_id.startswith("state_"):
                selected_state = interactive_id.replace("state_", "", 1)
                user.state_name = selected_state
                db.add(user); db.commit()

                save_state(db, user, ASK_DISTRICT)
                send_list_picker(
                    wa_id,
                    header=f"Select District ({selected_state})",
                    body="Choose your district",
                    rows=build_district_rows(selected_state),
                    section_title="Districts",
                )
            else:
                # try fuzzy detect from text_body
                guessed = detect_state_from_text(text_body)
                if guessed:
                    user.state_name = guessed
                    db.add(user); db.commit()
                    save_state(db, user, ASK_DISTRICT)
                    send_list_picker(
                        wa_id,
                        header=f"Select District ({guessed})",
                        body="Choose your district",
                        rows=build_district_rows(guessed),
                        section_title="Districts",
                    )
                else:
                    send_text(wa_id, "Please select a state from the list I sent.")
            return jsonify({"status":"ok"}), 200

        if user.state == ASK_DISTRICT:
            if interactive_id and interactive_id.startswith("dist_"):
                selected_dist = interactive_id.replace("dist_", "", 1)
                user.district = selected_dist
                db.add(user); db.commit()
                save_state(db, user, ASK_CATEGORY)
                send_text(wa_id, "Great 👍\nPlease choose your *legal issue category* (e.g., FIR, Police, Property, Family, Job, Business, Other).")
            else:
                guessed = detect_district_from_text(text_body, state=getattr(user, "state_name", None))
                if guessed:
                    user.district = guessed
                    db.add(user); db.commit()
                    save_state(db, user, ASK_CATEGORY)
                    send_text(wa_id, "Great 👍\nPlease choose your *legal issue category* (e.g., FIR, Police, Property, Family, Job, Business, Other).")
                else:
                    send_text(wa_id, "Please select a district from the list I sent.")
            return jsonify({"status":"ok"}), 200

        if user.state == ASK_CATEGORY:
            user.category = (text_body or "").strip()
            db.add(user); db.commit()

            # now show dates
            rows = generate_dates_calendar()
            save_state(db, user, ASK_DATE)
            send_list_picker(
                wa_id,
                header="Select appointment date 👇",
                body="Available Dates",
                rows=rows,
                section_title="Next 7 days",
            )
            return jsonify({"status":"ok"}), 200

        if user.state == ASK_DATE:
            if interactive_id and interactive_id.startswith("date_"):
                user.temp_date = interactive_id.replace("date_", "", 1)
                db.add(user); db.commit()
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
            return jsonify({"status":"ok"}), 200

        if user.state == ASK_SLOT:
            if interactive_id and interactive_id.startswith("slot_"):
                # code-only (e.g. "8_9")
                slot_code = interactive_id.replace("slot_", "", 1)
                user.temp_slot = slot_code
                db.add(user); db.commit()

                # build booking context
                name = getattr(user, "name", "Client")
                city = getattr(user, "city", "NA")
                category = getattr(user, "category", "General")
                state_name = getattr(user, "state_name", None)
                district = getattr(user, "district", None)
                date = getattr(user, "temp_date", None)
                slot = slot_code

                # Server-side validation rules example:
                # 1) slot not in the past
                # 2) respect BOOKING_CUTOFF_HOURS (if set)
                # 3) don't double-book same slot (your create_booking_temp should enforce too)

                # Basic "already started" check
                try:
                    # slot readable -> approximate start hour
                    # Expect slot codes like "10_11","12_1","3_4","6_7","8_9"
                    hour_part = int(slot.split("_")[0])
                    # map to 24h for PM where needed, use simple heuristic: if hour < 8 treat as PM? (booking_service can provide better)
                    # We will rely on generate_slots_calendar to produce valid slots; still do minimal check:
                    now = datetime.utcnow() + timedelta(hours=5, minutes=30)  # IST now approximation
                    slot_start_dt = datetime.strptime(date, "%Y-%m-%d").replace(hour=hour_part, minute=0, second=0, microsecond=0)
                    # If slot_start_dt < now -> cannot book
                    if slot_start_dt < now:
                        send_text(wa_id, "⚠️ Cannot book a slot that has already started or passed.")
                        return jsonify({"status":"ok"}), 200
                except Exception:
                    # non-fatal: proceed to create booking and let booking_service validate further
                    logger.debug("Unable to compute slot start time for validation", exc_info=True)

                booking, result = create_booking_temp(db, user, name, city, category, date, slot)
                if not booking:
                    # result contains a reason string
                    send_text(wa_id, f"⚠️ {result}")
                    return jsonify({"status":"ok"}), 200

                payment_link = result
                user.last_payment_link = payment_link
                save_state(db, user, WAITING_PAYMENT)

                send_text(wa_id,
                          "✅ *Your appointment details:*\n"
                          f"*Name:* {name}\n"
                          f"*State:* {state_name or 'NA'}\n"
                          f"*District:* {district or 'NA'}\n"
                          f"*City:* {city}\n"
                          f"*Category:* {category}\n"
                          f"*Date:* {date}\n"
                          f"*Slot:* {SLOT_MAP.get(slot, slot)}\n"
                          f"*Fees:* ₹{BOOKING_PRICE} (single session only) 🙂\n\n"
                          f"Please complete payment using this link:\n{payment_link}"
                          )
            else:
                send_text(wa_id, "Please select a time slot from the list I sent. If you didn't receive it, type *Book Consultation* to restart booking.")
            return jsonify({"status":"ok"}), 200

        if user.state == WAITING_PAYMENT:
            send_text(wa_id, f"💳 Your payment link is still active: {getattr(user, 'last_payment_link', 'not found')}")
            return jsonify({"status":"ok"}), 200

        # Suggest consult yes/no handling
        if user.state == SUGGEST_CONSULT:
            if lower_text in YES_WORDS:
                save_state(db, user, ASK_NAME)
                send_text(wa_id, "Great — first, please tell your full name.")
                return jsonify({"status":"ok"}), 200
            if lower_text in NO_WORDS:
                save_state(db, user, NORMAL)
                send_text(wa_id, "Sure. You can type anything to continue chatting.")
                return jsonify({"status":"ok"}), 200

        # Normal AI chat fallback
        send_typing_on(wa_id)
        ai_answer = ai_reply(text_body, user)
        send_typing_off(wa_id)
        send_text(wa_id, ai_answer)
        maybe_suggest_consult(db, user, wa_id, text_body)
        return jsonify({"status":"ok"}), 200

    except Exception as e:
        logger.exception("Error handling webhook")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# Payment webhook (confirm booking after payment)
@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    data = request.get_json(force=True, silent=True) or {}
    token = data.get("payment_token") or data.get("token") or ""
    if not token:
        return jsonify({"error":"missing token"}), 400
    db = get_db_session()
    try:
        booking, status = confirm_booking_after_payment(db, token)
        if not booking:
            return jsonify({"error": status}), 404
        # send confirmation WhatsApp (if booking has whatsapp_id)
        try:
            if getattr(booking, "whatsapp_id", None):
                send_text(booking.whatsapp_id, f"✅ Your booking for {booking.date} {getattr(booking, 'slot_readable', '')} is confirmed. See you then 🙂")
        except Exception:
            logger.exception("Failed to send confirmation WhatsApp")
        return jsonify({"status":"confirmed", "booking_id": booking.id}), 200
    finally:
        db.close()

# Debug endpoint: return a sample WhatsApp list payload (Ready UI preview / screenshot JSON)
@app.route("/ui_preview", methods=["GET"])
def ui_preview():
    kind = request.args.get("kind", "states")  # 'states' or 'districts'
    state = request.args.get("state")
    if kind == "states":
        payload = {
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type":"text", "text":"Select your State"},
                "body": {"text":"Choose your state"},
                "action": {"button":"Select", "sections": build_state_rows()}
            }
        }
        return jsonify(payload), 200
    elif kind == "districts" and state:
        payload = {
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type":"text", "text":f"Select District ({state})"},
                "body": {"text":"Choose your district"},
                "action": {"button":"Select", "sections": build_district_rows(state)}
            }
        }
        return jsonify(payload), 200
    else:
        return jsonify({"error":"missing state for districts preview"}), 400

if __name__ == "__main__":
    # run migrations & app
    with app.app_context():
        try:
            logger.info("🔧 Running DB migrations...")
            create_all()
            logger.info("✅ DB tables ready.")
        except Exception as e:
            logger.exception("DB migration failed")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
