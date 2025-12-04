# app.py — NyaySetu WhatsApp Legal Assistant

import os
import time
import uuid
import random
import logging
import requests
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI, RateLimitError, APIError, BadRequestError

from config import (
    OPENAI_API_KEY,
    PRIMARY_MODEL,
    WHATSAPP_PHONE_ID,
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_VERIFY_TOKEN,
    MAX_FREE_MESSAGES,
    TYPING_DELAY_SECONDS,
    ADMIN_PASSWORD,
)

from db import Base, engine, SessionLocal
import models  # ensure models are registered with Base
from models import User, Conversation, Booking, Lawyer

# ---------------- APP & LOGGING ----------------

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# WhatsApp / OpenAI / Business constants
VERIFY_TOKEN = WHATSAPP_VERIFY_TOKEN
TYPING_DELAY = TYPING_DELAY_SECONDS
CONSULT_FEE_RS = 499  # ₹ for 45-min consultation

# Razorpay keys (still read directly from env)
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "xxxx")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "yyyy")

# ---------------- DATABASE SESSION ----------------

# Create tables (if not already created)
Base.metadata.create_all(bind=engine)

# Global DB session (simple for Render free tier)
db = SessionLocal()

# In-memory booking state (for date/time flow)
pending_booking_state = {}  # {whatsapp_id: {"date": "YYYY-MM-DD", "step": "..."}}
# ---------------- WHATSAPP HELPERS ----------------

def w_headers():
    return {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def w_url():
    return f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_ID}/messages"


def send_text(to: str, text: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    logging.info(f"SEND TEXT => {to}: {text}")
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=15)
    except Exception as e:
        logging.error(f"Error sending WhatsApp text: {e}")


