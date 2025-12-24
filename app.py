import os
import json
import logging
import time
import hmac
import hashlib

from collections import defaultdict, deque
from datetime import datetime
from flask import Flask, request, jsonify

# ===============================
# TRANSLATIONS
# ===============================
from translations import TRANSLATIONS
from category_labels import CATEGORY_LABELS
from subcategory_labels import SUBCATEGORY_LABELS
# ===============================
# CONFIG
# ===============================
RESET_DB = True   # ⚠️ MUST BE FALSE IN PROD
#RESET_DB = ENV != "production"

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
    "help", "menu", "main menu", "home", "start",
    "cancel", "stop", "exit"
}

BOOKING_KEYWORDS = {
    "book consultation", "book consult", "consult", "lawyer"
}

CATEGORY_SUBCATEGORIES = {
    "Family": [
        "Divorce",
        "Maintenance and Alimony",
        "Domestic Violence",
        "Child Custody",
        "Dowry Harassment",
        "Other Family Matter",
        "Not Sure Need Guidance",
    ],

    "Criminal": [
        "Police Case or FIR",
        "Bail Matter",
        "Cyber Crime",
        "Theft or Assault",
        "False FIR",
        "Police Harassment",
        "Not Sure Need Guidance",
    ],

    "Accident": [
        "Road Accident",
        "Motor Accident Claim",
        "Injury Compensation",
        "Death Due to Accident",
        "Hit and Run Accident",
        "Not Sure Need Guidance",
    ],

    "Property": [
        "Property or Land Dispute",
        "Illegal Possession",
        "Builder Delay or Fraud",
        "Sale Deed or Agreement Issue",
        "Partition or Inheritance",
        "Injunction Case",
        "Not Sure Need Guidance",
    ],

    "Business": [
        "Cheque Bounce Case",
        "Money Recovery",
        "Contract Dispute",
        "Partnership Dispute",
        "Business Fraud",
        "Not Sure Need Guidance",
    ],

    "Job": [
        "Wrongful Termination",
        "Salary Not Paid",
        "Workplace Harassment",
        "Employment Issue",
        "PF or Gratuity Issue",
        "Not Sure Need Guidance",
    ],

    "Consumer": [
        "Consumer Complaint",
        "Refund Issue",
        "Online Fraud",
        "Service Deficiency",
        "Warranty Issue",
        "Not Sure Need Guidance",
    ],

    "Banking & Finance": [
        "Loan Recovery Harassment",
        "Fraudulent Transaction",
        "Credit Card Problem",
        "Bank Account Freeze",
        "Insurance Claim Issue",
        "Not Sure Need Guidance",
    ],

    "Other": [
        "General Legal Query",
        "Legal Notice Drafting",
        "Agreement Drafting",
        "Document Verification",
        "Not Sure Need Guidance",
    ],
}

# ===============================
# INIT
# ===============================
from db import SessionLocal, init_db
init_db()

from models import User, Booking
from config import WHATSAPP_VERIFY_TOKEN, BOOKING_PRICE, RAZORPAY_WEBHOOK_SECRET

