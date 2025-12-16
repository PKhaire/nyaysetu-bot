import os
import json
import logging
import time
from collections import defaultdict, deque
from datetime import datetime
from flask import Flask, request, jsonify

# ===============================
# CONFIG
# ===============================
RESET_DB = True   # ⚠️ MUST BE FALSE IN PROD

if RESET_DB:
    if os.path.exists("nyaysetu.db"):
        os.remove("nyaysetu.db")
        print("⚠️ DEV MODE: Existing SQLite DB removed")

FREE_AI_LIMIT = 5
FREE_AI_SOFT_PROMPT_AT = 4
# ===============================
# RATE LIMITING CONFIG
# ===============================
USER_MSG_LIMIT = 10          # messages per user
USER_MSG_WINDOW = 60         # seconds
AI_CALL_COOLDOWN = 2         # seconds between AI calls
GLOBAL_REQ_LIMIT = 100       # total requests
GLOBAL_REQ_WINDOW = 60       # seconds

# ===============================
# RATE LIMITING STORES (IN-MEMORY)
# ===============================
user_message_times = defaultdict(lambda: deque())
user_last_ai_call = {}
global_request_times = deque()

WELCOME_KEYWORDS = {"hi", "hello", "hey", "start"}

RESTART_KEYWORDS = {
    "restart", "reset", "start over", "begin again",
    "help", "menu", "main menu", "home",
    "cancel", "stop", "exit"
}

BOOKING_KEYWORDS = {
    "book consultation", "book consult", "consult", "lawyer"
}

# ===============================
# INIT
# ===============================
from db import SessionLocal, init_db
init_db()

from models import User, Booking
from config import WHATSAPP_VERIFY_TOKEN, BOOKING_PRICE
from utils import format_date_readable
from services.whatsapp_service import (
    send_text, send_buttons,
    send_typing_on, send_typing_off,
    send_list_picker
)
from services.openai_service import ai_reply
from services.booking_service import (
    generate_dates_calendar,
    generate_slots_calendar,
    create_booking_temp,
    confirm_booking_after_payment,
    SLOT_MAP
)
from services.location_service import (
    detect_state_from_text,
    build_state_list_rows,
    build_district_list_rows,
    get_safe_section_title
)

# ===============================
# APP
# ===============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = Flask(__name__)

# ===============================
# STATES
# ===============================
NORMAL = "NORMAL"
ASK_LANGUAGE = "ASK_LANGUAGE"
ASK_AI_OR_BOOK = "ASK_AI_OR_BOOK"
ASK_NAME = "ASK_NAME"
ASK_STATE = "ASK_STATE"
ASK_DISTRICT = "ASK_DISTRICT"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_SUBCATEGORY = "ASK_SUBCATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"
PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"

# ===============================
# HELPERS
# ===============================
def get_db():
    return SessionLocal()

def save_state(db, user, state):
    user.state = state
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
            language=None,
            state=NORMAL,
            ai_enabled=False,
            free_ai_count=0,
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# ===============================
# RATE LIMIT HELPERS
# ===============================
def is_user_rate_limited(wa_id):
    now = time.time()
    times = user_message_times[wa_id]

    while times and now - times[0] > USER_MSG_WINDOW:
        times.popleft()

    if len(times) >= USER_MSG_LIMIT:
        return True

    times.append(now)
    return False


def is_ai_rate_limited(wa_id):
    now = time.time()
    last_call = user_last_ai_call.get(wa_id, 0)

    if now - last_call < AI_CALL_COOLDOWN:
        return True

    user_last_ai_call[wa_id] = now
    return False


def is_global_rate_limited():
    now = time.time()

    while global_request_times and now - global_request_times[0] > GLOBAL_REQ_WINDOW:
        global_request_times.popleft()

    if len(global_request_times) >= GLOBAL_REQ_LIMIT:
        return True

    global_request_times.append(now)
    return False

# =================================================
# CATEGORY & SUB-CATEGORY HELPERS
# =================================================

def send_category_list(wa_id):
    """
    Sends the main legal category list to the user
    """
    categories = [
        ("cat_family", "Family Law"),
        ("cat_criminal", "Criminal Law"),
        ("cat_civil", "Civil / Property"),
        ("cat_corporate", "Corporate / Business"),
        ("cat_labour", "Labour & Employment"),
        ("cat_consumer", "Consumer Protection"),
        ("cat_other", "Other Legal Issues"),
    ]

    rows = []
    for cid, title in categories:
        rows.append({
            "id": cid,
            "title": title,
            "description": ""
        })

    send_list_picker(
        wa_id,
        header="Select Legal Category",
        body="Choose the type of legal issue",
        rows=rows,
        section_title="Legal Categories",
    )

