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

# ---------------- CONFIG ----------------

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")

PRIMARY_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "xxxx")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "yyyy")

client = OpenAI(api_key=OPENAI_API_KEY)

MAX_FREE_MESSAGES = 6          # free answers before booking CTA
TYPING_DELAY = 1.0            # seconds
CONSULT_FEE_RS = 499          # ₹499 for 45 min consultation

# in-memory state for date selection step: {whatsapp_id: "YYYY-MM-DD"}
pending_booking_dates = {}

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
    preferred_time = Column(String)  # e.g. "2025-11-30 — Afternoon (1 PM – 4 PM)"
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


def send_text(to, text):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    logging.info(f"SEND TEXT => {to}: {text}")
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Error sending WhatsApp text: {e}")


def send_buttons(to, body_text, buttons):
    """
    buttons: list of {"id": "BOOK", "title": "📅 Book Consultation"} etc.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": b}
                    for b in buttons
                ]
            }
        }
    }
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Error sending buttons: {e}")


def send_list_dates(to, days=7):
    """
    Send WhatsApp interactive list for next `days` days.
    Each row id: DATE_YYYY-MM-DD
    """
    today = datetime.now()
    rows = []
    for i in range(days):
        d = today + timedelta(days=i)
        date_id = d.strftime("DATE_%Y-%m-%d")
        title = d.strftime("%a, %d %b")
        rows.append({
            "id": date_id,
            "title": title,
            "description": ""
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": "📅 Please select your preferred date for consultation:"},
            "action": {
                "button": "Choose Date",
                "sections": [
                    {
                        "title": "Available Dates",
                        "rows": rows
                    }
                ]
            }
        }
    }
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Error sending date list: {e}")


def typing_on(to):
    try:
        requests.post(
            w_url(), headers=w_headers(),
            json={"messaging_product": "whatsapp", "to": to, "type": "typing_on"},
            timeout=5
        )
    except Exception:
        pass


def typing_off(to):
    try:
        requests.post(
            w_url(), headers=w_headers(),
            json={"messaging_product": "whatsapp", "to": to, "type": "typing_off"},
            timeout=5
        )
    except Exception:
        pass


# ---------------- USER & CONVERSATION HELPERS ----------------

def register_user(wa_id):
    user = db.query(User).filter_by(whatsapp=wa_id).first()
    if user:
        return user
    case_id = f"NS-{uuid.uuid4().hex[:8].upper()}"
    user = User(whatsapp=wa_id, case_id=case_id, language="English")
    db.add(user)
    db.commit()
    logging.info(f"New user registered: {wa_id} → {case_id}")
    return user


def store_message(wa_id, direction, text):
    msg = Conversation(whatsapp=wa_id, direction=direction, text=text)
    db.add(msg)
    db.commit()


def user_message_count(wa_id):
    return db.query(Conversation).filter_by(whatsapp=wa_id, direction="user").count()


def get_latest_booking_status(wa_id):
    b = (
        db.query(Booking)
        .filter_by(whatsapp=wa_id)
        .order_by(Booking.created_at.desc())
        .first()
    )
    if not b:
        return None
    return "confirmed" if b.confirmed else "pending"


def create_booking(wa_id, preferred_time_text):
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
        except RateLimitError:
            time.sleep(backoff)
            backoff *= 2
        except (BadRequestError, APIError) as e:
            logging.error(f"OpenAI API error: {e}")
            break
        except Exception as e:
            logging.error(f"OpenAI unknown error: {e}")
            time.sleep(backoff)
            backoff *= 2
    return None


def detect_language(text):
    prompt = f"Identify the language of this text, return only the language name: {text}"
    res = call_openai([{"role": "user", "content": prompt}], max_tokens=20)
    return res or "English"


def detect_category(text):
    prompt = (
        "Classify the legal topic of this message into one word from: "
        "property, police, family, business, money, other.\n"
        f"Message: {text}\n"
        "Return only the category."
    )
    res = call_openai([{"role": "user", "content": prompt}], max_tokens=10)
    if not res:
        return "other"
    return res.strip().lower()


def legal_reply(text, lang, category):
    system_prompt = (
        "You are a professional, ethical legal assistant for Indian law. "
        "You ALWAYS reply in the same language as the user. "
        "Give clear, simple, trustworthy information in 2–4 sentences. "
        "If the matter is serious or complex, recommend speaking to a lawyer and booking a consultation."
    )
    user_msg = f"[Language: {lang}] [Category: {category}] {text}"
    res = call_openai(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=220,
    )
    return res or "Sorry, I am unable to prepare a proper answer right now. Please try again."


# ---------------- RAZORPAY PAYMENT LINK ----------------

def create_payment_link(case_id, whatsapp_number, amount_in_rupees=CONSULT_FEE_RS):
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
            "customer": {
                "contact": whatsapp_number  # e.g. "9198xxxxxxx"
            },
            "notify": {
                "sms": True,
                "email": False,
            },
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
# ---------------- CONSTANTS FOR MESSAGES ----------------

WELCOME_TEMPLATE = (
    "👋 Welcome to NyaySetu — The Bridge To Justice.\n\n"
    "Your Case ID: {case_id}\n"
    "I’m your NyaySetu Legal Assistant.\n\n"
    "Please tell me your legal issue.\n"
    "I will guide you clearly, safely, and confidentially."
)

TIME_SLOTS = {
    "TIME_morning": ("Morning", "10 AM – 1 PM"),
    "TIME_afternoon": ("Afternoon", "1 PM – 4 PM"),
    "TIME_evening": ("Evening", "4 PM – 7 PM"),
}


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

    # --- Incoming message ---
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

        # Extract text/interactive content
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

        user = register_user(wa_from)
        store_message(wa_from, "user", text_body)
        conv_count = user_message_count(wa_from)

        # ---------- FIRST MESSAGE → WELCOME ----------
        if conv_count <= 1:
            lang = detect_language(text_body)
            user.language = lang
            db.commit()

            typing_on(wa_from)
            time.sleep(TYPING_DELAY)
            welcome_text = WELCOME_TEMPLATE.format(case_id=user.case_id)
            send_text(wa_from, welcome_text)
            typing_off(wa_from)

            # suggestions
            send_buttons(
                wa_from,
                "You can also choose a category to start:",
                [
                    {"id": "police", "title": "🚨 Police / FIR"},
                    {"id": "family", "title": "👪 Family / Marriage"},
                    {"id": "property", "title": "🏠 Property / Land"},
                    {"id": "money", "title": "💰 Money / Recovery"},
                    {"id": "business", "title": "💼 Business / Work"},
                ],
            )
            return jsonify({"status": "welcome"}), 200

        message = text_body.strip().lower()

        # ---------- BOOKING ENTRY POINT ----------
        if message in ["book", "booking", "consult", "consultation", "appointment", "📅 book consultation"]:
            send_list_dates(wa_from)
            return jsonify({"status": "ask_date"}), 200

        # ---------- DATE SELECTION (list reply) ----------
        if text_body.startswith("DATE_"):
            # e.g. DATE_2025-11-30
            date_str = text_body.replace("DATE_", "")
            pending_booking_dates[wa_from] = date_str
            logging.info(f"User {wa_from} selected date {date_str}")

            # send time-of-day buttons
            send_buttons(
                wa_from,
                f"Date selected: {date_str}\n\nNow choose a time:",
                [
                    {"id": "TIME_morning", "title": "🌅 Morning (10 AM – 1 PM)"},
                    {"id": "TIME_afternoon", "title": "🌞 Afternoon (1 PM – 4 PM)"},
                    {"id": "TIME_evening", "title": "🌙 Evening (4 PM – 7 PM)"},
                ],
            )
            return jsonify({"status": "ask_time"}), 200

        # ---------- TIME SLOT SELECTION ----------
        if text_body in TIME_SLOTS:
            date_str = pending_booking_dates.get(wa_from)
            if not date_str:
                send_text(wa_from, "Please first select a date. Reply *BOOK* to start booking again.")
                return jsonify({"status": "no_date"}), 200

            slot_label, window = TIME_SLOTS[text_body]
            preferred_text = f"{date_str} — {slot_label} ({window})"

            # Create booking
            booking = create_booking(wa_from, preferred_text)

            # Create Razorpay payment link
            payment_url = create_payment_link(user.case_id, wa_from, amount_in_rupees=CONSULT_FEE_RS)
            if not payment_url:
                send_text(
                    wa_from,
                    "Sorry, I could not create the payment link right now. "
                    "Please try again after some time."
                )
                return jsonify({"status": "payment_link_error"}), 200

            msg_out = (
                f"📝 Thank you. We’ve scheduled your session for:\n"
                f"*{booking.preferred_time}*\n\n"
                f"💰 To confirm your 45-minute legal expert call, please pay *₹{CONSULT_FEE_RS}*.\n"
                f"🔗 Payment Link: {payment_url}\n\n"
                "As soon as the payment is completed, your appointment will be confirmed instantly, "
                "and a verified legal expert will call you within the selected time window."
            )
            send_text(wa_from, msg_out)
            return jsonify({"status": "booking_created"}), 200

        # ---------- FREE MESSAGE LIMIT (AFTER BOOKING HANDLERS) ----------
        booking_status = get_latest_booking_status(wa_from)
        msg_count = user_message_count(wa_from)

        if booking_status != "confirmed" and msg_count >= MAX_FREE_MESSAGES:
            send_text(
                wa_from,
                "🛑 You have used your free legal answers.\n\n"
                "To continue with personalised legal help, please book a consultation.\n"
                "Reply *BOOK* to book a call with a legal expert."
            )
            return jsonify({"status": "limit_reached"}), 200

        # ---------- NORMAL LEGAL AI REPLY ----------
        lang = detect_language(text_body)
        category = detect_category(text_body)
        logging.info(f"Lang={lang}, Category={category}")

        typing_on(wa_from)
        time.sleep(TYPING_DELAY)
        reply = legal_reply(text_body, lang, category)
        typing_off(wa_from)

        send_text(wa_from, reply)
        store_message(wa_from, "bot", reply)

        # Suggest next steps
        send_buttons(
            wa_from,
            "You can also choose what to do next:",
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
# Configure this URL in Razorpay dashboard as:
# https://api.nyaysetu.in/payment/webhook

@app.route("/payment/webhook", methods=["POST"])
def payment_webhook():
    event = request.get_json(silent=True) or {}
    logging.info(f"Razorpay webhook: {event}")

    try:
        event_type = event.get("event")
        if event_type == "payment_link.paid":
            payment_link_entity = event.get("payload", {}) \
                                       .get("payment_link", {}) \
                                       .get("entity", {})

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

                    confirm_msg = (
                        "🎉 Payment received successfully!\n\n"
                        f"📌 Your consultation is confirmed for *{booking.preferred_time}*.\n"
                        "A verified NyaySetu legal expert will call you in this time window.\n\n"
                        "Thank you for trusting *NyaySetu — The Bridge To Justice*."
                    )
                    send_text(contact, confirm_msg)

    except Exception as e:
        logging.error(f"Error handling Razorpay webhook: {e}")

    return "", 200


# ---------------- ADMIN DASHBOARD ----------------

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminpass")

ADMIN_HTML = """
<html>
  <head><title>NyaySetu Admin</title></head>
  <body>
    <h1>NyaySetu Admin Dashboard</h1>
    <p>Simple overview of leads and bookings.</p>

    <h2>Users</h2>
    <table border="1" cellpadding="6">
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
    <table border="1" cellpadding="6">
      <tr><th>WhatsApp</th><th>Preferred Time</th><th>Confirmed</th><th>Created</th></tr>
      {% for b in bookings %}
      <tr>
        <td>{{b.whatsapp}}</td>
        <td>{{b.preferred_time}}</td>
        <td>{{b.confirmed}}</td>
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
    users = db.query(User).order_by(User.created_at.desc()).limit(100).all()
    bookings = db.query(Booking).order_by(Booking.created_at.desc()).limit(100).all()
    return render_template_string(ADMIN_HTML, users=users, bookings=bookings)


# ---------------- HEALTH CHECK ----------------

@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


# ---------------- RUN (for local dev) ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting NyaySetu app on port {port}")
    app.run(host="0.0.0.0", port=port)