from utils import format_date_readable
from services.whatsapp_service import (
    send_text, send_buttons,
    send_typing_on, send_typing_off,
    send_list_picker,
    send_payment_success_message,
    send_payment_receipt_pdf
)
from services.receipt_service import generate_pdf_receipt
from services.openai_service import ai_reply
from services.booking_service import (
    generate_dates_calendar,
    generate_slots_calendar,
    create_booking_temp,
    is_payment_already_processed,
    mark_booking_as_paid,
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

def send_category_list(wa_id, user):
    rows = [
        {
            "id": f"cat_{category.lower().replace(' ', '_').replace('&', 'and')}",
            # ✅ Use loop variable, NOT user.category
            "title": get_category_label(
                category.lower().replace(' ', '_').replace('&', 'and'),
                user
            ),
        }
        for category in CATEGORY_SUBCATEGORIES.keys()
    ]

    send_list_picker(
        wa_id,
        header=t(user, "select_category"),
        body=t(user, "choose_category"),
        section_title=t(user, "select_category"),
        rows=rows,
    )

def send_subcategory_list(wa_id, user, category):
    """
    Sends sub-categories strictly from CATEGORY_SUBCATEGORIES.
    Ensures 'General Legal Query' is always present.
    Category MUST be canonical key like: banking_and_finance
    """

    # ===============================
    # SAFETY GUARD — NEVER CRASH
    # ===============================
    if not category:
        logger.error(
            "send_subcategory_list called with category=None | wa_id=%s | state=%s",
            wa_id,
            user.state,
        )
        save_state(db, user, ASK_CATEGORY)
        send_category_list(wa_id, user)
        return

    # ===============================
    # NORMALIZE CATEGORY (DEFENSIVE)
    # ===============================
    # Handle accidental prefixes like "cat_banking_and_finance"
    if category.startswith("cat_"):
        category = category.replace("cat_", "", 1)

    # Display label (safe now)
    category_key = category.replace("_", " ").title()

    # ===============================
    # FETCH SUB-CATEGORIES
    # ===============================
    subcats = CATEGORY_SUBCATEGORIES.get(category_key, []).copy()

    # ✅ Ensure "General Legal Query" always exists
    if "General Legal Query" not in subcats:
        subcats.append("General Legal Query")

    # ===============================
    # BUILD WHATSAPP ROWS
    # ===============================
    rows = [
        {
            # ID FORMAT: subcat::<category_key>::<subcategory_key>
            "id": (
                "subcat::"
                f"{category}::"
                f"{sub.lower().replace(' ', '_').replace('/', '').replace('(', '').replace(')', '')}"
            ),
            # WhatsApp title limit = 24 chars
            "title": get_subcategory_label(sub, user)[:24],
        }
        for sub in subcats
    ]

    # ===============================
    # SEND LIST PICKER
    # ===============================
    send_list_picker(
        wa_id,
        header=f"{category_key} – {t(user, 'select_subcategory')}",
        body=t(user, "choose_subcategory"),
        section_title=t(user, "select_subcategory"),
        rows=rows,
    )

def parse_subcategory_id(interactive_id: str):
    """
    Expected format:
    subcat::<category_key>::<subcategory_key>
    Example:
    subcat::banking_and_finance::not_sure_need_guidance
    """
    if not interactive_id.startswith("subcat::"):
        return None, None

    parts = interactive_id.split("::")
    if len(parts) != 3:
        return None, None

    _, category, subcategory = parts
    return category, subcategory

def get_category_label(category_key, user):
    """
    category_key: canonical key (e.g. banking_and_finance)
    """
    lang = user.language or "en"

    display_key = (
        category_key
        .replace("_and_", " & ")
        .replace("_", " ")
        .title()
    )

    return CATEGORY_LABELS.get(display_key, {}).get(lang, display_key)

def get_subcategory_label(subcategory, user):
    lang = user.language or "en"
    return SUBCATEGORY_LABELS.get(subcategory, {}).get(lang, subcategory)

def t(user, key, **kwargs):
    """
    Translation helper with language normalization and safe fallback
    """

    # Normalize user.language → translation key
    lang_map = {
        "English": "en",
        "Hinglish": "hi",
        "Hindi": "hi",
        "Marathi": "mr",
        "en": "en",
        "hi": "hi",
        "mr": "mr",
    }

    lang = lang_map.get(user.language, "en")

    translations = TRANSLATIONS.get(lang, {})

    if key not in translations:
        logger.warning("⚠️ Missing translation: %s.%s", lang, key)

    text = translations.get(
        key,
        TRANSLATIONS["en"].get(key, key)
    )

    return text.format(**kwargs) if kwargs else text

def safe_header(text: str) -> str:
    # WhatsApp list headers do NOT allow markdown
    return (
        text
        .replace("*", "")
        .replace("_", "")
        .replace("~", "")
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
                send_text(wa_id, t(user, "payment_in_progress"))
                return jsonify({"status": "ok"}), 200

            user.state = NORMAL
            user.ai_enabled = False
            user.free_ai_count = 0
            user.temp_date = None
            user.temp_slot = None
            user.last_payment_link = None
            db.commit()

            send_text(wa_id, t(user, "restart"))
            return jsonify({"status": "ok"}), 200

        # ===============================
        # WELCOME
        # ===============================
        if user.state == NORMAL and lower_text in WELCOME_KEYWORDS:
            save_state(db, user, ASK_LANGUAGE)
            send_buttons(
                wa_id,
                t(user, "welcome", case_id=user.case_id),
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
                t(user, "rate_limit_exceeded")
            )
            return jsonify({"status": "ok"}), 200

        # ===============================
        # LANGUAGE SELECTION
        # ===============================
        if user.state == ASK_LANGUAGE:
            if interactive_id in ("lang_en", "lang_hi", "lang_mr"):
                user.language = interactive_id.replace("lang_", "")
                db.commit()
        
                # ✅ Marathi default state (prefill only)
                if user.language == "mr":
                    user.state_name = "Maharashtra"
                    user.auto_state_prefilled = True   # ⭐ ADD THIS LINE
        
                    # ✅ Marathi greeting — ONLY ONCE
                    if not getattr(user, "marathi_greeted", False):
                        send_text(
                            wa_id,
                            "🙏 जय महाराष्ट्र! 🇮🇳\n"
                            "आपण NyaySetu मध्ये स्वागत आहे ⚖️"
                        )
                        user.marathi_greeted = True
        
                    db.commit()
        
                save_state(db, user, ASK_AI_OR_BOOK)
        
                send_buttons(
                    wa_id,
                    t(user, "ask_ai_or_book"),
                    [
                        {"id": "opt_ai", "title": t(user, "ask_ai")},
                        {"id": "opt_book", "title": t(user, "book_consult")},
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
                send_text(wa_id, t(user, "ask_ai_prompt"))
                return jsonify({"status": "ok"}), 200

            if interactive_id == "opt_book":
                user.ai_enabled = False
                save_state(db, user, ASK_NAME)
                db.commit()
                send_text(wa_id, t(user, "ask_name"))
                return jsonify({"status": "ok"}), 200

        # ===============================
        # BOOKING KEYWORD (GLOBAL)
        # ===============================
        if lower_text in BOOKING_KEYWORDS or interactive_id == "book_now":
            user.ai_enabled = False
            user.free_ai_count = 0
            save_state(db, user, ASK_NAME)
            db.commit()
            send_text(wa_id, t(user, "ask_name"))
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
                    t(user, "free_limit_reached"),
                    [{"id": "book_now", "title": t(user, "book_consult")}],
                )
                return jsonify({"status": "ok"}), 200

            send_typing_on(wa_id)
            # -------------------------------
            # AI rate limiting
            # -------------------------------
            if is_ai_rate_limited(wa_id):
                send_text(wa_id, t(user, "ai_cooldown"))
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
                send_text(wa_id, t(user, "ask_name_retry"))
                return jsonify({"status": "ok"}), 200
        
            user.name = text_body.strip()
            db.commit()
        
            # ✅ Marathi users: auto-apply Maharashtra AFTER name
            if user.language == "mr":
                user.state_name = "Maharashtra"
                user.auto_state_applied = True
                db.commit()
        
                save_state(db, user, ASK_DISTRICT)
        
                send_list_picker(
                    wa_id,
                    header=t(user, "select_district_in", state=user.state_name),
                    body=t(user, "choose_district"),
                    rows=build_district_list_rows(user.state_name),
                    section_title=get_safe_section_title(user.state_name),
                )
                return jsonify({"status": "ok"}), 200
        
            # ✅ All other users → ask state
            save_state(db, user, ASK_STATE)
        
            send_list_picker(
                wa_id,
                header=safe_header(t(user, "select_state")),
                body=t(user, "choose_state"),
                rows=build_state_list_rows(page=1),
                section_title=t(user, "indian_states"),
            )
        
            return jsonify({"status": "ok"}), 200
    
        # -------------------------------
        # Ask State (STRICT & SAFE)
        # -------------------------------
        if user.state == ASK_STATE:
            state_name = None
        
            # ✅ Safety auto-skip (Marathi fallback only, no spam)
            if (
                user.language == "mr"
                and user.state_name == "Maharashtra"
                and getattr(user, "auto_state_applied", False)
                and not interactive_id
                and not text_body
            ):
                save_state(db, user, ASK_DISTRICT)
        
                send_list_picker(
                    wa_id,
                    header=t(user, "select_district_in", state=user.state_name),
                    body=t(user, "choose_district"),
                    rows=build_district_list_rows(user.state_name),
                    section_title=get_safe_section_title(user.state_name),
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Pagination
            # ---------------------------------
            if interactive_id and interactive_id.startswith("state_page_"):
                page = int(interactive_id.replace("state_page_", ""))
        
                send_list_picker(
                    wa_id,
                    header=safe_header(t(user, "select_state")),
                    body=t(user, "choose_state"),
                    rows=build_state_list_rows(
                        page=page,
                        preferred_state=user.state_name,
                    ),
                    section_title=t(user, "indian_states"),
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # State selected from list
            # ---------------------------------
            if interactive_id and interactive_id.startswith("state_"):
                state_name = interactive_id.replace("state_", "")
        
            # ---------------------------------
            # Typed fallback
            # ---------------------------------
            if not state_name and text_body:
                state_name = detect_state_from_text(text_body)
        
            # ---------------------------------
            # Invalid → retry
            # ---------------------------------
            if not state_name:
                send_text(wa_id, t(user, "ask_state_retry"))
                send_list_picker(
                    wa_id,
                    header=safe_header(t(user, "select_state")),
                    body=t(user, "choose_state"),
                    rows=build_state_list_rows(page=1),
                    section_title=t(user, "indian_states"),
                )
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Save & move forward
            # ---------------------------------
            user.state_name = state_name
            user.auto_state_applied = False
            db.commit()
        
            save_state(db, user, ASK_DISTRICT)
        
            send_list_picker(
                wa_id,
                header=t(user, "select_district_in", state=user.state_name),
                body=t(user, "choose_district"),
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
                    t(
                        user,
                        "district_invalid",
                        district=text_body,
                        state=user.state_name,
                    )
                )

                send_list_picker(
                    wa_id,
                    header=t(user, "select_district_in", state=user.state_name),
                    body=t(user, "choose_district"),
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
            send_category_list(wa_id, user)
        
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
                send_text(wa_id, t(user, "category_retry"))
                send_category_list(wa_id, user)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Save category & move forward
            # ---------------------------------
            
            user.category = category
            db.commit()
            
            save_state(db, user, ASK_SUBCATEGORY)
            
            # category is already normalized key
            send_subcategory_list(
                wa_id,
                user,
                user.category
            )

            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Sub Category (STRICT & SAFE)
        # -------------------------------
        if user.state == ASK_SUBCATEGORY:
        
            if not interactive_id:
                return jsonify({"status": "ignored"}), 200
        
            if not interactive_id.startswith("subcat::"):
                logger.info(
                    "Invalid subcategory input | wa_id=%s | id=%s",
                    wa_id,
                    interactive_id,
                )
                send_text(wa_id, t(user, "subcategory_retry"))
                send_subcategory_list(wa_id, user, user.category)
                return jsonify({"status": "ok"}), 200
        
            # Parse ID
            parsed_category, subcategory = parse_subcategory_id(interactive_id)
            expected_category = user.category
        
            if not expected_category:
                logger.error(
                    "Category missing during ASK_SUBCATEGORY | wa_id=%s",
                    wa_id,
                )
                save_state(db, user, ASK_CATEGORY)
                send_category_list(wa_id, user)
                return jsonify({"status": "ok"}), 200
        
            if not parsed_category or parsed_category != expected_category:
                send_text(wa_id, t(user, "subcategory_mismatch"))
                send_subcategory_list(wa_id, user, expected_category)
                return jsonify({"status": "ok"}), 200
        
            # Save subcategory
            user.subcategory = subcategory
            db.commit()
        
            # Analytics
            from models import CategoryAnalytics
            record = (
                db.query(CategoryAnalytics)
                .filter_by(category=parsed_category, subcategory=subcategory)
                .first()
            )
        
            if record:
                record.count += 1
            else:
                db.add(CategoryAnalytics(
                    category=parsed_category,
                    subcategory=subcategory,
                    count=1,
                ))
        
            db.commit()
        
            save_state(db, user, ASK_DATE)
        
            send_list_picker(
                wa_id,
                header=t(user, "select_date"),
                body=t(user, "available_dates"),
                rows=generate_dates_calendar(skip_today=True),
                section_title=t(user, "next_7_days"),
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
                send_text(wa_id, t(user, "select_date_retry"))
                return jsonify({"status": "ok"}), 200
        
            date_str = interactive_id.replace("date_", "").strip()
        
            # ---------------------------------
            # Validate date format
            # ---------------------------------
        
            try:
                selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                today = datetime.now().date()
            
                if selected_date <= today:
                    send_text(wa_id, t(user, "past_date_error"))
                    send_list_picker(
                        wa_id,
                        header=t(user, "select_date"),
                        body=t(user, "available_dates"),
                        rows=generate_dates_calendar(skip_today=True),
                        section_title="Next available days",
                    )
                    return jsonify({"status": "ok"}), 200
            
            except ValueError:
                send_text(wa_id, t(user, "invalid_date"))
                return jsonify({"status": "ok"}), 200
            # ---------------------------------
            # Save date & move forward
            # ---------------------------------
            
            slots = generate_slots_calendar(date_str)
            
            readable_date = format_date_readable(date_str)
            for slot in slots:
                if "description" in slot and slot["description"]:
                    slot["description"] = t(user, "available_on", date=readable_date)

            
            # ---------------------------------
            # No slots available (buffer case)
            # ---------------------------------
     
            if not slots:
                send_text(wa_id, t(user, "no_slots"))
                save_state(db, user, ASK_DATE)
        
                send_list_picker(
                    wa_id,
                    header=t(user, "select_date"),
                    body=t(user, "available_dates"),
                    rows=generate_dates_calendar(skip_today=True),
                    section_title="Next available days",
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
                header=f"{t(user, 'select_slot')} {format_date_readable(date_str)}",
                body=t(user, "available_slots"),
                rows=slots,
                section_title=t(user, "time_slots"),
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
            if interactive_id.startswith("date_"):
                save_state(db, user, ASK_DATE)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Validate slot selection
            # ---------------------------------
            if not interactive_id.startswith("slot_"):
                send_text(wa_id, t(user, "slot_retry"))
                return jsonify({"status": "ok"}), 200
        
            slot_code = interactive_id.replace("slot_", "").strip()
        
            # ---------------------------------
            # Validate slot exists
            # ---------------------------------
            if slot_code not in SLOT_MAP:
                send_text(wa_id, t(user, "invalid_slot"))
                send_list_picker(
                    wa_id,
                    header=f"Select time slot for {format_date_readable(user.temp_date)}",
                    body=t(user, "available_slots"),
                    rows=generate_slots_calendar(user.temp_date),
                    section_title=t(user, "time_slots"),
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
                send_text(wa_id, t(user, "booking_missing"))
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
                        
            # ---------------------------------
            # SAFE derivation for summary
            # ---------------------------------
            readable_date = (
                format_date_readable(user.temp_date)
                if user.temp_date else "N/A"
            )
            
            slot_text = SLOT_MAP.get(slot_code, "N/A")
            
            # ---------------------------------
            # Appointment Summary (SAFE)
            # ---------------------------------
            send_text(
                wa_id,
                t(
                    user,
                    "appointment_summary",
                    name=getattr(user, "full_name", None)
                         or getattr(user, "name", "N/A"),
                    state=user.state_name or "N/A",
                    district=user.district_name or "N/A",
                    category=get_category_label(user.category, user),
                    date=readable_date,
                    slot=slot_text,
                    amount=499,
                )
            )
            
            # ---------------------------------
            # SEND PAYMENT LINK (CRITICAL FIX)
            # ---------------------------------
            if user.last_payment_link:
                send_text(
                    wa_id,
                    f"💳 {t(user, 'payment_link_text')}\n{user.last_payment_link}"
                )
            else:
                logger.error(
                    "Payment link missing | wa_id=%s | user_id=%s",
                    wa_id,
                    user.id,
                )
                send_text(
                    wa_id,
                    t(user, "payment_link_error")
                )
            
            save_state(db, user, WAITING_PAYMENT)
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Waiting payment (SAFE & NON-SPAM)
        # -------------------------------
        if user.state == WAITING_PAYMENT:
        
            # Only respond if user sends actual text
            if text_body:
                if user.last_payment_link:
                    send_text(
                        wa_id,
                        f"💳 {t(user, 'payment_link_text')}\n{user.last_payment_link}"
                    )
                else:
                    send_text(
                        wa_id,
                        t(user, "payment_link_error")
                    )
        
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # AI Chat (ONLY AFTER PAYMENT)
        # -------------------------------
        if user.state == PAYMENT_CONFIRMED:
            # Send session intro ONCE
            if not user.session_started:
                send_text(wa_id, t(user, "session_start"))
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
        safe_wa_id = wa_id[:5] + "*****" + wa_id[-2:]
        logger.exception("Webhook error for wa_id=%s", safe_wa_id)
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

# ===============================
# PAYMENT WEBHOOK
# ===============================
@app.route("/payment/webhook", methods=["POST"])
def payment_webhook():
    try:
        # -------------------------------------------------
        # 1. Read RAW payload (required for HMAC)
        # -------------------------------------------------
        payload = request.data
        data = json.loads(payload.decode("utf-8"))

        # -------------------------------------------------
        # 2. Detect mode
        # -------------------------------------------------
        razorpay_mode = os.getenv("RAZORPAY_MODE", "live")
        if razorpay_mode not in ("test", "live"):
            logger.critical("❌ Invalid RAZORPAY_MODE")
            return "Server misconfiguration", 500

        signature = request.headers.get("X-Razorpay-Signature")

        # -------------------------------------------------
        # 3. SECURITY GATE
        # -------------------------------------------------
        if razorpay_mode == "live":
            if not signature:
                return "Signature missing", 400

            secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").encode()
            expected_signature = hmac.new(
                secret, payload, hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(expected_signature, signature):
                return "Invalid signature", 400
        else:
            user_agent = request.headers.get("User-Agent", "")
            if "Razorpay-Webhook" not in user_agent:
                return "Forbidden", 403

        # -------------------------------------------------
        # 4. Accept ONLY final payment event
        # -------------------------------------------------
        if data.get("event") != "payment_link.paid":
            return "Ignored", 200

        # -------------------------------------------------
        # 5. Extract payment details
        # -------------------------------------------------
        payment = data["payload"]["payment"]["entity"]
        payment_link = data["payload"]["payment_link"]["entity"]

        payment_id = payment["id"]
        payment_status = payment["status"]
        payment_link_id = payment_link["id"]
        payment_link_status = payment_link["status"]

        paid_amount = payment.get("amount")      # paise
        paid_currency = payment.get("currency") # INR

        # -------------------------------------------------
        # 6. FINAL CONFIRMATION CHECK
        # -------------------------------------------------
        if razorpay_mode == "live":
            confirmed = (
                payment_status == "captured"
                and payment_link_status == "paid"
            )
        else:
            confirmed = (
                payment_status == "captured"
                or payment_link_status == "paid"
            )

        if not confirmed:
            return "Not finalized", 200

        # -------------------------------------------------
        # 7. AMOUNT + CURRENCY VALIDATION (MANDATORY)
        # -------------------------------------------------
        EXPECTED_AMOUNT = int(BOOKING_PRICE * 100)

        if paid_currency != "INR" or paid_amount != EXPECTED_AMOUNT:
            logger.error(
                "❌ Amount mismatch | expected=%s | got=%s %s",
                EXPECTED_AMOUNT,
                paid_amount,
                paid_currency
            )
            return "Amount mismatch", 400

        # -------------------------------------------------
        # 8. IDEMPOTENCY CHECK (DB LEVEL)
        # -------------------------------------------------
        db = get_db()
        try:
            existing = (
                db.query(Booking)
                .filter(Booking.razorpay_payment_id == payment_id)
                .first()
            )
            if existing:
                logger.info(
                    "🔁 Duplicate webhook ignored | payment_id=%s",
                    payment_id
                )
                return "OK", 200
        finally:
            db.close()

        # -------------------------------------------------
        # 9. ATOMIC PAYMENT CONFIRMATION
        # -------------------------------------------------
        booking = mark_booking_as_paid(
            payment_link_id=payment_link_id,
            payment_id=payment_id,
            payment_mode=razorpay_mode
        )

        if not booking:
            return "Ignored", 200

        # -------------------------------------------------
        # 10. SIDE EFFECTS (AFTER COMMIT)
        # -------------------------------------------------
        try:
            send_payment_success_message(booking)
            pdf_path = generate_pdf_receipt(booking)
            send_payment_receipt_pdf(
                booking.whatsapp_id,
                pdf_path
            )
        except Exception:
            logger.exception(
                "⚠️ Receipt failed but payment confirmed | booking_id=%s",
                booking.id
            )

        logger.info("✅ PAYMENT CONFIRMED & BOOKING UPDATED")
        return "OK", 200

    except Exception:
        logger.exception("🔥 Razorpay webhook processing error")
        return "Internal error", 500