# =================================================
# SUB-CATEGORY HELPER (WITH GENERAL OPTION ALWAYS)
# =================================================

def send_subcategory_list(wa_id, category):
    """
    Sends sub-category list based on selected category.
    Always appends 'General Legal Query' as the last option.
    """
    subcategories_map = {
        "family": [
            ("subcat_divorce", "Divorce"),
            ("subcat_maintenance", "Maintenance / Alimony"),
            ("subcat_custody", "Child Custody"),
            ("subcat_domestic", "Domestic Violence"),
        ],
        "criminal": [
            ("subcat_bail", "Bail"),
            ("subcat_fir", "FIR / Police Case"),
            ("subcat_trial", "Criminal Trial"),
        ],
        "civil": [
            ("subcat_property", "Property Dispute"),
            ("subcat_agreement", "Agreement / Contract"),
            ("subcat_injunction", "Injunction"),
        ],
        "corporate": [
            ("subcat_company", "Company Matters"),
            ("subcat_compliance", "Compliance & Filings"),
            ("subcat_contract", "Business Contracts"),
        ],
        "labour": [
            ("subcat_termination", "Termination"),
            ("subcat_salary", "Salary Dispute"),
            ("subcat_hr", "Workplace / HR Issues"),
        ],
        "consumer": [
            ("subcat_complaint", "Consumer Complaint"),
            ("subcat_refund", "Refund / Deficiency"),
        ],
        "other": [],
    }

    # category value example: "cat_family"
    key = category.replace("cat_", "")
    items = subcategories_map.get(key, [])

    # ✅ Always add General Legal Query at the bottom
    items = items + [("subcat_general", "General Legal Query")]

    rows = []
    for sid, title in items:
        rows.append({
            "id": sid,
            "title": title,
            "description": ""
        })

    send_list_picker(
        wa_id,
        header="Select Sub-Category",
        body="Choose the specific issue",
        rows=rows,
        section_title="Legal Sub-Categories",
    )

