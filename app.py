# Map config values to local constants used in the app
VERIFY_TOKEN = WHATSAPP_VERIFY_TOKEN
TYPING_DELAY = TYPING_DELAY_SECONDS
# MAX_FREE_MESSAGES already comes from config

import os
import json
import logging
from datetime import datetime, timedelta

from flask import Flask, request

from config import WHATSAPP_VERIFY_TOKEN, MAX_FREE_MESSAGES, TYPING_DELAY_SECONDS
from db import get_user, create_user, update_user

# Services
from services.whatsapp_service import (
    send_text_message,
    send_button_message,
    send_list_message,
    send_call_button,
)

from services.openai_service import (
    detect_language,
    detect_category,
    generate_legal_reply,
)

# -----------------------------------------------------------------------------
# CONFIG & CONSTANTS
# -----------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

FREE_ANSWER_LIMIT = 6
NYAYSETU_PHONE = "7020030080"
NYAYSETU_URL = "https://nyaysetu.in/"


# -----------------------------------------------------------------------------
# UTILS: USER HELPER
# -----------------------------------------------------------------------------

def get_or_create_user(wa_id: str, name: str | None = None) -> dict:
    user = get_user(wa_id)
    if not user:
        user = create_user(wa_id)
        logging.info(f"New user registered: {wa_id} → {user.get('case_id')}")
    # Ensure new fields exist
    user.setdefault("state", "idle")
    user.setdefault("language", None)
    user.setdefault("free_count", 0)
    user.setdefault("history", [])          # list of dicts: {"q": ..., "a": ...}
    user.setdefault("pending_date", None)   # for booking flow
    user.setdefault("pending_time", None)
    return user


def save_user(user: dict) -> None:
    update_user(user)


# -----------------------------------------------------------------------------
# UTILS: LANGUAGE & MESSAGES
# -----------------------------------------------------------------------------

def language_display(lang: str | None) -> str:
    if lang == "hi":
        return "Hinglish"
    if lang == "mr":
        return "Marathi"
    return "English"


def send_welcome_and_language_buttons(wa_id: str, case_id: str | None = None):
    """First message: welcome + language selection buttons"""
    if not case_id:
        # Best-effort: we don't hit DB again here; just show generic welcome
        header = "👋 Welcome to NyaySetu — The Bridge To Justice."
        case_line = ""
    else:
        header = "👋 Welcome to NyaySetu — The Bridge To Justice."
        case_line = f"\nYour Case ID: {case_id}"

    body = (
        f"{header}{case_line}\n\n"
        "Please choose your preferred language:"
    )

    buttons = [
        {
            "type": "reply",
            "reply": {"id": "lang_en", "title": "English"},
        },
        {
            "type": "reply",
            "reply": {"id": "lang_hi", "title": "Hinglish"},
        },
        {
            "type": "reply",
            "reply": {"id": "lang_mr", "title": "Marathi"},
        },
    ]

    send_button_message(wa_id, body, buttons)


def send_ask_issue_message(user: dict):
    wa_id = user["user_id"]
    lang = user.get("language", "en")

    if lang == "hi":
        msg = "Please type your legal issue in Hinglish (Hindi in English letters)."
    elif lang == "mr":
        msg = "कृपया तुमचा कायदेशीर प्रश्न मराठीत किंवा इंग्रजीत लिहा."
    else:
        msg = "Please type your legal issue in English."

    send_text_message(wa_id, msg)


def send_wait_message(user: dict):
    lang = user.get("language", "en")
    wa_id = user["user_id"]

    # WaitMessage: B
    base = "🧠 Gathering the correct legal information…\nPlease wait a moment."

    if lang == "hi":
        msg = base + "\n(Thoda waqt lagega, kripya rukiyega.)"
    elif lang == "mr":
        msg = base + "\n(कृपया थोडा वेळ थांबा.)"
    else:
        msg = base

    send_text_message(wa_id, msg)


