import os
import time
import uuid
import random
import logging
import requests
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, render_template_string
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from openai import OpenAI, RateLimitError, APIError, BadRequestError

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
PRIMARY_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
TYPING_DELAY = 1.1
MAX_FREE_MESSAGES = 6
CONSULT_FEE_RS = 499

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------- DATABASE ----------------
DATABASE_URL = "sqlite:///nyaysetu.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    whatsapp = Column(String, index=True, unique=True)
    case_id = Column(String)
    language = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    whatsapp = Column(String, index=True)
    direction = Column(String)  # "user" or "bot"
    text = Column(Text)
    ts = Column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    whatsapp = Column(String, index=True)
    preferred_time = Column(String)
    confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)

# ---------------- WHATSAPP UTILITIES ----------------

def w_headers():
    return {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"}

def w_url():
    return f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"

def send_text(to, body):
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    try: requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except: pass

def send_buttons(to, body, buttons):
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {"type": "button", "body": {"text": body},
                        "action": {"buttons": [{"type": "reply", "reply": b} for b in buttons]}}
    }
    try: requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except: pass

def send_list_dates(to, days=7):
    today = datetime.now()
    rows = []
    for i in range(days):
        d = today + timedelta(days=i)
        rows.append({"id": d.strftime("DATE_%Y-%m-%d"),
                     "title": d.strftime("%a, %d %b"),
                     "description": ""})
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {"type": "list",
                        "body": {"text": "📅 कृपया दिनांक निवडा / Select your convenient date:"},
                        "action": {"button": "Select Date", "sections": [{"title": "Available Dates", "rows": rows}]}}
    }
    try: requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except: pass

def typing_on(to):
    try: requests.post(w_url(), headers=w_headers(), json={"messaging_product": "whatsapp", "to": to, "type": "typing_on"}, timeout=5)
    except: pass

def typing_off(to):
    try: requests.post(w_url(), headers=w_headers(), json={"messaging_product": "whatsapp", "to": to, "type": "typing_off"}, timeout=5)
    except: pass

# ---------------- BOOKING STATE ----------------
pending_booking_state = {}  # {whatsapp: {"date": "YYYY-MM-DD", "step": "awaiting_time"}}

# ---------------- TIME SLOTS ----------------
TIME_SLOTS = {
    "TIME_morning": ("Morning", "10 AM – 1 PM"),
    "TIME_afternoon": ("Afternoon", "1 PM – 4 PM"),
    "TIME_evening": ("Evening", "4 PM – 7 PM"),
}

# ---------------- MULTI-LANGUAGE WELCOME ----------------
WELCOME = {
    "English": (
        "👋 Welcome to NyaySetu — The Bridge To Justice.\n"
        "Your Case ID: {case}\n\n"
        "Please describe your legal issue. I will guide you safely & confidentially."
    ),
    "Hinglish": (
        "👋 NyaySetu mein swagat hai — The Bridge To Justice.\n"
        "Aapka Case ID: {case}\n\n"
        "Aap apni legal problem bataiye, main aapko safe aur confidential guidance dunga."
    ),
    "Marathi": (
        "👋 न्यायसेतू मध्ये स्वागत — The Bridge To Justice.\n"
        "तुमचा केस आयडी: {case}\n\n"
        "कृपया तुमची कायदेशीर अडचण सांगा, मी सुरक्षित व गोपनीय मार्गदर्शन करेन."
    ),
}

FREE_LIMIT = {
    "English": (
        "🛑 You have used your free legal answers.\n\n"
        "To continue with personalised legal help, please book a consultation.\n"
        "Reply *BOOK* to schedule a call with a legal expert."
    ),
    "Hinglish": (
        "🛑 Aapke free legal jawab complete ho gaye hain.\n\n"
        "Personalised legal help ke liye consultation book karein.\n"
        "Reply *BOOK* karein call schedule ke liye."
    ),
    "Marathi": (
        "🛑 तुमचे मोफत कायदेशीर उत्तर पूर्ण झाले आहेत.\n\n"
        "वैयक्तिक कायदेशीर मदतीसाठी consultation बुक करा.\n"
        "कॉल शेड्यूल करण्यासाठी *BOOK* लिहा."
    ),
}

INTRO_SUGGESTIONS = [
    {"id": "police", "title": "🚨 Police / FIR"},
    {"id": "family", "title": "👪 Family / Marriage"},
    {"id": "property", "title": "🏠 Property / Land"},
    {"id": "money", "title": "💰 Money / Recovery"},
    {"id": "business", "title": "💼 Business / Work"},
]
# ---------------- MESSAGE CLASSIFICATION / HELPERS ----------------

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "xxxx")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "yyyy")

