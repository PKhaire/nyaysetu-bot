# app.py
import os
import json
import logging

# ⚠️ TEMPORARY DEV RESET (REMOVE AFTER USE)
RESET_DB = False  # set to False after first successful run

if RESET_DB:
    if os.path.exists("nyaysetu.db"):
        os.remove("nyaysetu.db")
        print("⚠️ DEV MODE: Existing SQLite DB removed")

from datetime import datetime
from flask import Flask, request, jsonify
from db import SessionLocal, init_db
# 🔧 Initialize DB + migrations ON STARTUP
init_db()
from models import User, Booking
from config import (
    WHATSAPP_VERIFY_TOKEN,
    BOOKING_PRICE,
)
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
from services.location_service import (
    detect_state_from_text,
    detect_district_from_text,
    build_state_list_rows,
    build_district_list_rows,
    detect_country_from_wa_id,
)

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# -------------------------------------------------
# Flask App
# -------------------------------------------------
app = Flask(__name__)
# Initialize DB & run migrations ONCE
try:
    init_db()
    print("✅ Database initialized and migrated")
except Exception as e:
    print("❌ DB init failed:", e)

# -------------------------------------------------
# Conversation States
# -------------------------------------------------
NORMAL = "NORMAL"
ASK_LANGUAGE = "ASK_LANGUAGE"

SUGGEST_CONSULT = "SUGGEST_CONSULT"
ASK_NAME = "ASK_NAME"
ASK_STATE = "ASK_STATE"
ASK_DISTRICT = "ASK_DISTRICT"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"
ASK_RATING = "ASK_RATING"
ASK_SUBCATEGORY = "ASK_SUBCATEGORY"
CATEGORY_SUBCATEGORIES = {
    "FIR": [
        "Delay in FIR",
        "Police not registering FIR",
        "False FIR",
    ],
    "Police": [
        "Police harassment",
        "Illegal detention",
        "No action by police",
    ],
    "Property": [
        "Land dispute",
        "Builder fraud",
        "Illegal possession",
    ],
    "Family": [
        "Divorce",
        "Domestic violence",
        "Child custody",
    ],
    "Job": [
        "Wrongful termination",
        "Salary not paid",
        "Workplace harassment",
    ],
    "Business": [
        "Partnership dispute",
        "Cheque bounce",
        "Fraud",
    ],
    "Other": [],
}

# -------------------------------------------------
# DB Helpers
# -------------------------------------------------
def get_db():
    return SessionLocal()
    
def save_state(db, user, state):
    user.state = state
    db.add(user)
    db.commit()