def send_free_limit_menu(user: dict):
    """Show 4 options after free answers are over."""
    wa_id = user["user_id"]
    lang = user.get("language", "en")

    if lang == "hi":
        intro = (
            "Aapke 6 free legal answers complete ho gaye hai.\n"
            "Ab aap inme se ek option choose kar sakte hai:"
        )
    elif lang == "mr":
        intro = (
            "तुमचे 6 free कायदेशीर उत्तर पूर्ण झाले आहेत.\n"
            "आता खालील पर्यायांपैकी एक निवडा:"
        )
    else:
        intro = (
            "Your 6 free legal answers are over.\n"
            "To get more personalised help, please choose an option:"
        )

    sections = [
        {
            "title": "Next steps",
            "rows": [
                {"id": "cta_call", "title": "📞 Call NyaySetu"},
                {"id": "cta_book", "title": "📅 Book Consultation"},
                {"id": "cta_notice", "title": "📨 Send Legal Notice"},
                {"id": "cta_visit", "title": "🌐 Visit NyaySetu"},
            ],
        }
    ]

    send_list_message(wa_id, intro, sections)


def handle_cta_selection(user: dict, cta_id: str):
    wa_id = user["user_id"]
    lang = user.get("language", "en")

    if cta_id == "cta_call":
        msg = (
            f"You can call NyaySetu on {NYAYSETU_PHONE}.\n"
            "Tap the number to dial from your phone."
        )
        send_text_message(wa_id, msg)
        # Optional: call button if your whatsapp_service supports it
        try:
            send_call_button(wa_id, "Tap below to call NyaySetu:", NYAYSETU_PHONE)
        except Exception as e:
            logging.warning(f"send_call_button failed: {e}")

    elif cta_id == "cta_book":
        start_booking_flow(user)

    elif cta_id == "cta_notice":
        if lang == "hi":
            msg = (
                "‘Send Legal Notice’ feature jaldi hi aa raha hai.\n"
                "Filhaal aap NyaySetu ko call karke notice ke bare me madad le sakte hai."
            )
        elif lang == "mr":
            msg = (
                "‘Send Legal Notice’ फीचर लवकरच उपलब्ध होईल.\n"
                f"आत्तासाठी तुम्ही NyaySetu ला {NYAYSETU_PHONE} या नंबरवर कॉल करू शकता."
            )
        else:
            msg = (
                "‘Send Legal Notice’ feature is coming soon.\n"
                f"For now, you can call NyaySetu on {NYAYSETU_PHONE} for help."
            )
        send_text_message(wa_id, msg)

    elif cta_id == "cta_visit":
        msg = f"You can visit NyaySetu at: {NYAYSETU_URL}"
        send_text_message(wa_id, msg)


# -----------------------------------------------------------------------------
# BOOKING FLOW
# -----------------------------------------------------------------------------

def generate_next_7_days():
    days = []
    today = datetime.now().date()
    for i in range(7):
        d = today + timedelta(days=i)
        title = d.strftime("%a, %d %b")  # Thu, 04 Dec
        days.append((d.isoformat(), title))
    return days


def start_booking_flow(user: dict):
    wa_id = user["user_id"]
    lang = user.get("language", "en")

    user["state"] = "booking_date"
    user["pending_date"] = None
    user["pending_time"] = None
    save_user(user)

    if lang == "hi":
        msg = "📅 Kripya aapko convenient date select kijiye:"
    elif lang == "mr":
        msg = "📅 कृपया तुमच्यासाठी सोयीची तारीख निवडा:"
    else:
        msg = "📅 Please select your convenient date:"

    rows = []
    for iso_date, title in generate_next_7_days():
        rows.append({"id": f"DATE_{iso_date}", "title": title})

    sections = [{"title": "Available Dates", "rows": rows}]
    send_list_message(wa_id, msg, sections)


def handle_date_selected(user: dict, date_id: str):
    wa_id = user["user_id"]
    lang = user.get("language", "en")

    iso_date = date_id.replace("DATE_", "", 1)
    user["pending_date"] = iso_date
    user["state"] = "booking_time"
    save_user(user)

    if lang == "hi":
        msg = f"Date selected: {iso_date}\nAb time slot choose kijiye:"
    elif lang == "mr":
        msg = f"तारीख निवडली: {iso_date}\nआता वेळ स्लॉट निवडा:"
    else:
        msg = f"Date selected: {iso_date}\nNow please choose your preferred time slot:"

    sections = [
        {
            "title": "Time Slot",
            "rows": [
                {"id": "TIME_MORNING", "title": "🌅 Morning"},
                {"id": "TIME_AFTERNOON", "title": "🌞 Afternoon"},
                {"id": "TIME_EVENING", "title": "🌙 Evening"},
            ],
        }
    ]
    send_list_message(wa_id, msg, sections)


