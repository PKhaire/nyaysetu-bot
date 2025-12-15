# app.py
import os
import json
import logging

# ⚠️ TEMPORARY DEV RESET (REMOVE AFTER USE)
RESET_DB = True  # set to False after first successful run

if RESET_DB:
    if os.path.exists("nyaysetu.db"):
        os.remove("nyaysetu.db")
        print("⚠️ DEV MODE: Existing SQLite DB removed")

FREE_AI_LIMIT = 5
FREE_AI_SOFT_PROMPT_AT = 4

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
    get_safe_section_title,
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
PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
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
        # FREE AI CHAT (BEFORE BOOKING)
        # -------------------------------
        if user.state == "NORMAL":
            # Booking keyword always allowed
            if lower_text in ["book consultation", "book consult", "consult", "lawyer"]:
                user.free_ai_count = 0
                db.commit()
        
                save_state(db, user, ASK_NAME)
                send_text(
                    wa_id,
                    "Great 👍\nPlease tell me your *full name*."
                )
                return jsonify({"status": "ok"}), 200
        
            # Ignore empty / status events
            if not text_body:
                return jsonify({"status": "ignored"}), 200
        
            # Hard limit reached
            if user.free_ai_count >= FREE_AI_LIMIT:
                send_text(
                    wa_id,
                    "I’ve shared general legal guidance so far.\n\n"
                    "For personalised advice specific to your case, "
                    "please book a consultation with our legal expert.\n\n"
                    "👉 Type *Book Consultation* to continue."
                )
                return jsonify({"status": "ok"}), 200
        
            # Free AI reply
            send_typing_on(wa_id)
            try:
                reply = ai_reply(text_body, user)
            except Exception:
                send_typing_off(wa_id)
                send_text(
                    wa_id,
                    "⚠️ Sorry, I’m having trouble responding right now.\n"
                    "Please try again."
                )
                return jsonify({"status": "ok"}), 200
        
            send_typing_off(wa_id)
        
            user.free_ai_count += 1
            db.commit()
        
            # Soft CTA after 4th reply
            if user.free_ai_count >= FREE_AI_SOFT_PROMPT_AT:
                reply += (
                    "\n\nℹ️ *Want personalised legal advice?*\n"
                    "You can book a consultation anytime.\n"
                    "👉 Type *Book Consultation*"
                )
        
            send_text(wa_id, reply)
            return jsonify({"status": "ok"}), 200
            
        # -------------------------------
        # Start booking
        # -------------------------------
        if lower_text in ["book consultation", "book consult", "consult", "lawyer"]:
            user.free_ai_count = 0
            db.commit()
        
            save_state(db, user, ASK_NAME)
            send_text(
                wa_id,
                "Great 👍\nPlease tell me your *full name*."
            )
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Ask Name 
        # -------------------------------
        if user.state == ASK_NAME:
            # ❌ Ignore empty / non-user / status events
            if not text_body or len(text_body.strip()) < 2:
                send_text(
                    wa_id,
                    "Please tell me your *full name* to continue 🙂"
                )
                return jsonify({"status": "ok"}), 200
        
            # ✅ Save valid name only
            user.name = text_body.strip()
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
                    preferred_state=detect_state_from_text(text_body)
                ),
                section_title="Indian States",
            )
        
            return jsonify({"status": "ok"}), 200
        
        # -------------------------------
        # Ask State (STRICT & SAFE)
        # -------------------------------
        if user.state == ASK_STATE:
            state_name = None
        
            # ---------------------------------
            # Pagination: "More states..."
            # ---------------------------------
            if interactive_id and interactive_id.startswith("state_page_"):
                page = int(interactive_id.replace("state_page_", ""))
        
                send_list_picker(
                    wa_id,
                    header="Select State",
                    body="Choose your state",
                    rows=build_state_list_rows(
                        page=page,
                        preferred_state=user.state_name,
                    ),
                    section_title="Indian States",
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # State selected from list
            # ---------------------------------
            if interactive_id and interactive_id.startswith("state_"):
                state_name = interactive_id.replace("state_", "")
        
            # ---------------------------------
            # Typed state fallback (only if text present)
            # ---------------------------------
            if not state_name and text_body:
                state_name = detect_state_from_text(text_body)
        
            # ---------------------------------
            # Still invalid → ask again
            # ---------------------------------
            if not state_name:
                send_text(
                    wa_id,
                    "Please select or type your *state* 🙂"
                )
                send_list_picker(
                    wa_id,
                    header="Select State",
                    body="Choose your state or tap More",
                    rows=build_state_list_rows(
                        page=1,
                        preferred_state=user.state_name,
                    ),
                    section_title="Indian States",
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Save & move forward
            # ---------------------------------
            user.state_name = state_name
            db.commit()
        
            save_state(db, user, ASK_DISTRICT)
        
            from services.location_service import get_safe_section_title
        
            send_list_picker(
                wa_id,
                header=f"Select district in {state_name}",
                body="Choose district",
                rows=build_district_list_rows(state_name),
                section_title=get_safe_section_title(state_name),
            )
        
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Ask District (STRICT & SAFE)
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
                        preferred_district=user.district_name,
                    ),
                    section_title=get_safe_section_title(user.state_name),
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # District selected from list (VALIDATE)
            # ---------------------------------
            if interactive_id and interactive_id.startswith("district_"):
                candidate = interactive_id.replace("district_", "")
        
                from services.location_service import get_districts_for_state
                if candidate in get_districts_for_state(user.state_name):
                    district = candidate
        
            # ---------------------------------
            # Typed district (FUZZY + STATE ONLY)
            # ---------------------------------
            if not district and text_body:
                from services.location_service import detect_district_in_state
        
                matched = detect_district_in_state(user.state_name, text_body)
        
                if matched:
                    district = matched
        
                    # Auto-correction notice
                    if matched.lower() != text_body.lower():
                        send_text(
                            wa_id,
                            f"ℹ️ Interpreted *{text_body}* as *{matched}*."
                        )
        
            # ---------------------------------
            # Ignore empty / status events
            # ---------------------------------
            if not district and not text_body:
                return jsonify({"status": "ignored"}), 200
        
            # ---------------------------------
            # Still invalid → force list
            # ---------------------------------
            if not district:
                send_text(
                    wa_id,
                    f"❌ Could not identify district *{text_body}* in {user.state_name}.\n"
                    "Please select from the list below 👇"
                )
                send_list_picker(
                    wa_id,
                    header=f"Select district in {user.state_name}",
                    body="Choose district",
                    rows=build_district_list_rows(user.state_name),
                    section_title=get_safe_section_title(user.state_name),
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Save & move forward
            # ---------------------------------
            user.district_name = district
            db.commit()
        
            save_state(db, user, ASK_CATEGORY)
            send_category_list(wa_id)
        
            return jsonify({"status": "ok"}), 200
        
        # -------------------------------
        # Category (STRICT & SAFE)
        # -------------------------------
        if user.state == ASK_CATEGORY:
            category = None
        
            # ---------------------------------
            # Category selected from list
            # ---------------------------------
            if interactive_id and interactive_id.startswith("cat_"):
                category = interactive_id.replace("cat_", "")
        
            # ---------------------------------
            # Ignore empty / status events
            # ---------------------------------
            if not category and not text_body:
                return jsonify({"status": "ignored"}), 200
        
            # ---------------------------------
            # Still invalid → ask again
            # ---------------------------------
            if not category:
                send_text(
                    wa_id,
                    "Please select a legal category from the list 👇"
                )
                send_category_list(wa_id)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Save category & move forward
            # ---------------------------------
            user.category = category
            db.commit()
        
            save_state(db, user, ASK_SUBCATEGORY)
            send_subcategory_list(wa_id, category)
        
            return jsonify({"status": "ok"}), 200
        # -------------------------------
        # Sub Category (STRICT & SAFE)
        # -------------------------------
        if user.state == ASK_SUBCATEGORY:
            # ---------------------------------
            # Ignore empty / status events
            # ---------------------------------
            if not interactive_id:
                return jsonify({"status": "ignored"}), 200
        
            if not interactive_id.startswith("subcat_"):
                send_text(
                    wa_id,
                    "Please select a sub-category from the list 👇"
                )
                send_subcategory_list(wa_id, user.category)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Safe parsing
            # Format: subcat_<category>_<subcategory>
            # ---------------------------------
            parts = interactive_id.split("_", 2)
            if len(parts) != 3:
                send_text(
                    wa_id,
                    "Invalid selection. Please choose a sub-category again 👇"
                )
                send_subcategory_list(wa_id, user.category)
                return jsonify({"status": "ok"}), 200
        
            _, category, subcategory = parts
        
            # ---------------------------------
            # Validate category consistency
            # ---------------------------------
            if category != user.category:
                send_text(
                    wa_id,
                    "Selected sub-category does not match your category. Please try again 👇"
                )
                send_subcategory_list(wa_id, user.category)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Save sub-category
            # ---------------------------------
            user.subcategory = subcategory
            db.commit()
        
            # 📊 Analytics (SAFE)
            from models import CategoryAnalytics
        
            record = (
                db.query(CategoryAnalytics)
                .filter_by(category=category, subcategory=subcategory)
                .first()
            )
        
            if record:
                record.count += 1
            else:
                db.add(
                    CategoryAnalytics(
                        category=category,
                        subcategory=subcategory,
                        count=1,
                    )
                )
        
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
        # Date (STRICT & SAFE)
        # -------------------------------
        if user.state == ASK_DATE:
            # ---------------------------------
            # Ignore empty / status events
            # ---------------------------------
            if not interactive_id:
                return jsonify({"status": "ignored"}), 200
        
            # ---------------------------------
            # Date selected from list
            # ---------------------------------
            if not interactive_id.startswith("date_"):
                send_text(
                    wa_id,
                    "Please select an appointment *date* from the list 👇"
                )
                return jsonify({"status": "ok"}), 200
        
            date_str = interactive_id.replace("date_", "").strip()
        
            # ---------------------------------
            # Validate date format
            # ---------------------------------
            from datetime import datetime
        
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                send_text(
                    wa_id,
                    "Invalid date selected. Please choose again 👇"
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Save date & move forward
            # ---------------------------------
            user.temp_date = date_str
            db.commit()

            save_state(db, user, ASK_SLOT)
        
            slots = generate_slots_calendar(date_str)
        
            # ---------------------------------
            # No slots available (buffer case)
            # ---------------------------------
            if not slots:
                send_text(
                    wa_id,
                    "⚠️ No available time slots for this date.\n"
                    "Please select another date 👇"
                )
                send_list_picker(
                    wa_id,
                    header="Select appointment date 👇",
                    body="Available dates",
                    rows=generate_dates_calendar(),
                    section_title="Next 7 days",
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Show slots
            # ---------------------------------
            user.temp_date = date_str
            db.commit()
            save_state(db, user, ASK_SLOT)
            send_list_picker(
                wa_id,
                header=f"Select time slot for {date_str}",
                body="Available time slots (IST)",
                rows=slots,
                section_title="Time Slots",
            )
        
            return jsonify({"status": "ok"}), 200
            
        # -------------------------------
        # Slot (STRICT & SAFE)
        # -------------------------------
        if user.state == ASK_SLOT:
            # ---------------------------------
            # Ignore empty / status events
            # ---------------------------------
            if not interactive_id:
                return jsonify({"status": "ignored"}), 200

            # ---------------------------------
            # SAFETY: User clicked a DATE again
            # ---------------------------------
            if interactive_id and interactive_id.startswith("date_"):
                save_state(db, user, ASK_DATE)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Validate slot selection
            # ---------------------------------
            if not interactive_id.startswith("slot_"):
                send_text(
                    wa_id,
                    "Please select a time slot from the list 👇"
                )
                return jsonify({"status": "ok"}), 200
        
            slot_code = interactive_id.replace("slot_", "").strip()
        
            # ---------------------------------
            # Validate slot exists
            # ---------------------------------
            if slot_code not in SLOT_MAP:
                send_text(
                    wa_id,
                    "Invalid time slot selected. Please choose again 👇"
                )
                send_list_picker(
                    wa_id,
                    header=f"Select time slot for {user.temp_date}",
                    body="Available time slots (IST)",
                    rows=generate_slots_calendar(user.temp_date),
                    section_title="Time Slots",
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Final safety check before booking
            # ---------------------------------
            required_fields = [
                user.name,
                user.state_name,
                user.district_name,
                user.category,
                user.temp_date,
            ]
        
            if not all(required_fields):
                send_text(
                    wa_id,
                    "⚠️ Some booking details are missing. Please restart booking."
                )
                save_state(db, user, ASK_NAME)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Attempt booking (includes buffer & expiry validation)
            # ---------------------------------
            booking, payment_link = create_booking_temp(
                db=db,
                user=user,
                name=user.name,
                state=user.state_name,
                district=user.district_name,
                category=user.category,
                date=user.temp_date,
                slot_code=slot_code,
            )
        
            # ---------------------------------
            # Booking validation failed
            # ---------------------------------
            if not booking:
                send_text(wa_id, f"⚠️ {payment_link}")
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Save & move to payment
            # ---------------------------------
            user.temp_slot = slot_code
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
                f"*Slot:* {SLOT_MAP[slot_code]}\n"
                f"*Fees:* ₹{BOOKING_PRICE} (one-time session) 🙂\n\n"
                f"Please complete payment:\n{payment_link}"
            )
        
            return jsonify({"status": "ok"}), 200
        
        
        # -------------------------------
        # Waiting payment (AI LOCKED)
        # -------------------------------
        if user.state == WAITING_PAYMENT:
            send_text(
                wa_id,
                f"💳 Your payment link is active:\n{user.last_payment_link}"
            )
            return jsonify({"status": "ok"}), 200 
            
        # -------------------------------
        # AI Chat (ONLY AFTER PAYMENT)
        # -------------------------------
        if user.state == PAYMENT_CONFIRMED:
            # Send session intro ONCE
            if not user.session_started:
                send_text(
                    wa_id,
                    "✅ *Payment received successfully.*\n\n"
                    "You may now ask your legal questions here.\n"
                    "Our legal expert will also call you at the scheduled date and time."
                )
                user.session_started = True
                db.commit()
                return jsonify({"status": "ok"}), 200
        
            if not text_body:
                return jsonify({"status": "ignored"}), 200
        
            send_typing_on(wa_id)
            try:
                reply = ai_reply(text_body, user)
            except Exception:
                send_typing_off(wa_id)
                send_text(
                    wa_id,
                    "⚠️ Sorry, I’m having trouble responding right now.\n"
                    "Please try again."
                )
                return jsonify({"status": "ok"}), 200
        
            send_typing_off(wa_id)
            send_text(wa_id, reply)
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Default fallback (safe)
        # -------------------------------
        return jsonify({"status": "ignored"}), 200
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

        # ✅ Move user to PAYMENT_CONFIRMED
        save_state(db, booking.user, PAYMENT_CONFIRMED)
            
        send_text(
            booking.whatsapp_id,
            "💳 Payment successful!\n\n"
            "Your booking is confirmed 🙂\n"
            "Our legal expert will call you at the scheduled date and time."
        )
        return jsonify({"status": "confirmed"}), 200
    finally:
        db.close()


# -------------------------------------------------
# Startup
# -------------------------------------------------
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
