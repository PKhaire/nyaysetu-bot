import os
import json
import logging
import time as time_module
import hmac
import hashlib
import re
import unicodedata

from threading import Thread
from collections import defaultdict, deque
from datetime import datetime, time as dt_time, timedelta
from flask import Flask, request, jsonify, send_file
from config import ENV, WHATSAPP_VERIFY_TOKEN, BOOKING_PRICE, RAZORPAY_WEBHOOK_SECRET
from location_service import detect_district_and_state
from models import User, Booking
from db import engine, SessionLocal, init_db
from sqlalchemy import inspect, text
init_db()

# ===============================
# APP
# ===============================
logging.basicConfig(
    level=logging.DEBUG if os.getenv("LOG_LEVEL") == "DEBUG" else logging.INFO
)
logger = logging.getLogger("app")

app = Flask(__name__)

# =================================================
# DB RESET (EXPLICIT ONLY — NEVER AUTOMATIC)
# =================================================
RESET_DB = os.getenv("RESET_DB", "false").lower() == "true"  # ⚠️ MUST BE FALSE IN PROD HARD CODED

if RESET_DB:
    db_path = engine.url.database
    if db_path and os.path.exists(db_path):
        os.remove(db_path)
        print(f"⚠️ MANUAL DB RESET DONE at {db_path}")

# =================================================
# DB PRINT  (DEBUG== true)
# =============================================
def log_entire_database():
    logger.info("========== DB DUMP START ==========")

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if not tables:
        logger.info("No tables found in DB")
        return

    with engine.connect() as connection:
        for table in tables:
            logger.info("----- TABLE: %s -----", table)

            try:
                result = connection.execute(text(f"SELECT * FROM {table}"))
                rows = result.fetchall()

                if not rows:
                    logger.info("Table %s is EMPTY", table)
                    continue

                for idx, row in enumerate(rows, start=1):
                    logger.info("[%s][ROW %d] %s", table, idx, dict(row._mapping))

            except Exception:
                logger.exception("Failed to read table %s", table)

    logger.info("========== DB DUMP END ==========")

DEBUG_DB_LOG = os.getenv("DEBUG", "false").lower() == "true"
DB_DUMP_DONE_FLAG = "/tmp/db_dump_done.flag"

if DEBUG_DB_LOG:
    if not os.path.exists(DB_DUMP_DONE_FLAG):
        logger.warning(
            "⚠️ DEBUG=true → Dumping entire database to logs (ONCE per container)"
        )
        log_entire_database()

        # Mark dump as done
        try:
            with open(DB_DUMP_DONE_FLAG, "w") as f:
                f.write(str(datetime.utcnow()))
        except Exception:
            logger.exception("Failed to create DB dump flag file")
    else:
        logger.debug(
            "DB dump already performed for this container — skipping"
        )

# ===============================
# TRANSLATIONS
# ===============================
from translations import TRANSLATIONS
from category_labels import CATEGORY_LABELS
from subcategory_labels import SUBCATEGORY_LABELS

# ===============================
# CONFIG
# ===============================
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

WELCOME_KEYWORDS = {"hi","hii","hie", "hello", "hey", "start"}

RESTART_KEYWORDS = {
    "restart", "reset", "start over", "begin again",
    "help", "menu", "main menu", "home",
    "cancel", "stop", "exit"
}

BOOKING_KEYWORDS = {
    "book consultation", "book consult", "consult", "lawyer"
}