GREETING_KEYWORDS = {
    "hi", "hello", "hey", "hola",
    "namaste", "namaskar",
    "good morning", "good evening", "good afternoon"
}

COMMAND_KEYWORDS = {
    "book", "booking", "consult", "consultation", "appointment",
    "📅 book consultation", "📞 speak to lawyer", "📄 get draft notice",
    "call", "draft", "restart", "start"
}

TIME_COMMANDS = {"time_morning", "time_afternoon", "time_evening"}


def parse_date_from_text(text: str):
    """
    Try to convert a human-readable date like:
    - 'DATE_2025-12-04'
    - 'Thu, 04 Dec'
    - 'Thu 04 Dec'
    - '04 Dec'
    - '04-12-2025'
    - '2025-12-04'
    into 'YYYY-MM-DD'.
    Returns None if parsing fails.
    """
    if not text:
        return None

    text = text.strip()

    # Direct DATE_YYYY-MM-DD format
    if text.upper().startswith("DATE_"):
        return text[5:]

    from datetime import datetime
    now = datetime.now()

    # Try some common date patterns
    candidates = [text, text.replace(",", "")]
    formats = [
        "%a %d %b",       # Thu 04 Dec
        "%a %d %b %Y",    # Thu 04 Dec 2025
        "%d %b",          # 04 Dec
        "%d %b %Y",       # 04 Dec 2025
        "%d-%m-%Y",       # 04-12-2025
        "%d/%m/%Y",       # 04/12/2025
        "%Y-%m-%d",       # 2025-12-04
    ]

    for cand in candidates:
        for fmt in formats:
            try:
                dt = datetime.strptime(cand, fmt)
                # If year not present in format, assume current year
                if "%Y" not in fmt:
                    dt = dt.replace(year=now.year)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

    return None


def count_legal_questions(wa_id: str) -> int:
    """
    Count only 'real' user legal questions:
    - ignore greetings like 'hi', 'hello'
    - ignore commands like BOOK, CONSULT, category buttons
    - ignore DATE_..., TIME_... selections
    """
    msgs = (
        db.query(Conversation)
        .filter_by(whatsapp=wa_id, direction="user")
        .order_by(Conversation.ts.asc())
        .all()
    )

    total = 0
    for m in msgs:
        body = (m.text or "").strip().lower()
        if not body:
            continue

        if body in GREETING_KEYWORDS:
            continue
        if body in COMMAND_KEYWORDS:
            continue
        if body.startswith("date_"):
            continue
        if body in TIME_COMMANDS:
            continue

        total += 1

    return total


# ---------------- USER & CONVERSATION HELPERS ----------------

def register_user(wa_id: str) -> User:
    user = db.query(User).filter_by(whatsapp=wa_id).first()
    if user:
        return user
    case_id = f"NS-{uuid.uuid4().hex[:8].upper()}"
    user = User(whatsapp=wa_id, case_id=case_id, language="English")
    db.add(user)
    db.commit()
    logging.info(f"New user registered: {wa_id} → {case_id}")
    return user


def store_message(wa_id: str, direction: str, text: str):
    msg = Conversation(whatsapp=wa_id, direction=direction, text=text)
    db.add(msg)
    db.commit()


def user_message_count(wa_id: str) -> int:
    return db.query(Conversation).filter_by(whatsapp=wa_id, direction="user").count()


def get_latest_booking_status(wa_id: str):
    b = (
        db.query(Booking)
        .filter_by(whatsapp=wa_id)
        .order_by(Booking.created_at.desc())
        .first()
    )
    if not b:
        return None
    return "confirmed" if b.confirmed else "pending"


def create_booking(wa_id: str, preferred_time_text: str) -> Booking:
    b = Booking(whatsapp=wa_id, preferred_time=preferred_time_text, confirmed=False)
    db.add(b)
    db.commit()
    return b


# ---------------- OPENAI UTILITIES ----------------