def generate_case_id():
    import random, string
    return "NS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_or_create_user(db, wa_id):
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if not user:
        user = User(
            whatsapp_id=wa_id,
            case_id=generate_case_id(),
            language="English",
            state=NORMAL,
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def send_category_list(wa_id):
    send_list_picker(
        wa_id,
        header="Select Legal Category",
        body="Choose the category that best matches your issue",
        section_title="Legal Categories",
        rows=[
            {"id": "cat_FIR", "title": "FIR"},
            {"id": "cat_Police", "title": "Police"},
            {"id": "cat_Property", "title": "Property"},
            {"id": "cat_Family", "title": "Family"},
            {"id": "cat_Job", "title": "Job"},
            {"id": "cat_Business", "title": "Business"},
            {"id": "cat_Other", "title": "Other"},
        ],
    )

def send_subcategory_list(wa_id, category):
    subcats = CATEGORY_SUBCATEGORIES.get(category, []).copy()

    # ✅ Ensure General legal query for every category
    if "General legal query" not in subcats:
        subcats.insert(0, "General legal query")

    rows = [
        {
            "id": f"subcat_{category}_{sub}",
            "title": sub[:24],   # WhatsApp limit
        }
        for sub in subcats
    ]

    send_list_picker(
        wa_id,
        header=f"{category} – Select Sub-Category",
        body="Choose the issue type",
        section_title="Sub-Categories",
        rows=rows,
    )

# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return "NyaySetu backend running", 200


@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return challenge, 200

    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(force=True, silent=True) or {}
    logger.info("INCOMING PAYLOAD: %s", json.dumps(payload))

    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            return jsonify({"status": "ignored"}), 200

        message = messages[0]
        wa_id = value["contacts"][0]["wa_id"]
    except Exception:
        return jsonify({"status": "ignored"}), 200

    db = get_db()
    try:
        user = get_or_create_user(db, wa_id)

        text_body = ""
        interactive_id = None

        if message["type"] == "text":
            text_body = message["text"]["body"]
        elif message["type"] == "interactive":
            itype = message["interactive"]["type"]
            if itype == "button_reply":
                interactive_id = message["interactive"]["button_reply"]["id"]
                text_body = interactive_id
            elif itype == "list_reply":
                interactive_id = message["interactive"]["list_reply"]["id"]
                text_body = interactive_id

        lower_text = text_body.lower().strip()

        logger.info(
            "User=%s State=%s Text=%s",
            wa_id, user.state, text_body
        )

        # -------------------------------
        # Language Selection (FIRST TIME)
        # -------------------------------
        if user.state == NORMAL and not user.language:
            save_state(db, user, ASK_LANGUAGE)
            send_buttons(
                wa_id,
                "Welcome to *NyaySetu* ⚖️\nPlease select your language:",
                [
                    {"id": "lang_en", "title": "English"},
                    {"id": "lang_hi", "title": "Hinglish"},
                    {"id": "lang_mr", "title": "Marathi"},
                ],
            )
            return jsonify({"status": "ok"}), 200

        if user.state == ASK_LANGUAGE:
            lang_map = {
                "lang_en": "English",
                "lang_hi": "Hinglish",
                "lang_mr": "Marathi",
            }
            if interactive_id in lang_map:
                user.language = lang_map[interactive_id]
                save_state(db, user, NORMAL)
                send_text(
                    wa_id,
                    f"✅ Language set to *{user.language}*\n\nPlease tell me your legal issue."
                )
            return jsonify({"status": "ok"}), 200
        # -------------------------------
        # Start booking
        # -------------------------------
        if lower_text in ["book consultation", "book consult", "consult", "lawyer"]:
            save_state(db, user, ASK_NAME)
            send_text(wa_id, "Great 👍\nPlease tell me your *full name*.")
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Ask Name
        # -------------------------------
        if user.state == ASK_NAME:
            user.name = text_body
            db.commit()

            save_state(db, user, ASK_STATE)
            send_text(
                wa_id,
                "Thanks 🙏\nWhich *state* are you in?\n"
                "You can type or select from the list 👇"
            )
            send_list_picker(
                wa_id,
                header="Select State",
                body="Choose your state or tap More",
                rows=build_state_list_rows(
                    page=1,
                    preferred_state=user.state_name or detect_state_from_text(text_body)
                ),
                section_title="Indian States",
            )
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Ask State
        # -------------------------------
        if user.state == ASK_STATE:
            state_name = None

            if interactive_id and interactive_id.startswith("state_page_"):
                page = int(interactive_id.replace("state_page_", ""))
                send_list_picker(
                    wa_id,
                    header="Select State",
                    body="Choose your state",
                    rows=build_state_list_rows(
                        page=page,
                        preferred_state=user.state_name
                    ),
                    section_title="Indian States",
                )
                return jsonify({"status": "ok"}), 200

            if not state_name:
                state_name = detect_state_from_text(text_body)

            if not state_name:
                send_text(wa_id, "Please select or type your *state*.")
                return jsonify({"status": "ok"}), 200

            user.state_name = state_name
            db.commit()

            save_state(db, user, ASK_DISTRICT)
            send_list_picker(
                wa_id,
                header=f"Select district in {state_name}",
                body="Choose district",
                rows=build_district_list_rows(state_name),
                section_title=f"{state_name} districts",
            )
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Ask District
        # -------------------------------
        if user.state == ASK_DISTRICT:
            district = None

            # ---------------------------------
            # Pagination: "More districts..."
            # ---------------------------------
            if interactive_id and interactive_id.startswith("district_page_"):
                page = int(interactive_id.replace("district_page_", ""))

                send_list_picker(
                    wa_id,
                    header=f"Select district in {user.state_name}",
                    body="Choose your district",
                    rows=build_district_list_rows(
                                user.state_name,
                                page=page,
                                preferred_district=user.district_name
                    ),                    
                    section_title=f"{user.state_name} districts",
                )
                return jsonify({"status": "ok"}), 200

            # ---------------------------------
            # District selected from list
            # ---------------------------------
            if interactive_id and interactive_id.startswith("district_"):
                district = interactive_id.replace("district_", "")

            # ---------------------------------
            # Typed district fallback
            # ---------------------------------
            if not district:
                detected = detect_district_from_text(text_body)
                if detected:
                    _, district = detected

            # ---------------------------------
            # Still not detected
            # ---------------------------------
            if not district:
                send_text(
                    wa_id,
                    "Please select a district from the list or *type your district name*."
                )
                return jsonify({"status": "ok"}), 200

            # ---------------------------------
            # Save district & move forward
            # ---------------------------------
            user.district_name = district
            db.commit()

            save_state(db, user, ASK_CATEGORY)

            send_text(
                wa_id,
                "Got it 👍\nChoose your *legal category* "
                "(FIR, Police, Property, Family, Job, Business, Other)."
            )
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Category
        # -------------------------------
        if user.state == ASK_SUBCATEGORY:
            if not interactive_id or not interactive_id.startswith("subcat_"):
                send_text(wa_id, "Please select a sub-category from the list 👇")
                send_subcategory_list(wa_id, user.category)
                return jsonify({"status": "ok"}), 200
        
            # Extract sub-category
            _, category, subcategory = interactive_id.split("_", 2)
        
            user.subcategory = subcategory
            db.commit()
        
            # 📊 Analytics
            from models import CategoryAnalytics
        
            record = (
                db.query(CategoryAnalytics)
                .filter_by(category=category, subcategory=subcategory)
                .first()
            )
        
            if record:
                record.count += 1
            else:
                record = CategoryAnalytics(
                    category=category,
                    subcategory=subcategory,
                    count=1,
                )
                db.add(record)
        
            db.commit()
        
            save_state(db, user, ASK_DATE)
        
            send_list_picker(
                wa_id,
                header="Select appointment date 👇",
                body="Available dates",
                rows=generate_dates_calendar(),
                section_title="Next 7 days",
            )
            return jsonify({"status": "ok"}), 200


        # -------------------------------
        # Date
        # -------------------------------
        if user.state == ASK_DATE:
            if not interactive_id or not interactive_id.startswith("date_"):
                send_text(wa_id, "Please select a date from the list.")
                return jsonify({"status": "ok"}), 200

            user.temp_date = interactive_id.replace("date_", "")
            db.commit()

            save_state(db, user, ASK_SLOT)
            send_list_picker(
                wa_id,
                header=f"Select time slot for {user.temp_date}",
                body="Available time slots (IST)",
                rows=generate_slots_calendar(user.temp_date),
                section_title="Time Slots",
            )
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Slot
        # -------------------------------
        if user.state == ASK_SLOT:
            if not interactive_id or not interactive_id.startswith("slot_"):
                send_text(wa_id, "Please select a time slot from the list.")
                return jsonify({"status": "ok"}), 200

            slot_code = interactive_id.replace("slot_", "")
            user.temp_slot = slot_code
            db.commit()

            booking, payment_link = create_booking_temp(
                db=db,
                user=user,
                name=user.name,
                city=user.district_name,
                category=user.category,
                date_str=user.temp_date,
                slot_code=slot_code,
            )

            if not booking:
                send_text(wa_id, f"⚠️ {payment_link}")
                return jsonify({"status": "ok"}), 200

            user.last_payment_link = payment_link
            save_state(db, user, WAITING_PAYMENT)

            send_text(
                wa_id,
                "✅ *Your appointment details:*\n"
                f"*Name:* {user.name}\n"
                f"*State:* {user.state_name}\n"
                f"*District:* {user.district_name}\n"
                f"*Category:* {user.category}\n"
                f"*Date:* {user.temp_date}\n"
                f"*Slot:* {SLOT_MAP[slot_code]}\n"
                f"*Fees:* ₹{BOOKING_PRICE} (one-time session) 🙂\n\n"
                f"Please complete payment:\n{payment_link}"
            )
            return jsonify({"status": "ok"}), 200
        # -------------------------------
        # Waiting payment
        # -------------------------------
        if user.state == WAITING_PAYMENT:
            send_text(
                wa_id,
                f"💳 Your payment link is active:\n{user.last_payment_link}"
            )
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # AI Chat (Fallback)
        # -------------------------------
        send_typing_on(wa_id)
        reply = ai_reply(text_body, user)
        send_typing_off(wa_id)
        send_text(wa_id, reply)
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.exception("Webhook error")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# -------------------------------------------------
# Payment Webhook
# -------------------------------------------------
@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    data = request.get_json(force=True) or {}
    token = data.get("payment_token")

    if not token:
        return jsonify({"error": "missing token"}), 400

    db = get_db()
    try:
        booking, msg = confirm_booking_after_payment(db, token)
        if not booking:
            return jsonify({"error": msg}), 404

        send_text(
            booking.whatsapp_id,
            f"✅ Your booking on {booking.date} at {booking.slot_readable} is confirmed 🙂"
        )
        return jsonify({"status": "confirmed"}), 200
    finally:
        db.close()


# -------------------------------------------------
# Startup
# -------------------------------------------------
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