# ===============================
# ROUTES
# ===============================
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Invalid token", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(force=True, silent=True) or {}

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
            interactive_id = message["interactive"][itype]["id"]
            text_body = interactive_id

        lower_text = text_body.lower().strip()
        # -------------------------------
        # Global rate limiting
        # -------------------------------
        if message["type"] in ("text", "interactive"):
            if is_global_rate_limited():
                return jsonify({"status": "rate_limited"}), 200
               
        # ===============================
        # RESTART
        # ===============================
        if lower_text in RESTART_KEYWORDS:
            if user.state == WAITING_PAYMENT:
                send_text(
                    wa_id,
                    "⚠️ Payment is in progress.\nPlease complete or wait."
                )
                return jsonify({"status": "ok"}), 200

            user.state = NORMAL
            user.language = None
            user.ai_enabled = False
            user.free_ai_count = 0
            user.temp_date = None
            user.temp_slot = None
            user.last_payment_link = None
            db.commit()

            send_text(wa_id, "🔄 Session reset.\nType *Hi* to start again.")
            return jsonify({"status": "ok"}), 200

        # ===============================
        # WELCOME
        # ===============================
        if user.state == NORMAL and lower_text in WELCOME_KEYWORDS:
            save_state(db, user, ASK_LANGUAGE)
            send_buttons(
                wa_id,
                f"👋 *Welcome to NyaySetu* ⚖️\n\n🆔 Case ID: {user.case_id}\n\nSelect language:",
                [
                    {"id": "lang_en", "title": "English"},
                    {"id": "lang_hi", "title": "Hinglish"},
                    {"id": "lang_mr", "title": "Marathi"},
                ],
            )
            return jsonify({"status": "ok"}), 200
            
        # -------------------------------
        # Per-user rate limiting
        # -------------------------------
        if is_user_rate_limited(wa_id):
            send_text(
                wa_id,
                "⏳ You’re sending messages too quickly.\n"
                "Please wait a moment and try again."
            )
            return jsonify({"status": "ok"}), 200

        # ===============================
        # LANGUAGE
        # ===============================
        if user.state == ASK_LANGUAGE:
            lang_map = {"lang_en": "English", "lang_hi": "Hinglish", "lang_mr": "Marathi"}
            if interactive_id in lang_map:
                user.language = lang_map[interactive_id]
                save_state(db, user, ASK_AI_OR_BOOK)
                send_buttons(
                    wa_id,
                    f"Language set to *{user.language}*\nHow would you like to proceed?",
                    [
                        {"id": "opt_ai", "title": "Ask AI"},
                        {"id": "opt_book", "title": "Book Consultation"},
                    ],
                )
            return jsonify({"status": "ok"}), 200

        # ===============================
        # AI OR BOOK
        # ===============================
        if user.state == ASK_AI_OR_BOOK:
            if interactive_id == "opt_ai":
                user.ai_enabled = True
                save_state(db, user, NORMAL)
                db.commit()
                send_text(wa_id, "🤖 Ask your legal question.")
                return jsonify({"status": "ok"}), 200

            if interactive_id == "opt_book":
                user.ai_enabled = False
                save_state(db, user, ASK_NAME)
                db.commit()
                send_text(wa_id, "Please tell me your *full name*.")
                return jsonify({"status": "ok"}), 200

        # ===============================
        # BOOKING KEYWORD (GLOBAL)
        # ===============================
        if lower_text in BOOKING_KEYWORDS or interactive_id == "book_now":
            user.ai_enabled = False
            user.free_ai_count = 0
            save_state(db, user, ASK_NAME)
            db.commit()
            send_text(wa_id, "Please tell me your *full name*.")
            return jsonify({"status": "ok"}), 200

        # ===============================
        # FREE AI CHAT
        # ===============================
        if user.state == NORMAL and user.ai_enabled:
            if not text_body:
                return jsonify({"status": "ignored"}), 200

            if user.free_ai_count >= FREE_AI_LIMIT:
                send_buttons(
                    wa_id,
                    "🚫 Free AI limit reached.\nPlease book a consultation.",
                    [{"id": "book_now", "title": "Book Consultation"}],
                )
                return jsonify({"status": "ok"}), 200

            send_typing_on(wa_id)
            # -------------------------------
            # AI rate limiting
            # -------------------------------
            if is_ai_rate_limited(wa_id):
                send_text(
                    wa_id,
                    "⏳ Please wait a moment before sending another message."
                )
                return jsonify({"status": "ok"}), 200

            reply = ai_reply(text_body, user)
            send_typing_off(wa_id)

            user.free_ai_count += 1
            db.commit()

            if user.free_ai_count == FREE_AI_SOFT_PROMPT_AT:
                reply += "\n\n⚖️ Need personalised advice?\nType *Book Consultation*."

            send_text(wa_id, reply)
            return jsonify({"status": "ok"}), 200

        # =================================================
        # BOOKING FLOW CONTINUATION
        # =================================================
        
        # -------------------------------
        # Ask Name
        # -------------------------------
        if user.state == ASK_NAME:
            if not text_body or len(text_body.strip()) < 2:
                send_text(wa_id, "Please enter your *full name* 🙂")
                return jsonify({"status": "ok"}), 200
        
            user.name = text_body.strip()
            save_state(db, user, ASK_STATE)
        
            send_text(
                wa_id,
                "Thanks 🙏\nWhich *state* are you in?"
            )
        
            send_list_picker(
                wa_id,
                header="Select State",
                body="Choose your state",
                rows=build_state_list_rows(page=1),
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
                    rows=build_state_list_rows(page=page),
                    section_title="Indian States",
                )
                return jsonify({"status": "ok"}), 200
        
            if interactive_id and interactive_id.startswith("state_"):
                state_name = interactive_id.replace("state_", "")
        
            if not state_name and text_body:
                state_name = detect_state_from_text(text_body)
        
            if not state_name:
                send_text(wa_id, "Please select or type your *state* 👇")
                send_list_picker(
                    wa_id,
                    header="Select State",
                    body="Choose your state",
                    rows=build_state_list_rows(page=1),
                    section_title="Indian States",
                )
                return jsonify({"status": "ok"}), 200
        
            user.state_name = state_name
            save_state(db, user, ASK_DISTRICT)
        
            send_list_picker(
                wa_id,
                header=f"Select district in {state_name}",
                body="Choose your district",
                rows=build_district_list_rows(state_name),
                section_title=get_safe_section_title(state_name),
            )
            return jsonify({"status": "ok"}), 200
        
        
        # -------------------------------
        # Ask District
        # -------------------------------
        if user.state == ASK_DISTRICT:
            district = None
        
            if interactive_id and interactive_id.startswith("district_page_"):
                page = int(interactive_id.replace("district_page_", ""))
                send_list_picker(
                    wa_id,
                    header=f"Select district in {user.state_name}",
                    body="Choose your district",
                    rows=build_district_list_rows(user.state_name, page=page),
                    section_title=get_safe_section_title(user.state_name),
                )
                return jsonify({"status": "ok"}), 200
        
            if interactive_id and interactive_id.startswith("district_"):
                district = interactive_id.replace("district_", "")
        
            if not district and text_body:
                from services.location_service import detect_district_in_state
                district = detect_district_in_state(user.state_name, text_body)
        
            if not district:
                send_text(
                    wa_id,
                    f"Please select a district in *{user.state_name}* 👇"
                )
                send_list_picker(
                    wa_id,
                    header=f"Select district in {user.state_name}",
                    body="Choose your district",
                    rows=build_district_list_rows(user.state_name),
                    section_title=get_safe_section_title(user.state_name),
                )
                return jsonify({"status": "ok"}), 200
        
            user.district_name = district
            save_state(db, user, ASK_CATEGORY)
            send_category_list(wa_id)
            return jsonify({"status": "ok"}), 200
        
        
        # -------------------------------
        # Ask Category
        # -------------------------------
        if user.state == ASK_CATEGORY:
            if interactive_id and interactive_id.startswith("cat_"):
                user.category = interactive_id.replace("cat_", "")
                save_state(db, user, ASK_SUBCATEGORY)
                send_subcategory_list(wa_id, user.category)
                return jsonify({"status": "ok"}), 200
        
            send_text(wa_id, "Please select a legal category 👇")
            send_category_list(wa_id)
            return jsonify({"status": "ok"}), 200
        
        # -------------------------------
        # Ask Sub-Category
        # -------------------------------
        if user.state == ASK_SUBCATEGORY:
            if not interactive_id or not interactive_id.startswith("subcat_"):
                send_text(wa_id, "Please select a sub-category 👇")
                send_subcategory_list(wa_id, user.category)
                return jsonify({"status": "ok"}), 200
        
            # interactive_id examples:
            # subcat_complaint
            # subcat_refund
            # subcat_general
            subcategory = interactive_id.replace("subcat_", "")
        
            user.subcategory = subcategory
            save_state(db, user, ASK_DATE)
        
            send_list_picker(
                wa_id,
                header="Select appointment date",
                body="Available dates",
                rows=generate_dates_calendar(skip_today=True),
                section_title="Next 7 days",
            )
            return jsonify({"status": "ok"}), 200

        
        # -------------------------------
        # Ask Date
        # -------------------------------
        if user.state == ASK_DATE:
            if not interactive_id or not interactive_id.startswith("date_"):
                send_text(wa_id, "Please select a date 👇")
                return jsonify({"status": "ok"}), 200
        
            date_str = interactive_id.replace("date_", "")
            user.temp_date = date_str
            save_state(db, user, ASK_SLOT)
        
            send_list_picker(
                wa_id,
                header=f"Select time slot for {format_date_readable(date_str)}",
                body="Available time slots (IST)",
                rows=generate_slots_calendar(date_str),
                section_title="Time Slots",
            )
            return jsonify({"status": "ok"}), 200
        
        
        # -------------------------------
        # Ask Slot
        # -------------------------------
        if user.state == ASK_SLOT:
            if not interactive_id or not interactive_id.startswith("slot_"):
                send_text(wa_id, "Please select a time slot 👇")
                return jsonify({"status": "ok"}), 200
        
            slot_code = interactive_id.replace("slot_", "")
        
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
        
            if not booking:
                send_text(wa_id, payment_link)
                return jsonify({"status": "ok"}), 200
        
            user.temp_slot = slot_code
            user.last_payment_link = payment_link
            save_state(db, user, WAITING_PAYMENT)
        
            send_text(
                wa_id,
                "✅ *Your appointment details:*\n"
                f"*Name:* {user.name}\n"
                f"*State:* {user.state_name}\n"
                f"*District:* {user.district_name}\n"
                f"*Category:* {user.category}\n"
                f"*Date:* {format_date_readable(user.temp_date)}\n"
                f"*Slot:* {SLOT_MAP[slot_code]}\n"
                f"*Fees:* ₹{BOOKING_PRICE}\n\n"
                f"💳 Complete payment:\n{payment_link}"
            )
            return jsonify({"status": "ok"}), 200
        
        
        # -------------------------------
        # Waiting for Payment
        # -------------------------------
        if user.state == WAITING_PAYMENT:
            send_text(
                wa_id,
                f"💳 Your payment link is active:\n{user.last_payment_link}"
            )
            return jsonify({"status": "ok"}), 200

    finally:
        db.close()

# ===============================
# PAYMENT WEBHOOK
# ===============================
@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    data = request.get_json(force=True) or {}
    token = data.get("payment_token")

    db = get_db()
    try:
        booking, msg = confirm_booking_after_payment(db, token)
        if not booking:
            return jsonify({"error": msg}), 404

        booking.user.ai_enabled = True
        booking.user.free_ai_count = 0
        save_state(db, booking.user, PAYMENT_CONFIRMED)

        send_text(
            booking.whatsapp_id,
            "💳 Payment successful.\nYour consultation is confirmed."
        )
        return jsonify({"status": "confirmed"}), 200
    finally:
        db.close()