def call_openai(messages, temperature=0.2, max_tokens=300):
    backoff = 1.0
    for attempt in range(4):
        try:
            res = client.chat.completions.create(
                model=PRIMARY_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return res.choices[0].message.content
        except RateLimitError as e:
            logging.warning(f"OpenAI rate limited: {e}; retrying...")
            time.sleep(backoff)
            backoff *= 2
        except (BadRequestError, APIError) as e:
            logging.error(f"OpenAI API error: {e}")
            break
        except Exception as e:
            logging.error(f"OpenAI unexpected error: {e}")
            time.sleep(backoff)
            backoff *= 2
    return None


def normalize_language_name(name: str) -> str:
    if not name:
        return "English"
    n = name.strip().lower()
    if "marathi" in n:
        return "Marathi"
    if "hinglish" in n or "hindi" in n or "mix" in n:
        return "Hinglish"
    # default
    return "English"


def detect_language(text: str) -> str:
    prompt = (
        "Detect the main language of this message. "
        "Reply with exactly one word from: English, Hinglish, Marathi.\n\n"
        f"Text: {text}"
    )
    res = call_openai([{"role": "user", "content": prompt}], max_tokens=10)
    return normalize_language_name(res or "English")


def detect_category(text: str) -> str:
    prompt = (
        "Classify the legal topic of this message into one word from: "
        "property, police, family, business, money, other.\n"
        f"Message: {text}\n"
        "Return only the category word."
    )
    res = call_openai([{"role": "user", "content": prompt}], max_tokens=10)
    if not res:
        return "other"
    return res.strip().lower()


def legal_reply(text: str, lang: str, category: str) -> str:
    system_prompt = (
        "You are a professional, ethical legal assistant for Indian law. "
        "You are NOT a lawyer and you do NOT create a lawyer–client relationship. "
        "You ALWAYS reply in the same language style as specified (English, Hinglish, Marathi). "
        "Give clear, simple, trustworthy information in 2–4 short sentences. "
        "Avoid promising any specific result or guarantee. "
        "If the matter is serious, urgent, criminal, or complex, clearly advise the user "
        "to consult a qualified advocate and suggest that they can book a consultation call."
    )

    user_msg = f"[Language: {lang}] [Category: {category}] User message: {text}"

    res = call_openai(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=220,
    )
    if not res:
        if lang == "Marathi":
            return "माफ करा, सध्या योग्य उत्तर तयार करता आले नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा."
        if lang == "Hinglish":
            return "Sorry, abhi proper answer generate nahi ho paya. Thodi der baad phir try karein."
        return "Sorry, I am unable to prepare a proper answer right now. Please try again in some time."
    return res


# ---------------- RAZORPAY PAYMENT LINK ----------------

def create_payment_link(case_id: str, whatsapp_number: str, amount_in_rupees: int = CONSULT_FEE_RS):
    """
    Create a Razorpay Payment Link and return its URL.
    """
    try:
        amount_paise = amount_in_rupees * 100
        url = "https://api.razorpay.com/v1/payment_links"

        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "description": f"NyaySetu Legal Consultation - Case {case_id}",
            "reference_id": case_id,
            "customer": {"contact": whatsapp_number},
            "notify": {"sms": True, "email": False},
            "reminder_enable": True,
        }

        resp = requests.post(
            url,
            auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
            json=payload,
            timeout=10,
        )
        data = resp.json()
        logging.info(f"Razorpay link response: {data}")

        if resp.status_code in (200, 201) and data.get("short_url"):
            return data["short_url"]

        return None
    except Exception as e:
        logging.error(f"Error creating Razorpay payment link: {e}")
        return None
