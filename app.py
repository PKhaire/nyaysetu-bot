import os
import time
import uuid
import logging
import requests
import threading
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
MAX_FREE_ANSWERS = 6  # number of BOT legal answers allowed for free
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
    language = Column(String)  # English / Hinglish / Marathi
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
    return {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }


def w_url():
    return f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"


def send_text(to, body):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body}
    }
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except Exception:
        logging.exception("Error sending WhatsApp text")


def send_buttons(to, body, buttons):
    """
    buttons: list of {"id": "value", "title": "Label"}
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": b} for b in buttons
                ]
            }
        }
    }
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except Exception:
        logging.exception("Error sending WhatsApp buttons")


def send_list_dates(to, days=7):
    """
    Send WhatsApp interactive list for next `days` days.
    Each row id: DATE_YYYY-MM-DD
    """
    today = datetime.now()
    rows = []
    for i in range(days):
        d = today + timedelta(days=i)
        rows.append({
            "id": d.strftime("DATE_%Y-%m-%d"),
            "title": d.strftime("%a, %d %b"),
            "description": ""
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": "📅 कृपया दिनांक निवडा / Select your convenient date:"},
            "action": {
                "button": "Select Date",
                "sections": [
                    {"title": "Available Dates", "rows": rows}
                ]
            }
        }
    }
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except Exception:
        logging.exception("Error sending dates list")


def typing_on(to):
    try:
        requests.post(
            w_url(),
            headers=w_headers(),
            json={"messaging_product": "whatsapp", "to": to, "type": "typing_on"},
            timeout=5,
        )
    except Exception:
        pass


def typing_off(to):
    try:
        requests.post(
            w_url(),
            headers=w_headers(),
            json={"messaging_product": "whatsapp", "to": to, "type": "typing_off"},
            timeout=5,
        )
    except Exception:
        pass


# ---------------- BOOKING STATE ----------------
# {whatsapp: {"date": "YYYY-MM-DD", "step": "awaiting_time"}}
pending_booking_state = {}

# ---------------- TIME SLOTS ----------------
TIME_SLOTS = {
    "TIME_morning": ("Morning", "10 AM – 1 PM"),
    "TIME_afternoon": ("Afternoon", "1 PM – 4 PM"),
    "TIME_evening": ("Evening", "4 PM – 7 PM"),
}

# ---------------- MULTI-LANGUAGE WELCOME & LIMIT TEXT ----------------
# Welcome: Style A (professional)
WELCOME = {
    "English": (
        "👋 Welcome to NyaySetu — The Bridge To Justice.\n"
        "Your Case ID: {case}\n\n"
        "Before we begin, please choose your preferred language 👇"
    ),
    "Hinglish": (
        "👋 NyaySetu mein swagat hai — The Bridge To Justice.\n"
        "Aapka Case ID: {case}\n\n"
        "Shuru karne se pehle, kripya apni pasand ki bhasha choose karein 👇"
    ),
    "Marathi": (
        "👋 न्यायसेतू मध्ये स्वागत — The Bridge To Justice.\n"
        "तुमचा केस आयडी: {case}\n\n"
        "सुरुवात करण्यापूर्वी, कृपया तुमची पसंतीची भाषा निवडा 👇"
    ),
}

FREE_LIMIT = {
    "English": (
        "🛑 You have used your free legal answers.\n\n"
        "To continue receiving personalised guidance, please choose an option below."
    ),
    "Hinglish": (
        "🛑 Aapke free legal jawab complete ho chuke hain.\n\n"
        "Personalised legal guidance ke liye, kripya niche diye gaye options me se koi ek chunen."
    ),
    "Marathi": (
        "🛑 तुमचे मोफत कायदेशीर उत्तर पूर्ण झाले आहेत.\n\n"
        "पुढील वैयक्तिक मार्गदर्शनासाठी खालीलपैकी एक पर्याय निवडा."
    ),
}

# Plain text language buttons (no emojis)
LANGUAGE_BUTTONS = [
    {"id": "lang_en", "title": "English"},
    {"id": "lang_hinglish", "title": "Hinglish"},
    {"id": "lang_marathi", "title": "Marathi"},
]

LIMIT_ACTION_BUTTONS = [
    {"id": "action_call", "title": "📞 Call NyaySetu"},
    {"id": "action_book", "title": "📅 Book Consultation"},
    {"id": "action_notice", "title": "📄 Send Legal Notice"},
    {"id": "action_visit", "title": "🌐 Visit NyaySetu"},
]

# ---------------- MESSAGE CLASSIFICATION / HELPERS ----------------

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "xxxx")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "yyyy")


def normalize_language_name(name: str) -> str:
    if not name:
        return "English"
    n = name.strip().lower()
    if "marathi" in n:
        return "Marathi"
    if "hinglish" in n or "hindi" in n or "mix" in n:
        return "Hinglish"
    return "English"


def parse_date_from_text(text: str):
    """
    Convert date-like text to 'YYYY-MM-DD' where possible.
    """
    if not text:
        return None

    text = text.strip()

    if text.upper().startswith("DATE_"):
        return text[5:]

    from datetime import datetime as _dt
    now = _dt.now()

    candidates = [text, text.replace(",", "")]
    formats = [
        "%a %d %b",
        "%a %d %b %Y",
        "%d %b",
        "%d %b %Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ]

    for cand in candidates:
        for fmt in formats:
            try:
                dt = _dt.strptime(cand, fmt)
                if "%Y" not in fmt:
                    dt = dt.replace(year=now.year)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

    return None


# ---------------- USER & CONVERSATION HELPERS ----------------


def register_user(wa_id: str) -> User:
    user = db.query(User).filter_by(whatsapp=wa_id).first()
    if user:
        return user
    case_id = f"NS-{uuid.uuid4().hex[:8].upper()}"
    user = User(whatsapp=wa_id, case_id=case_id, language=None)
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


def count_legal_bot_answers(wa_id: str) -> int:
    """
    Count BOT replies that are likely legal answers / guidance.
    We EXCLUDE only system / flow messages (welcome, language, booking, payment, limit).
    Everything else is treated as a legal answer.
    """
    msgs = (
        db.query(Conversation)
        .filter_by(whatsapp=wa_id, direction="bot")
        .order_by(Conversation.ts.asc())
        .all()
    )
    total = 0

    skip_keywords = [
        "welcome to nyaysetu",
        "nyaysetu mein swagat hai",
        "न्यायसेतू मध्ये स्वागत",
        "select your preferred language",
        "bhasha",
        "भाषा",
        "select your convenient date",
        "कृपया दिनांक",
        "date selected:",
        "now choose a time slot",
        "payment link",
        "we’ve scheduled your session",
        "we've scheduled your session",
        "payment received successfully",
        "consultation is confirmed",
        "thank you for trusting nyaysetu",
        "you have used your free legal answers",
        "aapke free legal jawab",
        "तुमचे मोफत कायदेशीर उत्तर पूर्ण झाले आहेत",
        "choose an option below",
    ]

    for m in msgs:
        t = (m.text or "").strip()
        if not t:
            continue
        low = t.lower()

        # Skip non-legal / system messages
        if any(k in low for k in skip_keywords):
            continue

        # Everything else is a counted legal answer
        total += 1

    return total


# ---------------- OPENAI UTILITIES ----------------


def call_openai(messages, temperature=0.2, max_tokens=300):
    """
    Single-attempt OpenAI call to avoid long retry loops and OOM.
    """
    try:
        res = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return res.choices[0].message.content
    except RateLimitError as e:
        logging.warning(f"OpenAI rate limited: {e}")
    except (BadRequestError, APIError) as e:
        logging.error(f"OpenAI API error: {e}")
    except Exception as e:
        logging.error(f"OpenAI unexpected error: {e}")
    return None


def simple_detect_category(text: str) -> str:
    """
    Simple rule-based category detection (no extra OpenAI call).
    """
    low = text.lower()
    if any(k in low for k in ["land", "property", "flat", "plot", "rent", "lease"]):
        return "property"
    if any(k in low for k in ["police", "fir", "ipc", "crime", "criminal"]):
        return "police"
    if any(k in low for k in ["marriage", "divorce", "child", "maintenance", "498a", "husband", "wife", "family"]):
        return "family"
    if any(k in low for k in ["company", "job", "office", "employment", "salary", "gratuity", "pf"]):
        return "business"
    if any(k in low for k in ["loan", "money", "recovery", "refund", "cheque", "bounce", "debt"]):
        return "money"
    return "other"


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


# ---------------- WAIT MESSAGE (LANGUAGE-SPECIFIC) ----------------


def get_wait_message(lang: str) -> str:
    if lang == "Marathi":
        return "🧠 योग्य कायदेशीर माहिती मिळवत आहे…\nकृपया थोडा वेळ प्रतीक्षा करा."
    if lang == "Hinglish":
        return "🧠 Sahi legal information check kar raha hoon…\nKripya thoda intezaar karein."
    return "🧠 Gathering the correct legal information…\nPlease wait a moment."


# ---------------- RAZORPAY PAYMENT LINK ----------------


def create_payment_link(case_id: str, whatsapp_number: str, amount_in_rupees: int = CONSULT_FEE_RS):
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
    # --- Verification ---
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

        if not wa_from or not text_body.strip():
            return jsonify({"status": "empty"}), 200

        # Sanitize raw text for date parsing – take only last line if multi-line
        if "\n" in text_body:
            raw_text_body = text_body.split("\n")[-1].strip()
        else:
            raw_text_body = text_body.strip()

        logging.info(f"Parsed text_body={text_body!r}, raw_text_body={raw_text_body!r}")

        # Register user & store incoming message
        user = register_user(wa_from)
        store_message(wa_from, "user", text_body)
        conv_count = user_message_count(wa_from)
        lang_for_user = normalize_language_name(user.language) if user.language else "English"

        # ---------- FIRST MESSAGE → WELCOME + LANGUAGE SELECTION ----------
        if conv_count == 1 and user.language is None:
            typing_on(wa_from)
            time.sleep(TYPING_DELAY)
            welcome_text = WELCOME["English"].format(case=user.case_id)
            send_text(wa_from, welcome_text)
            typing_off(wa_from)

            send_buttons(
                wa_from,
                "Choose the language you are most comfortable with 👇",
                LANGUAGE_BUTTONS,
            )
            return jsonify({"status": "ask_language"}), 200

        message = text_body.strip().lower()

        # ---------- LANGUAGE SELECTION HANDLER ----------
        if text_body in ("lang_en", "lang_hinglish", "lang_marathi"):
            if text_body == "lang_en":
                user.language = "English"
            elif text_body == "lang_hinglish":
                user.language = "Hinglish"
            else:
                user.language = "Marathi"
            db.commit()

            lang_for_user = normalize_language_name(user.language)

            if lang_for_user == "Marathi":
                msg_lang = "कृपया तुमचा कायदेशीर प्रश्न मराठीत लिहा."
            elif lang_for_user == "Hinglish":
                msg_lang = "Ab apna legal issue Hinglish (Hindi + English mix) me type karein."
            else:
                msg_lang = "Please type your legal issue in English."

            send_text(wa_from, msg_lang)
            return jsonify({"status": "language_set"}), 200

        # ---------- LIMIT-ACTION BUTTON HANDLER (AFTER FREE REPLIES) ----------
        if text_body == "action_call":
            send_text(wa_from, "📞 Click to call NyaySetu: tel:7020030080")
            return jsonify({"status": "action_call"}), 200

        if text_body == "action_visit":
            send_text(wa_from, "🌐 Visit NyaySetu: https://nyaysetu.in/")
            return jsonify({"status": "action_visit"}), 200

        if text_body == "action_notice":
            if lang_for_user == "Marathi":
                send_text(
                    wa_from,
                    "📄 लवकरच येथे थेट WhatsApp वरून कायदेशीर नोटीस ड्राफ्ट करण्याची सुविधा येत आहे."
                )
            elif lang_for_user == "Hinglish":
                send_text(
                    wa_from,
                    "📄 Jaldi hi yahan se directly WhatsApp par legal notice draft karne ki facility available hogi."
                )
            else:
                send_text(
                    wa_from,
                    "📄 Coming soon: You will be able to draft and send a legal notice directly from NyaySetu on WhatsApp."
                )
            return jsonify({"status": "action_notice"}), 200

        if text_body == "action_book":
            pending_booking_state[wa_from] = {"date": None, "step": "awaiting_date"}
            send_list_dates(wa_from)
            return jsonify({"status": "ask_date"}), 200

        # ---------- BOOKING ENTRY POINT (TEXT) ----------
        if message in {
            "book", "booking", "consult", "consultation", "appointment",
            "📅 book consultation"
        }:
            pending_booking_state[wa_from] = {"date": None, "step": "awaiting_date"}
            send_list_dates(wa_from)
            return jsonify({"status": "ask_date"}), 200

        # ---------- DATE SELECTION (FROM LIST OR MANUAL TEXT) ----------
        if text_body.startswith("DATE_") or parse_date_from_text(raw_text_body):
            date_str = parse_date_from_text(text_body) or parse_date_from_text(raw_text_body)
            if not date_str:
                if lang_for_user == "Marathi":
                    send_text(wa_from, "मला हा दिनांक समजला नाही. कृपया लिस्टमधून दिनांक पुन्हा निवडा.")
                elif lang_for_user == "Hinglish":
                    send_text(wa_from, "Mujhe yeh date samajh nahi aaya. Kripya list se dobara date select karein.")
                else:
                    send_text(wa_from, "Sorry, I could not understand this date. Please select again from the list.")
                return jsonify({"status": "date_parse_error"}), 200

            pending_booking_state[wa_from] = {"date": date_str, "step": "awaiting_time"}
            logging.info(f"User {wa_from} selected date {date_str}")

            send_buttons(
                wa_from,
                f"📅 Date selected: *{date_str}*\n\nNow choose a time slot:",
                [
                    {"id": "TIME_morning", "title": "Morning (10 AM – 1 PM)"},
                    {"id": "TIME_afternoon", "title": "Afternoon (1 PM – 4 PM)"},
                    {"id": "TIME_evening", "title": "Evening (4 PM – 7 PM)"},
                ],
            )
            return jsonify({"status": "ask_time"}), 200

        # ---------- TIME SLOT SELECTION ----------
        if text_body in TIME_SLOTS:
            state = pending_booking_state.get(wa_from)
            date_str = state["date"] if state and state.get("date") else None

            if not date_str:
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

            booking = create_booking(wa_from, preferred_text)

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

        # ---------- FREE ANSWERS LIMIT CHECK (BEFORE AI REPLY) ----------
        booking_status = get_latest_booking_status(wa_from)
        legal_answer_count = count_legal_bot_answers(wa_from)

        if booking_status != "confirmed" and legal_answer_count >= MAX_FREE_ANSWERS:
            limit_msg = FREE_LIMIT.get(lang_for_user, FREE_LIMIT["English"])
            send_buttons(
                wa_from,
                limit_msg,
                LIMIT_ACTION_BUTTONS,
            )
            return jsonify({"status": "limit_reached"}), 200

        # ---------- DUPLICATE MESSAGE PROTECTION ----------
        last_user_msgs = (
            db.query(Conversation)
            .filter_by(whatsapp=wa_from, direction="user")
            .order_by(Conversation.ts.desc())
            .limit(2)
            .all()
        )
        if len(last_user_msgs) == 2:
            t0 = (last_user_msgs[0].text or "").strip()
            t1 = (last_user_msgs[1].text or "").strip()
            if t0 and t0 == t1:
                send_text(wa_from, "I’ve already answered this for you. Please check the previous message.")
                return jsonify({"status": "duplicate"}), 200

        # ---------- NORMAL LEGAL AI REPLY (USES SELECTED LANGUAGE) ----------
        lang_for_user = normalize_language_name(user.language or "English")
        category = simple_detect_category(text_body)
        logging.info(f"Lang={lang_for_user}, Category={category}")

        # ---------- SMART TYPING + BACKGROUND AI CALL + WAIT MESSAGE ----------
        ai_result = {"text": None}

        def ai_worker():
            try:
                ai_text = legal_reply(text_body, lang_for_user, category)
                ai_result["text"] = ai_text
            except Exception:
                logging.exception("AI worker failed")
                ai_result["text"] = None

        thread = threading.Thread(target=ai_worker, daemon=True)
        thread.start()

        typing_on(wa_from)
        start_time = time.time()
        sent_wait_message = False

        # While the AI thread runs, keep sending typing_on every ~1.5 seconds
        # and send a wait message after ~3 seconds if still not ready.
        while thread.is_alive():
            elapsed = time.time() - start_time

            if not sent_wait_message and elapsed > 3:
                wait_msg = get_wait_message(lang_for_user)
                send_text(wa_from, wait_msg)
                sent_wait_message = True

            typing_on(wa_from)
            time.sleep(1.5)

            # Safety break after ~25 seconds to avoid hanging
            if elapsed > 25:
                break

        typing_off(wa_from)

        # If thread is still alive after safety break, we don't block further
        if thread.is_alive():
            reply = ai_result.get("text")
        else:
            reply = ai_result.get("text")

        if not reply:
            # fallback friendly message
            if lang_for_user == "Marathi":
                reply = "माफ करा, सध्या उत्तर देताना अडचण येत आहे. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा."
            elif lang_for_user == "Hinglish":
                reply = "Sorry, abhi jawab dene me dikkat aa rahi hai. Thodi der baad phir try karein."
            else:
                reply = "Sorry, I’m having trouble generating a reply right now. Please try again in a little while."

        send_text(wa_from, reply)
        store_message(wa_from, "bot", reply)

        return jsonify({"status": "answered"}), 200

    except Exception as e:
        logging.exception("Webhook error")
        return jsonify({"status": "error", "error": str(e)}), 500


# ---------------- RAZORPAY WEBHOOK ----------------


@app.route("/payment/webhook", methods=["POST"])
def payment_webhook():
    event = request.get_json(silent=True) or {}
    logging.info(f"Razorpay webhook: {event}")

    try:
        event_type = event.get("event")

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


# ---------------- HEALTH CHECK ----------------


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


# ---------------- RUN (LOCAL DEV) ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting NyaySetu app on port {port}")
    app.run(host="0.0.0.0", port=port)