CATEGORY_SUBCATEGORIES = {
    "Family": [
        "Divorce",
        "Separation",
        "Maintenance",
        "Alimony",
        "Domestic Violence",
        "Child Custody",
        "Dowry Case",
        "Other Family Issue",
        "Not Sure",
    ],

    "Criminal": [
        "Police Case",
        "Bail Matter",
        "Cyber Crime",
        "Theft or Assault",
        "False FIR",
        "Police Harassment",
        "Not Sure",
    ],

    "Accident": [
        "Road Accident",
        "MACT Claim",
        "Personal Injury",
        "Accidental Death",
        "Hit and Run",
        "Not Sure",
    ],

    "Property": [
        "Property Dispute",
        "Illegal Possession",
        "Builder Issue",
        "Sale Deed Issue",
        "Partition Dispute",
        "Injunction Matter",
        "Not Sure",
    ],

    "Business": [
        "Cheque Bounce",
        "Money Recovery",
        "Contract Dispute",
        "Partner Dispute",
        "Business Fraud",
        "Not Sure",
    ],

    "Job": [
        "Wrongful Termination",
        "Unpaid Salary",
        "Workplace Harassment",
        "Service Dispute",
        "PF or Gratuity Issue",
        "Not Sure",
    ],

    "Consumer": [
        "Consumer Complaint",
        "Refund Issue",
        "Online Fraud",
        "Service Deficiency",
        "Product Defect",
        "Not Sure",
    ],

    "Banking and Finance": [
        "Loan Harassment",
        "Unauthorized Transaction",
        "Loan or Card Dispute",
        "Account Freeze",
        "Insurance Claim",
        "Not Sure",
    ],

    "Other": [
        "General Legal Query",
        "Legal Notice",
        "Draft Agreement",
        "Document Review",
        "Not Sure",
    ],
}

# ===============================
# INIT
# ===============================
from utils.date_utils import format_date_readable
from utils.i18n import t
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

# ===============================
# STATES
# ===============================
NORMAL = "NORMAL"
ASK_LANGUAGE = "ASK_LANGUAGE"
ASK_AI_OR_BOOK = "ASK_AI_OR_BOOK"
ASK_NAME = "ASK_NAME"
ASK_DISTRICT = "ASK_DISTRICT"
CONFIRM_LOCATION = "CONFIRM_LOCATION"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_SUBCATEGORY = "ASK_SUBCATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"
PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
FLOW_VERIFY_DETAILS = "VERIFY_DETAILS"
BTN_ASK_AI = "ASK_AI"
BTN_BOOK_CONSULT = "BOOK_CONSULT"
BTN_DETAILS_OK = "DETAILS_OK"
BTN_DETAILS_EDIT = "DETAILS_EDIT"


# ===============================
# HELPERS
# ===============================
def get_db():
    return SessionLocal()

def get_flow_state(user):
    return user.flow_state

def set_flow_state(db, user, value):
    user.flow_state = value
    db.commit()

def save_state(db, user, state):
    set_flow_state(db, user, state)

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
            flow_state=NORMAL,
            ai_enabled=False,
            free_ai_count=0,
            welcome_sent=False,     
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
    now = time_module.time()
    times = user_message_times[wa_id]

    while times and now - times[0] > USER_MSG_WINDOW:
        times.popleft()

    if len(times) >= USER_MSG_LIMIT:
        return True

    times.append(now)
    return False


def is_ai_rate_limited(wa_id):
    now = time_module.time()
    last_call = user_last_ai_call.get(wa_id, 0)

    if now - last_call < AI_CALL_COOLDOWN:
        return True

    user_last_ai_call[wa_id] = now
    return False


def is_global_rate_limited():
    now = time_module.time()

    while global_request_times and now - global_request_times[0] > GLOBAL_REQ_WINDOW:
        global_request_times.popleft()

    if len(global_request_times) >= GLOBAL_REQ_LIMIT:
        return True

    global_request_times.append(now)
    return False

# =================================================
# Name
# =================================================

BUSINESS_KEYWORDS = {"pvt", "ltd", "limited", "company", "llp", "inc", "com", "in", "gov"}

def normalize_name(raw: str):
    if not raw:
        return None

    # Normalize unicode (removes zero-width chars)
    name = unicodedata.normalize("NFKC", raw)

    # Remove leading/trailing spaces & punctuation
    name = name.strip(" .,-")

    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)

    # Reject digits
    if re.search(r"\d", name):
        return None

    # Reject forbidden symbols
    if re.search(r"[\/@#!$%^&*_=+<>?{}[\]|\\]", name):
        return None

    # Allow only letters, spaces and dot
    if not re.fullmatch(r"[A-Za-z.\s'-]+", name):
        return None

    # Reject business names
    lowered = name.lower()
    for word in BUSINESS_KEYWORDS:
        if word in lowered.split():
            return None

    # Optional: Title Case
    name = name.title()

    # Minimum length after cleanup
    if len(name) < 2:
        return None

    return name
    