# ---------------- MAIN WEBHOOK ----------------

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # --- Verification for WhatsApp Webhook Setup ---
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Verification failed", 403

    # --- Incoming message handling ---
    payload = request.get_json(silent=True) or {}
    logging.info(f"Incoming payload: {payload}")

    try:
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return jsonify({"status": "no_messages"}), 200

        msg = messages[0]
        wa_from = msg.get("from")
        msg_type = msg.get("type")

        # Extract text / interactive content
        text_body = ""
        if msg_type == "text":
            text_body = msg.get("text", {}).get("body", "") or ""
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            if "button_reply" in interactive:
                r = interactive["button_reply"]
                text_body = r.get("id") or r.get("title", "")
            elif "list_reply" in interactive:
                r = interactive["list_reply"]
                text_body = r.get("id") or r.get("title", "")
        else:
            send_text(wa_from, "Please type your legal question in text so I can guide you properly.")
            return jsonify({"status": "unsupported"}), 200

        raw_text_body = text_body  # original text (for date parsing etc.)

        if not wa_from or not text_body.strip():
            return jsonify({"status": "empty"}), 200

        # Register / fetch user and store incoming message
        user = register_user(wa_from)
        store_message(wa_from, "user", text_body)
        conv_count = user_message_count(wa_from)

        # ---------- FIRST MESSAGE → WELCOME FLOW ----------
        if conv_count <= 1:
            # Detect language only once and store
            lang = detect_language(text_body)
            user.language = lang
            db.commit()

            typing_on(wa_from)
            time.sleep(TYPING_DELAY)
            welcome_template = WELCOME.get(lang, WELCOME["English"])
            welcome_text = welcome_template.format(case=user.case_id)
            send_text(wa_from, welcome_text)
            typing_off(wa_from)

            # Initial suggestions (categories)
            send_buttons(
                wa_from,
                "You can also choose a category to start:",
                INTRO_SUGGESTIONS,
            )
            return jsonify({"status": "welcome"}), 200

        # For subsequent messages
        message = text_body.strip().lower()
        lang_for_user = normalize_language_name(user.language or "English")

        # ---------- BOOKING ENTRY POINT ----------
        if message in {
            "book", "booking", "consult", "consultation", "appointment",
            "📅 book consultation"
        }:
            # Reset booking state for this user
            pending_booking_state[wa_from] = {"date": None, "step": "awaiting_date"}
            send_list_dates(wa_from)
            return jsonify({"status": "ask_date"}), 200

        # ---------- DATE SELECTION (list reply or manual text) ----------
        if text_body.startswith("DATE_") or parse_date_from_text(raw_text_body):
            # Prefer ID form if present, otherwise parse from visible text
            date_str = parse_date_from_text(text_body) or parse_date_from_text(raw_text_body)
            if not date_str:
                # Date failed to parse
                if lang_for_user == "Marathi":
                    send_text(wa_from, "मला हा दिनांक समजला नाही. कृपया लिस्टमधून दिनांक पुन्हा निवडा.")
                elif lang_for_user == "Hinglish":
                    send_text(wa_from, "Mujhe yeh date samajh nahi aaya. Kripya list se dobara date select karein.")
                else:
                    send_text(wa_from, "Sorry, I could not understand this date. Please select again from the list.")
                return jsonify({"status": "date_parse_error"}), 200

            pending_booking_state[wa_from] = {"date": date_str, "step": "awaiting_time"}
            logging.info(f"User {wa_from} selected date {date_str}")

            # Ask user to choose time slot
            send_buttons(
                wa_from,
                f"📅 Date selected: *{date_str}*\n\nNow choose a time slot:",
                [
                    {"id": "TIME_morning", "title": "🌅 Morning (10 AM – 1 PM)"},
                    {"id": "TIME_afternoon", "title": "🌞 Afternoon (1 PM – 4 PM)"},
                    {"id": "TIME_evening", "title": "🌙 Evening (4 PM – 7 PM)"},
                ],
            )
            return jsonify({"status": "ask_time"}), 200

        # ---------- TIME SLOT SELECTION ----------
        if text_body in TIME_SLOTS:
            state = pending_booking_state.get(wa_from)
            date_str = state["date"] if state and state.get("date") else None

            if not date_str:
                # User clicked time without date
                if lang_for_user == "Marathi":
                    send_text(
                        wa_from,
                        "कृपया आधी दिनांक निवडा. जर नवीन बुकिंग सुरू करायची असेल तर *BOOK* लिहा."
                    )
                elif lang_for_user == "Hinglish":
                    send_text(
                        wa_from,
                        "Please pehle date select karein. Agar naya booking start karna hai to *BOOK* likhein."
                    )
                else:
                    send_text(
                        wa_from,
                        "Please first select a date from the list. "
                        "If you want to start again, reply with *BOOK*."
                    )
                return jsonify({"status": "no_date"}), 200

            slot_label, window = TIME_SLOTS[text_body]
            preferred_text = f"{date_str} — {slot_label} ({window})"

            # Create booking record
            booking = create_booking(wa_from, preferred_text)

            # Create Razorpay payment link
            payment_url = create_payment_link(user.case_id, wa_from, amount_in_rupees=CONSULT_FEE_RS)
            if not payment_url:
                if lang_for_user == "Marathi":
                    send_text(
                        wa_from,
                        "क्षमस्व, सध्या पेमेंट लिंक तयार करता आली नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा."
                    )
                elif lang_for_user == "Hinglish":
                    send_text(
                        wa_from,
                        "Sorry, abhi payment link create nahi ho paayi. Thodi der baad phir se try karein."
                    )
                else:
                    send_text(
                        wa_from,
                        "Sorry, I could not create the payment link right now. "
                        "Please try again after some time."
                    )
                return jsonify({"status": "payment_link_error"}), 200

            if lang_for_user == "Marathi":
                msg_out = (
                    f"📝 धन्यवाद. तुमचे सत्र या वेळेसाठी नोंद झाले आहे:\n"
                    f"*{booking.preferred_time}*\n\n"
                    f"💰 45 मिनिटांच्या कायदेशीर सल्ल्यासाठी कृपया *₹{CONSULT_FEE_RS}* भरा.\n"
                    f"🔗 पेमेंट लिंक: {payment_url}\n\n"
                    "पेमेंट पूर्ण होताच तुमचे अपॉइंटमेंट कन्फर्म होईल आणि निवडलेल्या स्लॉटमध्ये "
                    "एक सत्यापित कायदे तज्ञ तुमच्याशी संपर्क करतील."
                )
            elif lang_for_user == "Hinglish":
                msg_out = (
                    f"📝 Dhanyavaad. Aapka session is time ke liye note ho gaya hai:\n"
                    f"*{booking.preferred_time}*\n\n"
                    f"💰 45-minute legal consultation ke liye kripya *₹{CONSULT_FEE_RS}* pay karein.\n"
                    f"🔗 Payment Link: {payment_url}\n\n"
                    "Payment complete hote hi aapka appointment confirm ho jayega "
                    "aur ek verified legal expert aapko selected time window me call karega."
                )
            else:
                msg_out = (
                    f"📝 Thank you. We’ve scheduled your session for:\n"
                    f"*{booking.preferred_time}*\n\n"
                    f"💰 To confirm your 45-minute legal expert call, please pay *₹{CONSULT_FEE_RS}*.\n"
                    f"🔗 Payment Link: {payment_url}\n\n"
                    "As soon as the payment is completed, your appointment will be confirmed, "
                    "and a verified legal expert will call you within the selected time window."
                )

            send_text(wa_from, msg_out)
            pending_booking_state.pop(wa_from, None)
            return jsonify({"status": "booking_created"}), 200

        # ---------- FREE MESSAGE LIMIT (AFTER BOOKING HANDLERS) ----------
        booking_status = get_latest_booking_status(wa_from)
        legal_q_count = count_legal_questions(wa_from)

        if booking_status != "confirmed" and legal_q_count >= MAX_FREE_MESSAGES:
            limit_msg = FREE_LIMIT.get(lang_for_user, FREE_LIMIT["English"])
            send_text(wa_from, limit_msg)
            return jsonify({"status": "limit_reached"}), 200

        # ---------- NORMAL LEGAL AI REPLY ----------
        # We detect language fresh (user can switch languages), but store base preference in user.language
        detected_lang = detect_language(text_body)
        category = detect_category(text_body)
        logging.info(f"Lang={detected_lang}, Category={category}")

        typing_on(wa_from)
        time.sleep(TYPING_DELAY)
        reply = legal_reply(text_body, detected_lang, category)
        typing_off(wa_from)

        send_text(wa_from, reply)
        store_message(wa_from, "bot", reply)

        # Suggest next steps only if user still has free answers left and booking not yet confirmed
        if booking_status != "confirmed" and legal_q_count < MAX_FREE_MESSAGES:
            if detected_lang == "Marathi":
                btn_body = "पुढे काय करायचे ते निवडा:"
            elif detected_lang == "Hinglish":
                btn_body = "Aap agla step choose kar sakte hain:"
            else:
                btn_body = "You can also choose what to do next:"

            send_buttons(
                wa_from,
                btn_body,
                [
                    {"id": "book", "title": "📅 Book Consultation"},
                    {"id": "call", "title": "📞 Speak to Lawyer"},
                    {"id": "draft", "title": "📄 Get Draft Notice"},
                ],
            )

        return jsonify({"status": "answered"}), 200

    except Exception as e:
        logging.exception("Webhook error")
        return jsonify({"status": "error", "error": str(e)}), 500