def handle_time_selected(user: dict, time_id: str):
    wa_id = user["user_id"]
    lang = user.get("language", "en")

    slot_map = {
        "TIME_MORNING": "Morning",
        "TIME_AFTERNOON": "Afternoon",
        "TIME_EVENING": "Evening",
    }
    slot = slot_map.get(time_id, "Preferred time")

    date_str = user.get("pending_date") or "your chosen date"

    if lang == "hi":
        msg = (
            f"Thank you! Aapki consultation request note kar li gayi hai.\n"
            f"Date: {date_str}\nTime: {slot}\n\n"
            "NyaySetu team aapse confirm karne ke liye contact karegi."
        )
    elif lang == "mr":
        msg = (
            f"धन्यवाद! तुमची consultation विनंती नोंदवली गेली आहे.\n"
            f"दिनांक: {date_str}\nवेळ: {slot}\n\n"
            "NyaySetu टीम तुम्हाला पुष्टीसाठी संपर्क करेल."
        )
    else:
        msg = (
            "Thank you! Your consultation request has been noted.\n"
            f"Date: {date_str}\nTime: {slot}\n\n"
            "The NyaySetu team will contact you to confirm your slot."
        )

    send_text_message(wa_id, msg)

    # Reset booking state but keep language & free_count
    user["state"] = "chatting"
    user["pending_date"] = None
    user["pending_time"] = slot
    save_user(user)


# -----------------------------------------------------------------------------
# LEGAL REPLY FLOW
# -----------------------------------------------------------------------------

def handle_legal_question(user: dict, text_body: str):
    wa_id = user["user_id"]

    # Check free limit
    free_count = user.get("free_count", 0)
    if free_count >= FREE_ANSWER_LIMIT:
        logging.info(f"User {wa_id} reached free limit ({free_count}). Showing CTA.")
        send_free_limit_menu(user)
        user["state"] = "limit_reached"
        save_user(user)
        return

    # Typing + wait message
    try:
        # If your whatsapp_service has send_typing you can add it there.
        # Here we just send wait text.
        send_wait_message(user)
    except Exception as e:
        logging.warning(f"Wait message failed: {e}")

    # Detect language + category (for logging / future)
    try:
        lang_detected = detect_language(text_body)
        category = detect_category(text_body)
        logging.info(f"Lang={lang_detected}, Category={category}")
    except Exception as e:
        logging.error(f"Language/category detection failed: {e}")
        lang_detected = user.get("language", "en")
        category = "other"

    # Generate legal reply
    try:
        reply = generate_legal_reply(
            text_body,
            language=lang_detected,
            category=category,
            style="short",  # your Q1: A (short & simple)
        )
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        fallback = (
            "I'm unable to generate a proper legal explanation right now.\n"
            f"For urgent help, please call NyaySetu on {NYAYSETU_PHONE} "
            "or consult a qualified advocate."
        )
        send_text_message(wa_id, fallback)
        return

    # Send reply
    send_text_message(wa_id, reply)

    # Update free count & history
    user["free_count"] = free_count + 1
    user["state"] = "chatting"
    history = user.get("history", [])
    history.append({"q": text_body, "a": reply, "ts": datetime.utcnow().isoformat()})
    # keep last 30
    user["history"] = history[-30:]
    save_user(user)


# -----------------------------------------------------------------------------
# MESSAGE ROUTING
# -----------------------------------------------------------------------------

def is_greeting(text: str) -> bool:
    t = text.strip().lower()
    return t in {"hi", "hello", "hii", "hey", "helo", "hlo", "hy", "hello nyaysetu"}