# =================================================
# CATEGORY & SUB-CATEGORY HELPERS
# =================================================

def send_category_list(wa_id, user):
    rows = [
        {
            "id": f"cat_{category.lower().replace(' ', '_').replace('&', 'and')}",
            "title": get_category_label(category, user),
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
            user.flow_state,
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
    
def send_payment_receipt_again(db, wa_id):
    booking = (
        db.query(Booking)
        .filter(
            Booking.whatsapp_id == wa_id,
            Booking.status == "PAID"
        )
        .order_by(Booking.id.desc())
        .first()
    )

    if not booking:
        send_text(wa_id, "❌ No completed payment found.")
        return

    try:
        # ---------------------------------
        # Generate PDF if required
        # ---------------------------------
        if not booking.receipt_generated:
            pdf_path = generate_pdf_receipt(booking)
            booking.receipt_generated = True
            booking.receipt_path = pdf_path
        else:
            pdf_path = getattr(booking, "receipt_path", None)

        if not pdf_path:
            raise RuntimeError("Receipt PDF path missing")

        # ---------------------------------
        # Send receipt
        # ---------------------------------
        send_payment_receipt_pdf(
            booking.whatsapp_id,
            pdf_path
        )

        booking.receipt_sent = True
        db.commit()

        send_text(
            wa_id,
            "📄 Your payment receipt has been sent again."
        )

    except Exception:
        logger.exception("Receipt resend failed | booking_id=%s", booking.id)
        send_text(
            wa_id,
            "⚠️ Unable to resend receipt right now. Please try later."
        )
        
from services.advocate_service import find_advocate
from services.email_service import send_advocate_booking_email, send_new_booking_email, send_booking_notification_email

def post_payment_background_tasks(booking_id):
    db = SessionLocal()
    try:
        booking = db.query(Booking).get(booking_id)
        if not booking:
            return

        # 🔹 1. Booking notification (TEMP – centralized)
        try:
            send_booking_notification_email(booking)
        except Exception:
            logger.exception(
                "⚠️ Booking notification email failed | booking_id=%s",
                booking.id
            )

        # 🔹 2. Admin email (keep existing behaviour for future used)
        #try:
        #    send_new_booking_email(booking)
        #except Exception:
        #    logger.exception(
        #       "⚠️ Admin email failed | booking_id=%s",
        #        booking.id
        #    )

        # 🔹 3. Receipt PDF + WhatsApp (keep existing behaviour for future used)
        #try:
        #    pdf_path = generate_pdf_receipt(booking)
        #   send_payment_receipt_pdf(
        #        booking.whatsapp_id,
        #        pdf_path
        #    )
        #except Exception:
        #    logger.exception(
        #        "⚠️ Receipt sending failed | booking_id=%s",
        #        booking.id
        #    )

    finally:
        db.close()

def send_verification_screen(db, user, wa_id):
    save_state(db, user, FLOW_VERIFY_DETAILS)
    send_buttons(
        wa_id,
        (
            "Please verify your details:\n\n"
            f"👤 Name: {user.name}\n"
            f"📍 State: {user.state_name}\n"
            f"🏙 District: {user.district_name}"
        ),
        [
            {"id": BTN_DETAILS_OK, "title": "✅ Verified"},
            {"id": BTN_DETAILS_EDIT, "title": "✏️ Edit Details"},
        ],
    )

def get_booking_window(booking):
    """
    Returns (booking_start, booking_end) in UTC
    or (None, None) if booking is invalid
    """

    # 1️⃣ Booking object must exist
    if not booking or not booking.date or not booking.slot_code:
        return None, None

    # 2️⃣ Normalize date
    booking_date = booking.date
    if isinstance(booking_date, str):
        try:
            booking_date = datetime.strptime(
                booking_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            return None, None

    # 3️⃣ Extract start hour from slot_code
    try:
        start_hour = int(booking.slot_code.split("_")[0])
    except Exception:
        return None, None

    # 4️⃣ Compute window
    booking_start = datetime.combine(
        booking_date,
        dt_time(start_hour, 0)
    )
    booking_end = booking_start + timedelta(hours=1)

    logger.debug(
        "BOOKING_WINDOW | booking_id=%s | date=%s | slot=%s | start=%s | end=%s",
        getattr(booking, "id", None),
        booking.date if booking else None,
        booking.slot_code if booking else None,
        booking_start,
        booking_end,
    )
    
    return booking_start, booking_end

def has_completed_consultation(db, wa_id):
    booking = (
        db.query(Booking)
        .filter(
            Booking.whatsapp_id == wa_id,
            Booking.status == "PAID"
        )
        .order_by(Booking.id.desc())
        .first()
    )

    booking_start, booking_end = get_booking_window(booking)

    # 🔒 HARD SAFETY CHECK — NEVER COMPARE None
    if not booking_start or not booking_end:
        logger.warning(
            "CONSULTATION_CHECK_INVALID | wa_id=%s | booking_id=%s | start=%s | end=%s",
            wa_id,
            getattr(booking, "id", None),
            booking_start,
            booking_end,
        )
        return False

    now = datetime.utcnow()

    logger.debug(
        "CONSULTATION_CHECK | wa_id=%s | now=%s | booking_end=%s | completed=%s",
        wa_id,
        now,
        booking_end,
        now > booking_end,
    )

    return now > booking_end

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
        if (
            interactive_id == BTN_ASK_AI
            and user.flow_state == NORMAL
            and user.welcome_sent
            and has_completed_consultation(db, wa_id)
        ):
            user.ai_enabled = True
            user.free_ai_count = 0
            db.commit()
            send_text(
                wa_id,
                "🤖 You can ask your legal question now."
            )
            return jsonify({"status": "ok"}), 200

        if (
            interactive_id == BTN_BOOK_CONSULT
            and user.welcome_sent
            and has_completed_consultation(db, wa_id)
        ):
            send_verification_screen(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        lower_text = text_body.lower().strip()
        # =================================================
        # POST-PAYMENT SESSION CONTROL (CRITICAL)
        # =================================================
        paid_booking = (
            db.query(Booking)
            .filter(
                Booking.whatsapp_id == wa_id,
                Booking.status == "PAID"
            )
            .order_by(Booking.id.desc())
            .first()
        )
        
        if paid_booking:
            logger.debug(
                "POST_PAYMENT_BLOCK_ENTER | wa_id=%s | booking_id=%s | state=%s",
                wa_id,
                paid_booking.id,
                user.flow_state,
            )      
            # -------------------------------
            # DEFENSIVE GUARD — NEVER CRASH
            # -------------------------------
            if not paid_booking.date or not paid_booking.slot_code:
                logger.warning(
                    "Incomplete paid booking | booking_id=%s | date=%s | slot=%s",
                    paid_booking.id,
                    paid_booking.date,
                    paid_booking.slot_code,
                )
                return jsonify({"status": "ignored"}), 200
        
            # -------------------------------
            # SAFE booking window (single source of truth)
            # -------------------------------
            booking_start, booking_end = get_booking_window(paid_booking)
            
            if not booking_start or not booking_end:
                logger.error(
                    "Invalid booking window | booking_id=%s | date=%s | slot=%s",
                    paid_booking.id,
                    paid_booking.date,
                    paid_booking.slot_code,
                )
                return jsonify({"status": "ignored"}), 200
            
            now = datetime.utcnow()

            # -------------------------------
            # A) Consultation already OVER
            # -------------------------------
            if paid_booking and now > booking_end:
                logger.debug(
                    "POST_PAYMENT_EXPIRED | wa_id=%s | now=%s | booking_end=%s | resetting_state",
                    wa_id,
                    now,
                    booking_end,
                )              
                set_flow_state(db, user, NORMAL)
                user.ai_enabled = False
                user.free_ai_count = 0
                user.temp_date = None
                user.temp_slot = None
                user.last_payment_link = None
                db.commit()
            
                # ⚠️ DO NOT auto-send welcome here
                # Let "Hi" trigger welcome naturally
                return jsonify({"status": "ignored"}), 200
                        
            # =================================================
            # 🔒 HARD GUARD: POST-PAYMENT SESSION (TIME-BOUND)
            # =================================================
            if now <= booking_end:
                logger.debug(
                    "POST_PAYMENT_ACTIVE | wa_id=%s | now=%s | booking_end=%s | state_before=%s",
                    wa_id,
                    now,
                    booking_end,
                    user.flow_state,
                )
                
                # 🔒 Ensure state is aligned (webhook race-safe)
                if user.flow_state != PAYMENT_CONFIRMED:
                    set_flow_state(db, user, PAYMENT_CONFIRMED)
            
                message = (text_body or "").strip().lower()
            
                if message == "receipt":
                   #send_payment_receipt_again(db, wa_id) when manual reciept required

                    send_text(
                        wa_id,
                        "📄 Receipt will be available soon. Please contact support if needed."
                    )
                    return jsonify({"status": "ok"}), 200

               
                reply = ai_reply(message, user, context="post_payment")
                send_text(
                    wa_id,
                    "🤖 *Consultation Preparation Assistant*\n\n" + reply
                )
                return jsonify({"status": "ok"}), 200

            
        # -------------------------------
        # Global rate limiting
        # -------------------------------
        if message["type"] in ("text", "interactive"):
            if is_global_rate_limited():
                return jsonify({"status": "rate_limited"}), 200
               
        # ===============================
        # RESTART (BLOCKED AFTER PAYMENT)
        # ===============================
        if lower_text in RESTART_KEYWORDS:
            logger.debug(
                "RESTART_ATTEMPT | wa_id=%s | state=%s",
                wa_id,
                user.flow_state,
            )
            # 🔒 Never allow restart after payment
            if user.flow_state == PAYMENT_CONFIRMED:
                send_text(
                    wa_id,
                    "✅ Your consultation is already confirmed.\n\n"
                    "📄 Type *RECEIPT* for payment receipt.\n"
                    "💬 You may ask questions to prepare for your consultation."
                )
                return jsonify({"status": "ok"}), 200
        
            if user.flow_state == WAITING_PAYMENT:
                send_text(wa_id, t(user, "payment_in_progress"))
                return jsonify({"status": "ok"}), 200
        
            set_flow_state(db, user, NORMAL)
            user.ai_enabled = False
            user.free_ai_count = 0
            user.temp_date = None
            user.temp_slot = None
            user.last_payment_link = None
            db.commit()
        
            send_text(wa_id, t(user, "restart"))
            return jsonify({"status": "ok"}), 200
            
        # ===============================
        # RETURNING USER HOME
        # ===============================
        if (
            user.flow_state == NORMAL
            and user.welcome_sent
            and has_completed_consultation(db, wa_id)
            and not user.ai_enabled
            and user.free_ai_count == 0
            and lower_text in WELCOME_KEYWORDS
        ):
            send_buttons(
                wa_id,
                (
                    f"👋 Welcome back to NyaySetu, {user.name}!\n\n"
                    "What would you like to do today?"
                ),
                [
                    {"id": BTN_ASK_AI, "title": "🤖 Ask AI"},
                    {"id": BTN_BOOK_CONSULT, "title": "📅 Book Consultation"},
                ],
            )
            return jsonify({"status": "ok"}), 200

        # ===============================
        # WELCOME (ONE-TIME ONLY)
        # ===============================
        logger.debug(
            "WELCOME_CHECK | wa_id=%s | state=%s | welcome_sent=%s | text=%s",
            wa_id,
            user.flow_state,
            user.welcome_sent,
            lower_text,
        )
        if (
            user.flow_state == NORMAL
            and not user.welcome_sent
            and lower_text in WELCOME_KEYWORDS
        ):
            save_state(db, user, ASK_LANGUAGE)
        
            send_buttons(
                wa_id,
                t(user, "welcome", case_id=user.case_id),
                [
                    {"id": "lang_en", "title": "English"},
                    {"id": "lang_hi", "title": "Hinglish"},
                    {"id": "lang_mr", "title": "मराठी"},
                ],
            )
        
            # 🔒 mark onboarding permanently done
            user.welcome_sent = True
            db.commit()
        
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
        if user.flow_state == ASK_LANGUAGE:
            if interactive_id in ("lang_en", "lang_hi", "lang_mr"):
                user.language = interactive_id.replace("lang_", "")
                db.commit()
        
                # ✅ Marathi (Greetings)
                if user.language == "mr":
                
                    if not getattr(user, "marathi_greeted", False):
                        send_text(
                            wa_id,
                            "🙏 जय महाराष्ट्र! 🇮🇳\nआपण NyaySetu मध्ये स्वागत आहे ⚖️"
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
        if user.flow_state == ASK_AI_OR_BOOK:
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
        if (
            (lower_text in BOOKING_KEYWORDS or interactive_id == "book_now")
            and user.flow_state == NORMAL
        ):     
            # 🔁 Returning user → go to verification
            if user.welcome_sent and has_completed_consultation(db, wa_id):
                send_verification_screen(db, user, wa_id)
                return jsonify({"status": "ok"}), 200

        
            # 🆕 New user → normal onboarding
            user.ai_enabled = False
            user.free_ai_count = 0
            save_state(db, user, ASK_NAME)
            db.commit()
            send_text(wa_id, t(user, "ask_name"))
            return jsonify({"status": "ok"}), 200

        # ===============================
        # FREE AI CHAT
        # ===============================
        if user.flow_state == NORMAL and user.ai_enabled:
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
        if (
            user.flow_state == FLOW_VERIFY_DETAILS
            and interactive_id == BTN_DETAILS_OK
        ):
            save_state(db, user, ASK_CATEGORY)
            send_category_list(wa_id, user)
            return jsonify({"status": "ok"}), 200
        if (
            user.flow_state == FLOW_VERIFY_DETAILS
            and interactive_id == BTN_DETAILS_EDIT
        ):
            save_state(db, user, ASK_NAME)
            send_text(wa_id, t(user, "ask_name"))
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Ask Name
        # -------------------------------
        if user.flow_state == ASK_NAME:
            if not text_body or len(text_body.strip()) < 2:
                send_text(wa_id, t(user, "ask_name_retry"))
                return jsonify({"status": "ok"}), 200
        
            clean_name = normalize_name(text_body)
            
            if not clean_name:
                send_text(
                    wa_id,
                    "❌ Please enter a valid *personal name*.\n"
                    "Ex: Prashant Keshav Khaire"
                )
                return jsonify({"status": "ok"}), 200
            
            user.name = clean_name
            db.commit()        
        
            # ✅ ALL users → ask DISTRICT directly
            save_state(db, user, ASK_DISTRICT)
        
            send_text(
                wa_id,
                t(user, "ask_district_text")            
            )
        
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Ask District (SMART FLOW)
        # -------------------------------
        if user.flow_state == ASK_DISTRICT:
        
            if not text_body:
                send_text(
                    wa_id,
                    t(user, "ask_district_text")            
                )
                return jsonify({"status": "ok"}), 200
        
            district, state, confidence = detect_district_and_state(text_body)
        
            # -------------------------------
            # HIGH CONFIDENCE
            # -------------------------------
            if confidence == "HIGH":
                user.temp_district = district
                user.temp_state = state
                db.commit()
        
                save_state(db, user, CONFIRM_LOCATION)
        
                send_buttons(
                    wa_id,
                    f"📍 We found:\n*{district}, {state}*\n\nIs this correct?",
                    [
                        {"id": "loc_yes", "title": "✅ Yes"},
                        {"id": "loc_change", "title": "✏️ Change"},
                    ],
                )
                return jsonify({"status": "ok"}), 200
        
            # -------------------------------
            # MULTIPLE MATCHES
            # -------------------------------
            if confidence == "MULTIPLE":
                send_text(
                    wa_id,
                    t(user, "district_multiple_matches")
                )
                return jsonify({"status": "ok"}), 200
        
            # -------------------------------
            # LOW CONFIDENCE
            # -------------------------------
            send_text(
                wa_id,
                t(user, "district_not_identified")
            )
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Confirm Location
        # -------------------------------
        if user.flow_state == CONFIRM_LOCATION:
        
            if interactive_id == "loc_yes":
                user.district_name = user.temp_district
                user.state_name = user.temp_state
        
                user.temp_district = None
                user.temp_state = None
                db.commit()
        
                save_state(db, user, ASK_CATEGORY)
                send_category_list(wa_id, user)
                return jsonify({"status": "ok"}), 200
        
            if interactive_id == "loc_change":
                user.temp_district = None
                user.temp_state = None
                db.commit()
        
                save_state(db, user, ASK_DISTRICT)
                send_text(
                    wa_id,
                    t(user, "district_retry")
                )
                return jsonify({"status": "ok"}), 200        
        
        # -------------------------------
        # Category (STRICT & SAFE)
        # -------------------------------
        if user.flow_state == ASK_CATEGORY:
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
        if user.flow_state == ASK_SUBCATEGORY:
        
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
        if user.flow_state == ASK_DATE:
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
        if user.flow_state == ASK_SLOT:
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
                subcategory=user.subcategory, 
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
                    amount=BOOKING_PRICE,
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

        # ===============================
        # WAITING PAYMENT (SAFE MODE)
        # ===============================
        if user.flow_state == WAITING_PAYMENT:
        
            # Ignore delivery/status callbacks
            if not text_body:
                return jsonify({"status": "ignored"}), 200
        
            # 🔒 Safety: if payment already completed, stop immediately
            booking = (
                db.query(Booking)
                .filter(
                    Booking.whatsapp_id == wa_id,
                    Booking.status == "PAID"
                )
                .first()
            )
        
            if booking:
                return jsonify({"status": "ignored"}), 200
        
            # Resend payment link only on user text
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
    db = get_db()
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

        paid_amount = payment.get("amount")
        paid_currency = payment.get("currency")

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
        # 7. AMOUNT VALIDATION
        # -------------------------------------------------
        EXPECTED_AMOUNT = int(BOOKING_PRICE * 100)

        if paid_currency != "INR" or paid_amount != EXPECTED_AMOUNT:
            logger.error("❌ Amount mismatch")
            return "Amount mismatch", 400

        # -------------------------------------------------
        # 8. IDEMPOTENCY CHECK
        # -------------------------------------------------
        existing = (
            db.query(Booking)
            .filter(Booking.razorpay_payment_id == payment_id)
            .first()
        )

        if existing:
            logger.info("🔁 Duplicate webhook ignored")
            return "OK", 200

        # -------------------------------------------------
        # 9. CONFIRM PAYMENT
        # -------------------------------------------------
        booking = mark_booking_as_paid(
            payment_link_id=payment_link_id,
            payment_id=payment_id,
            payment_mode=razorpay_mode
        )
        
        if not booking:
            return "Ignored", 200
        
        # -------------------------------------------------
        # 10. CLOSE USER PAYMENT STATE
        # -------------------------------------------------
        user = (
            db.query(User)
            .filter(User.whatsapp_id == booking.whatsapp_id)
            .first()
        )
        
        if user:
            set_flow_state(db, user, PAYMENT_CONFIRMED)
            user.last_payment_link = None
            db.commit()
        
        # -------------------------------------------------
        # 11. FAST USER CONFIRMATION (TEXT ONLY)
        # -------------------------------------------------
        try:
            send_payment_success_message(booking)
        except Exception:
            logger.exception("⚠️ Payment success message failed")
        
        # -------------------------------------------------
        # 12. BACKGROUND HEAVY TASKS (EMAIL + PDF)
        # -------------------------------------------------
         Thread(
             target=post_payment_background_tasks,
             args=(booking.id,),
             daemon=True
         ).start()
        
        logger.info("✅ PAYMENT CONFIRMED & BOOKING UPDATED")
        
        return "OK", 200
    except Exception:
        logger.exception("🔥 Razorpay webhook processing error")
        return "Internal error", 500
    
    finally:
        db.close()    
        