# ---------------- RAZORPAY WEBHOOK ----------------
# Configure this URL in Razorpay Dashboard as:
# https://api.nyaysetu.in/payment/webhook
# (or your Render domain)

@app.route("/payment/webhook", methods=["POST"])
def payment_webhook():
    event = request.get_json(silent=True) or {}
    logging.info(f"Razorpay webhook: {event}")

    try:
        event_type = event.get("event")

        # We only care about successful payment link events
        if event_type == "payment_link.paid":
            payment_link_entity = (
                event.get("payload", {})
                .get("payment_link", {})
                .get("entity", {})
            )

            ref_case_id = payment_link_entity.get("reference_id")
            customer = payment_link_entity.get("customer", {}) or {}
            contact = customer.get("contact")  # WhatsApp number

            logging.info(f"Payment success for case {ref_case_id}, contact={contact}")

            if contact:
                booking = (
                    db.query(Booking)
                    .filter_by(whatsapp=contact)
                    .order_by(Booking.created_at.desc())
                    .first()
                )

                if booking and not booking.confirmed:
                    booking.confirmed = True
                    db.commit()

                    # Detect user stored language (same as welcome message)
                    user = db.query(User).filter_by(whatsapp=contact).first()
                    lang = normalize_language_name(user.language if user else "English")

                    if lang == "Marathi":
                        confirm_msg = (
                            "🎉 पेमेंट यशस्वीरीत्या प्राप्त झाले!\n\n"
                            f"📌 तुमचे consultation *{booking.preferred_time}* या वेळेसाठी निश्चित झाले आहे.\n"
                            "निवडलेल्या वेळेमध्ये सत्यापित कायदे तज्ञ तुमच्याशी कॉलद्वारे संपर्क करतील.\n\n"
                            "न्यायसेतूवर विश्वास दाखवल्याबद्दल धन्यवाद. 🙏"
                        )
                    elif lang == "Hinglish":
                        confirm_msg = (
                            "🎉 Payment successfully received!\n\n"
                            f"📌 Aapka consultation *{booking.preferred_time}* ke liye confirm ho gaya hai.\n"
                            "Selected time slot me ek verified legal expert aapko call karega.\n\n"
                            "NyaySetu par vishwas karne ke liye dhanyavaad. 🙏"
                        )
                    else:
                        confirm_msg = (
                            "🎉 Payment received successfully!\n\n"
                            f"📌 Your consultation is confirmed for *{booking.preferred_time}*.\n"
                            "A verified NyaySetu legal expert will call you during the selected time window.\n\n"
                            "Thank you for trusting NyaySetu. 🙏"
                        )

                    send_text(contact, confirm_msg)

    except Exception as e:
        logging.error(f"Error handling Razorpay webhook: {e}")

    return "", 200


