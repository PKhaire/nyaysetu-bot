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

client = OpenAI(api_key=OPENAI_API_KEY)

MAX_FREE_MESSAGES = 6  # free replies before booking prompt
TYPING_DELAY = 1.0

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
    direction = Column(String)  # user/bot
    text = Column(Text)
    ts = Column(DateTime, default=datetime.utcnow)

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    whatsapp = Column(String, index=True)
    preferred_time = Column(String)
    otp = Column(String)
    otp_valid = Column(DateTime)
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
    logging.info(f"SEND TEXT => {text}")
    requests.post(w_url(), headers=w_headers(), json=payload)

def send_buttons(to, message, buttons):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": message},
            "action": {"buttons": [{"type": "reply", "reply": b} for b in buttons]}
        }
    }
    requests.post(w_url(), headers=w_headers(), json=payload)

def typing_on(to):
    requests.post(w_url(), headers=w_headers(),
                  json={"messaging_product": "whatsapp", "to": to, "type": "typing_on"})

def typing_off(to):
    requests.post(w_url(), headers=w_headers(),
                  json={"messaging_product": "whatsapp", "to": to, "type": "typing_off"})


# ---------------- USER + MESSAGE TRACKING ----------------

def register_user(w_id):
    user = db.query(User).filter_by(whatsapp=w_id).first()
    if user:
        return user
    case_id = f"NS-{uuid.uuid4().hex[:8].upper()}"
    user = User(whatsapp=w_id, case_id=case_id, language="English")
    db.add(user)
    db.commit()
    return user

def store_message(w_id, direction, text):
    msg = Conversation(whatsapp=w_id, direction=direction, text=text)
    db.add(msg)
    db.commit()

def user_message_count(w_id):
    return db.query(Conversation).filter_by(whatsapp=w_id, direction="user").count()


# ---------------- BOOKING UTILITIES ----------------

def create_booking(w_id, preferred):
    otp = f"{random.randint(100000, 999999)}"
    booking = Booking(
        whatsapp=w_id,
        preferred_time=preferred,
        otp=otp,
        otp_valid=datetime.utcnow() + timedelta(minutes=10),
        confirmed=False
    )
    db.add(booking)
    db.commit()
    return booking

def verify_booking(w_id, otp_input):
    booking = db.query(Booking).filter_by(whatsapp=w_id).order_by(Booking.created_at.desc()).first()
    if not booking:
        return False, "No booking found."
    if booking.otp != otp_input:
        return False, "Incorrect OTP."
    if datetime.utcnow() > booking.otp_valid:
        return False, "OTP expired."
    booking.confirmed = True
    db.commit()
    return True, booking

def get_booking_status(w_id):
    booking = db.query(Booking).filter_by(whatsapp=w_id).order_by(Booking.created_at.desc()).first()
    if not booking:
        return None
    if booking.confirmed:
        return "confirmed"
    return "pending"


# ---------------- OPENAI / MULTILINGUAL LEGAL AI ----------------

def call_openai(messages, temperature=0.2, max_tokens=300):
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
            time.sleep(1.2)
        except Exception as e:
            logging.error(f"OpenAI ERROR: {e}")
            break
    return None

def detect_language(text):
    prompt = f"Identify the language of this text, return only the language name: {text}"
    return call_openai([{"role": "user", "content": prompt}], max_tokens=10) or "English"

def detect_category(text):
    prompt = (
        "Classify message into ONE category: property, police, family, business, money, other.\n"
        f"Message: {text}\nReturn only the category."
    )
    return (call_openai([{"role": "user", "content": prompt}], max_tokens=10) or "other").lower()

def legal_reply(text, lang, category):
    system_prompt = (
        "You are an ethical professional legal advisor. Reply in the SAME language the user uses. "
        "Give short & clear legal information (2–4 sentences). If deeper help is needed, gently "
        "suggest booking consultation."
    )
    user_input = f"[Language: {lang}] [Category: {category}] {text}"
    res = call_openai([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ])
    return res or "Currently unable to respond. Please try again."

# ---------------- WELCOME TEMPLATE ----------------

WELCOME_TEMPLATE = (
    "👋 Welcome to NyaySetu — The Bridge To Justice.\n\n"
    "Your Case ID: {case_id}\n"
    "I’m your NyaySetu Legal Assistant.\n\n"
    "Please tell me your legal issue.\n"
    "I will guide you clearly, safely, and confidentially."
)

TIME_KEYWORDS = [
    "morning", "evening", "afternoon", "night",
    "tmr", "tmrw", "tommorow", "tomorrow",
    "today", "tonight",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "sat", "sun", "mon", "tue", "wed", "thu", "fri"
]