def send_buttons(to: str, body: str, buttons: list):
    """
    buttons: list of dicts with keys: id, title
      e.g. {"id": "book", "title": "📅 Book Consultation"}
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
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons
                ]
            },
        },
    }
    logging.info(f"SEND BUTTONS => {to}: {body} :: {buttons}")
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=15)
    except Exception as e:
        logging.error(f"Error sending WhatsApp buttons: {e}")


def typing_on(to: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "typing",
        "state": "typing_on",
    }
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except Exception:
        pass


def typing_off(to: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "typing",
        "state": "typing_off",
    }
    try:
        requests.post(w_url(), headers=w_headers(), json=payload, timeout=10)
    except Exception:
        pass


# ---------------- CONSTANTS FOR MESSAGES ----------------

WELCOME = {
    "English": (
        "👋 Welcome to *NyaySetu — The Bridge To Justice*.\n\n"
        "Your Case ID: *{case}*\n"
        "I’m your NyaySetu Legal Assistant.\n\n"
        "Please briefly describe your legal issue.\n"
        "I’ll help you with clear, simple, and confidential guidance."
    ),
    "Hinglish": (
        "👋 *NyaySetu — The Bridge To Justice* mein aapka swagat hai.\n\n"
        "Aapka Case ID: *{case}*\n"
        "Main aapka NyaySetu Legal Assistant hoon.\n\n"
        "Kripya apni legal problem short mein bataiye.\n"
        "Main aapko simple aur safe tariqe se guide karunga."
    ),
    "Marathi": (
        "👋 *न्यायसेतू — The Bridge To Justice* मध्ये आपले स्वागत आहे.\n\n"
        "आपला Case ID: *{case}*\n"
        "मी तुमचा NyaySetu Legal Assistant आहे.\n\n"
        "कृपया तुमची कायदेशीर समस्या थोडक्यात लिहा.\n"
        "मी तुम्हाला सोप्या आणि विश्वासार्ह पद्धतीने मार्गदर्शन करेन."
    ),
}

INTRO_SUGGESTIONS = [
    {"id": "category_property", "title": "🏠 Property / Rent"},
    {"id": "category_police", "title": "👮 Police / FIR"},
    {"id": "category_family", "title": "👪 Family / Marriage"},
    {"id": "category_money", "title": "💰 Loan / Money"},
]

TIME_SLOTS = {
    "TIME_morning": ("Morning", "10 AM – 1 PM"),
    "TIME_afternoon": ("Afternoon", "1 PM – 4 PM"),
    "TIME_evening": ("Evening", "4 PM – 7 PM"),
}

FREE_LIMIT = {
    "English": (
        "🛑 You have used your *free legal answers*.\n\n"
        "To get personalised help from a real advocate, "
        "you can *book a 45-minute consultation call*.\n\n"
        "Reply *BOOK* to schedule your call."
    ),
    "Hinglish": (
        "🛑 Aapne apne *free legal answers* use kar liye hain.\n\n"
        "Agar aapko ek real lawyer se personalised madad chahiye, "
        "to aap *45-minute consultation call* book kar sakte hain.\n\n"
        "Call schedule karne ke liye *BOOK* likhein."
    ),
    "Marathi": (
        "🛑 तुम्ही तुमची *फ्री legal answers* वापरून झाली आहेत.\n\n"
        "जर तुम्हाला खऱ्या वकिलाकडून खास मार्गदर्शन हवे असेल तर "
        "तुम्ही *45-मिनिटांचे consultation call* बुक करू शकता.\n\n"
        "कॉल बुक करण्यासाठी *BOOK* असे लिहा."
    ),
}
# ---------------- DB HELPERS ----------------

def register_user(wa_id: str) -> User:
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()
    if user:
        return user

    # Create new user with unique Case ID
    case_id = f"NS-{uuid.uuid4().hex[:8].upper()}"
    user = User(whatsapp_id=wa_id, case_id=case_id, language="English")
    db.add(user)
    db.commit()
    db.refresh(user)
    logging.info(f"New user registered: {wa_id} → {case_id}")
    return user


def store_message(wa_id: str, direction: str, text: str):
    msg = Conversation(
        user_whatsapp_id=wa_id,
        direction=direction,
        text=text,
    )
    db.add(msg)
    db.commit()


def user_message_count(wa_id: str) -> int:
    return (
        db.query(Conversation)
        .filter_by(user_whatsapp_id=wa_id, direction="user")
        .count()
    )


def count_legal_questions(wa_id: str) -> int:
    """
    Count user legal questions (user messages).
    """
    return user_message_count(wa_id)


def get_latest_booking_status(wa_id: str) -> str:
    booking = (
        db.query(Booking)
        .filter_by(user_whatsapp_id=wa_id)
        .order_by(Booking.created_at.desc())
        .first()
    )
    if not booking:
        return "none"
    return "confirmed" if booking.confirmed else "pending"


def create_booking(wa_id: str, preferred_time_text: str) -> Booking:
    b = Booking(
        user_whatsapp_id=wa_id,
        preferred_time=preferred_time_text,
        confirmed=False,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


# ---------------- OPENAI HELPERS ----------------

def call_openai(messages, temperature=0.2, max_tokens=300):
    backoff = 1.0
    for attempt in range(4):
        try:
            res = client.chat.completions.create(
                model=PRIMARY_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return res.choices[0].message.content
        except RateLimitError:
            logging.warning("OpenAI rate limit – backing off")
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


def normalize_language_name(lang: str) -> str:
    if not lang:
        return "English"
    lang = lang.strip().lower()
    if "marathi" in lang:
        return "Marathi"
    if "hindi" in lang or "hinglish" in lang:
        return "Hinglish"
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
    Create a Razorpay Payment Link and return its short URL, or None on failure.
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
            timeout=15,
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

        raw_text_body = text_body
        if not wa_from or not text_body.strip():
            return jsonify({"status": "empty"}), 200

        # Register / fetch user and store incoming message
        user = register_user(wa_from)
        store_message(wa_from, "user", text_body)
        conv_count = user_message_count(wa_from)

        # ---------- FIRST MESSAGE → WELCOME FLOW ----------
        if conv_count <= 1:
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
        if message in ["book", "booking", "consult", "consultation", "appointment", "📅 book consultation"]:
            # Ask date by sending next 7 days as list of buttons
            today = datetime.utcnow().date()
            buttons = []
            for i in range(7):
                d = today + timedelta(days=i)
                btn_id = f"DATE_{d.isoformat()}"
                label = d.strftime("%d %b (%a)")
                buttons.append({"id": btn_id, "title": label})

            if lang_for_user == "Marathi":
                body = "कृपया तुमच्या consultation साठी दिनांक निवडा:"
            elif lang_for_user == "Hinglish":
                body = "Kripya consultation ke liye date choose karein:"
            else:
                body = "Please choose a date for your consultation:"

            send_buttons(wa_from, body, buttons[:3])  # WA allows up to 3 buttons
            # if more than 3 days needed, use list templates later
            pending_booking_state[wa_from] = {"step": "awaiting_date"}
            return jsonify({"status": "ask_date"}), 200

        # ---------- DATE SELECTION ----------
        if text_body.startswith("DATE_"):
            date_str = text_body.replace("DATE_", "")

            try:
                _ = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
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
            if lang_for_user == "Marathi":
                body = (
                    f"📅 निवडलेला दिनांक: *{date_str}*\n\n"
                    "आता कृपया वेळेचा slot निवडा:"
                )
            elif lang_for_user == "Hinglish":
                body = (
                    f"📅 Selected date: *{date_str}*\n\n"
                    "Ab kripya time slot choose karein:"
                )
            else:
                body = f"📅 Date selected: *{date_str}*\n\nNow choose a time slot:"

            send_buttons(
                wa_from,
                body,
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
                        "कृपया आधी दिनांक निवडा. जर नवीन बुकिंग सुरू करायची असेल तर *BOOK* लिहा.",
                    )
                elif lang_for_user == "Hinglish":
                    send_text(
                        wa_from,
                        "Please pehle date select karein. Agar naya booking start karna hai to *BOOK* likhein.",
                    )
                else:
                    send_text(
                        wa_from,
                        "Please first select a date from the list. "
                        "If you want to start again, reply with *BOOK*.",
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
                        "क्षमस्व, सध्या पेमेंट लिंक तयार karta आली नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
                    )
                elif lang_for_user == "Hinglish":
                    send_text(
                        wa_from,
                        "Sorry, abhi payment link create nahi ho paayi. Thodi der baad phir se try karein.",
                    )
                else:
                    send_text(
                        wa_from,
                        "Sorry, I could not create the payment link right now. "
                        "Please try again after some time.",
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
        detected_lang = detect_language(text_body)
        category = detect_category(text_body)
        logging.info(f"Lang={detected_lang}, Category={category}")

        typing_on(wa_from)
        time.sleep(TYPING_DELAY)
        reply = legal_reply(text_body, detected_lang, category)
        typing_off(wa_from)

        send_text(wa_from, reply)
        store_message(wa_from, "bot", reply)

        # Suggest next steps (only if still under free limit and not confirmed)
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
# https://api.nyaysetu.in/payment/webhook  (or your Render domain)

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
                    .filter_by(user_whatsapp_id=contact)
                    .order_by(Booking.created_at.desc())
                    .first()
                )

                if booking and not booking.confirmed:
                    booking.confirmed = True
                    db.commit()

                    # Detect user stored language
                    user = db.query(User).filter_by(whatsapp_id=contact).first()
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
      <td>{{u.whatsapp_id}}</td>
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
      <td>{{b.user_whatsapp_id}}</td>
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


# ---------------- RUN (for local dev) ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting NyaySetu app on port {port}")
    app.run(host="0.0.0.0", port=port)