# ---------------- ADMIN DASHBOARD ----------------

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminpass")

ADMIN_HTML = """
<html>
<head>
  <title>NyaySetu Admin</title>
  <style>
    body { font-family: Arial; padding: 30px; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 40px; }
    th, td { border: 1px solid #555; padding: 10px; font-size: 14px; }
    th { background-color: #eee; }
    h1 { margin-bottom: 30px; }
  </style>
</head>
<body>
  <h1>NyaySetu — Admin Dashboard</h1>

  <h2>Users</h2>
  <table>
    <tr><th>WhatsApp</th><th>Case ID</th><th>Language</th><th>Created</th></tr>
    {% for u in users %}
    <tr>
      <td>{{u.whatsapp}}</td>
      <td>{{u.case_id}}</td>
      <td>{{u.language}}</td>
      <td>{{u.created_at}}</td>
    </tr>
    {% endfor %}
  </table>

  <h2>Bookings</h2>
  <table>
    <tr><th>WhatsApp</th><th>Preferred Time</th><th>Confirmed</th><th>Created</th></tr>
    {% for b in bookings %}
    <tr>
      <td>{{b.whatsapp}}</td>
      <td>{{b.preferred_time}}</td>
      <td>{{"Yes" if b.confirmed else "No"}}</td>
      <td>{{b.created_at}}</td>
    </tr>
    {% endfor %}
  </table>
</body>
</html>
"""

@app.route("/admin")
def admin_dashboard():
    pwd = request.args.get("pwd", "")
    if pwd != ADMIN_PASSWORD:
        return "Forbidden", 403

    users = db.query(User).order_by(User.created_at.desc()).limit(200).all()
    bookings = db.query(Booking).order_by(Booking.created_at.desc()).limit(200).all()
    return render_template_string(ADMIN_HTML, users=users, bookings=bookings)
# ---------------- HEALTH CHECK ENDPOINT ----------------
@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


# ---------------- RUN (LOCAL DEV ONLY) ----------------
# ⚠ Render / production ignores this block (uses gunicorn).
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting NyaySetu app on port {port}")
    app.run(host="0.0.0.0", port=port)