# ---------------- WEBHOOK ----------------

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

        # extract text (including interactive button replies)
        text_body = ""
        if msg_type == "text":
            text_body = msg.get("text", {}).get("body", "") or ""
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            if "button_reply" in interactive:
                text_body = interactive["button_reply"].get("id") or interactive["button_reply"].get("title", "")
            elif "list_reply" in interactive:
                text_body = interactive["list_reply"].get("id") or interactive["list_reply"].get("title", "")
        else:
            # For now, ignore media/other types, ask user to send text
            send_text(wa_from, "Please type your legal question in text so I can guide you properly.")
            return jsonify({"status": "unsupported_type"}), 200

        if not wa_from or not text_body.strip():
            return jsonify({"status": "empty"}), 200

        user = register_user(wa_from)
        store_message(wa_from, "user", text_body)
        conv_count = user_message_count(wa_from)

        # -------- FIRST MESSAGE → WELCOME FLOW --------
        if conv_count <= 1:
            lang = detect_language(text_body)
            user.language = lang
            db.commit()

            typing_on(wa_from)
            time.sleep(TYPING_DELAY)
            welcome_text = WELCOME_TEMPLATE.format(case_id=user.case_id)
            send_text(wa_from, welcome_text)
            typing_off(wa_from)

            # show quick buttons
            send_buttons(wa_from, "You can also choose a category:", [
                {"id": "police", "title": "🚨 Police / FIR"},
                {"id": "family", "title": "👪 Family / Marriage"},
                {"id": "property", "title": "🏠 Property / Land"},
                {"id": "money", "title": "💰 Money / Recovery"},
                {"id": "business", "title": "💼 Business / Contract"},
            ])
            return jsonify({"status": "welcome"}), 200

        # normalize message
        message = text_body.strip().lower()

        # -------- 1) BOOKING KEYWORDS (always allowed, even after free limit) --------
        if message in ["book", "booking", "consult", "consultation", "appointment", "lawyer", "📅 book consultation", "book consultation"]:
            send_text(
                wa_from,
                "📅 Sure — Please reply with your preferred time.\n"
                "For example:\n"
                "• Tomorrow Morning\n"
                "• Today Evening\n"
                "• Sunday Afternoon"
            )
            return jsonify({"status": "ask_time"}), 200

        # -------- 2) PREFERRED TIME DETECTION --------
        if any(key in message for key in TIME_KEYWORDS):
            booking = create_booking(wa_from, text_body.strip())
            send_text(
                wa_from,
                f"📝 Thank you. We’ve noted your preferred time as:\n*{booking.preferred_time}*\n\n"
                f"🔐 Your OTP is *{booking.otp}* (valid 10 minutes).\n\n"
                f"To confirm, reply:\n*CONFIRM {booking.otp}*\n\n"
                f"Or click to pay & confirm: (payment link demo)\nhttps://pay.nyaysetu.in/?case={user.case_id}"
            )
            return jsonify({"status": "booking_created"}), 200

        # -------- 3) OTP CONFIRMATION --------
        if message.startswith("confirm"):
            parts = message.split()
            if len(parts) >= 2:
                otp_candidate = parts[1]
                ok, res = verify_booking(wa_from, otp_candidate)
                if ok:
                    booking = res
                    send_text(
                        wa_from,
                        f"🎉 Your booking is confirmed for *{booking.preferred_time}*.\n"
                        "A lawyer will call you at the scheduled time."
                    )
                    send_text(
                        wa_from,
                        "🙏 Thank you for trusting *NyaySetu — The Bridge To Justice*.\n"
                        "We are with you at every step."
                    )
                    return jsonify({"status": "booking_confirmed"}), 200
                else:
                    send_text(
                        wa_from,
                        f"❌ OTP verification failed: {res}\n\n"
                        "You can reply *BOOK* to restart booking."
                    )
                    return jsonify({"status": "otp_failed"}), 200

        # -------- 4) FREE TRIAL CHECK (after booking handling) --------
        booking_status = get_booking_status(wa_from)
        msg_count = user_message_count(wa_from)

        # if already confirmed booking → don't block with free limit
        if booking_status != "confirmed":
            if msg_count >= MAX_FREE_MESSAGES:
                send_text(
                    wa_from,
                    "🛑 You have used your free legal answers.\n\n"
                    "To continue with personalised legal help and speak to a lawyer, "
                    "please reply *BOOK* to book a consultation."
                )
                return jsonify({"status": "limit_reached"}), 200

        # -------- 5) NORMAL LEGAL AI REPLY --------
        lang = detect_language(text_body)
        category = detect_category(text_body)
        logging.info(f"Lang={lang}, Category={category}")

        typing_on(wa_from)
        time.sleep(TYPING_DELAY)
        reply = legal_reply(text_body, lang, category)
        typing_off(wa_from)

        send_text(wa_from, reply)
        store_message(wa_from, "bot", reply)

        # follow-up buttons
        send_buttons(wa_from, "You can choose what to do next:", [
            {"id": "book", "title": "📅 Book Consultation"},
            {"id": "call", "title": "📞 Speak to Lawyer"},
            {"id": "draft", "title": "📄 Get Draft Notice"},
        ])

        return jsonify({"status": "answered"}), 200

    except Exception as e:
        logging.exception("Webhook error")
        return jsonify({"status": "error", "error": str(e)}), 500


# ---------------- ADMIN DASHBOARD (SIMPLE) ----------------

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminpass")

ADMIN_HTML = """
<html>
  <head><title>NyaySetu Admin</title></head>
  <body>
    <h1>NyaySetu Admin Dashboard</h1>
    <p>Leads & bookings overview</p>

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
def admin():
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


# ---------------- RUN APP (for local dev) ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting NyaySetu on port {port}")
    app.run(host="0.0.0.0", port=port)