def handle_text_message(user: dict, text_body: str):
    wa_id = user["user_id"]
    raw = text_body
    text_body = text_body.strip()
    logging.info(f"Parsed text_body='{text_body}', raw_text_body='{raw}'")

    # Restart flow on greeting
    if is_greeting(text_body):
        user["state"] = "awaiting_language"
        user["language"] = None
        user["free_count"] = 0
        user["history"] = []
        user["pending_date"] = None
        user["pending_time"] = None
        save_user(user)
        send_welcome_and_language_buttons(wa_id, user.get("case_id"))
        return

    state = user.get("state", "idle")

    # If we are waiting for language but user typed it instead of pressing button
    if state in {"idle", "awaiting_language"} and user.get("language") is None:
        lower = text_body.lower()
        if "english" in lower or "eng" == lower:
            user["language"] = "en"
        elif "hinglish" in lower or "hindi" in lower:
            user["language"] = "hi"
        elif "marathi" in lower or "मराठी" in lower:
            user["language"] = "mr"

        if user.get("language") is None:
            # Ask again properly with buttons
            send_welcome_and_language_buttons(wa_id, user.get("case_id"))
            user["state"] = "awaiting_language"
            save_user(user)
            return

        # Got language from text
        user["state"] = "awaiting_issue"
        save_user(user)
        send_ask_issue_message(user)
        return

    # Handle booking-related manual text (very basic)
    if state == "booking_date":
        # User typed a date instead of selecting; just ask to use menu
        msg = "Please select a date from the list above by tapping it."
        send_text_message(wa_id, msg)
        return

    if state == "booking_time":
        msg = "Please select a time slot from the list above by tapping it."
        send_text_message(wa_id, msg)
        return

    # Limit state: any further legal question → show menu again
    if state == "limit_reached":
        send_free_limit_menu(user)
        return

    # Normal legal Q&A
    if user.get("language") is None:
        # Safety: if somehow language lost
        user["state"] = "awaiting_language"
        save_user(user)
        send_welcome_and_language_buttons(wa_id, user.get("case_id"))
        return

    handle_legal_question(user, text_body)


def handle_button_reply(user: dict, button_id: str):
    wa_id = user["user_id"]
    logging.info(f"Button reply from {wa_id}: {button_id}")

    if button_id.startswith("lang_"):
        lang = button_id.replace("lang_", "", 1)
        if lang not in {"en", "hi", "mr"}:
            lang = "en"
        user["language"] = lang
        user["state"] = "awaiting_issue"
        save_user(user)
        send_ask_issue_message(user)
        return

    # Backward compatibility: 'book' id from older flows
    if button_id in {"book", "cta_book"}:
        handle_cta_selection(user, "cta_book")
        return


def handle_list_reply(user: dict, row_id: str):
    wa_id = user["user_id"]
    logging.info(f"List reply from {wa_id}: {row_id}")

    # Booking date
    if row_id.startswith("DATE_"):
        handle_date_selected(user, row_id)
        return

    # Booking time
    if row_id.startswith("TIME_"):
        handle_time_selected(user, row_id)
        return

    # CTA menu
    if row_id.startswith("cta_"):
        handle_cta_selection(user, row_id)
        return


# -----------------------------------------------------------------------------
# WEBHOOK ENDPOINTS
# -----------------------------------------------------------------------------

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logging.info("Webhook verified successfully.")
        return challenge, 200

    logging.warning("Webhook verification failed.")
    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"Incoming payload: {json.dumps(data, ensure_ascii=False)}")

    if not data or "entry" not in data:
        return "OK", 200

    try:
        entry = data["entry"][0]
        change = entry["changes"][0]
        value = change["value"]

        if "messages" not in value:
            # Status updates etc.
            return "OK", 200

        message = value["messages"][0]
        wa_id = message["from"]
        contacts = value.get("contacts", [])
        name = contacts[0]["profile"]["name"] if contacts else None

        user = get_or_create_user(wa_id, name)

        msg_type = message.get("type")

        if msg_type == "text":
            text_body = message["text"]["body"]
            handle_text_message(user, text_body)

        elif msg_type == "interactive":
            interactive = message["interactive"]
            itype = interactive.get("type")

            if itype == "button_reply":
                button_id = interactive["button_reply"]["id"]
                handle_button_reply(user, button_id)

            elif itype == "list_reply":
                row_id = interactive["list_reply"]["id"]
                handle_list_reply(user, row_id)

        # Ignore other message types silently
    except Exception as e:
        logging.exception(f"Error handling webhook: {e}")

    return "OK", 200


# -----------------------------------------------------------------------------
# ROOT & DEBUG
# -----------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return {"status": "NyaySetu Legal Bot Running", "version": "app11"}, 200


@app.route("/reset/<user_id>", methods=["GET"])
def reset_user(user_id):
    """Manual reset via URL (for testing only)."""
    user = get_user(user_id)
    if not user:
        return {"error": "user_not_found"}, 404
    user["state"] = "idle"
    user["language"] = None
    user["free_count"] = 0
    user["history"] = []
    user["pending_date"] = None
    user["pending_time"] = None
    save_user(user)
    return {"reset": "ok"}, 200


# -----------------------------------------------------------------------------
# START SERVER (for local / Render)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 NyaySetu Legal Bot Server started on port {port}")
    app.run(host="0.0.0.0", port=port)
