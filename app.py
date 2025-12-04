import os
import json
import time
import logging
from flask import Flask, request
from db import get_user, create_user, update_user
from whatsapp_service import send_text_message, send_button_message, send_list_message, send_call_button
from openai_service import get_legal_answer

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

FREE_LIMIT = 4

# --- GLOBAL HELPERS ----------------------------------------------------------

def normalize_msg(msg: str) -> str:
    """Normalize text input to avoid false triggers."""
    if not msg:
        return ""
    msg = msg.strip().lower()
    replacements = {
        "hii": "hi", "hiii": "hi", "hiiii": "hi",
        "hello": "hi", "helo": "hi", "hey": "hi",
        "hye": "hi", "hy": "hi",
    }
    return replacements.get(msg, msg)

def is_greeting(msg: str) -> bool:
    """Returns True if user is starting conversation."""
    greetings = ["hi", "start", "hello", "help", "restart", "menu"]
    return normalize_msg(msg) in greetings

def send_typing_indicator(user_id: str):
    """Simulate typing effect on WhatsApp."""
    try:
        send_text_message(user_id, "⌛ typing…")
        time.sleep(1.5)
    except Exception as e:
        logging.error(f"Typing indicator failed: {e}")

def send_wait_message(user_id: str, lang: str):
    """Multilingual wait message."""
    msg_map = {
        "en": "🧠 Gathering the correct legal information…\nPlease wait a moment.",
        "hi": "🧠 Sahi kanooni jaankari dhoondi ja rahi hai…\nKripya pray wait karein.",
        "mr": "🧠 योग्य कायदेशीर माहिती घेत आहोत…\nकृपया थांबा.",
    }
    send_text_message(user_id, msg_map.get(lang, msg_map["en"]))

# --- UPDATE FREE LIMIT STATE -------------------------------------------------

def increment_counter(user):
    """Increase the free responses count."""
    user["free_count"] = (user.get("free_count") or 0) + 1
    update_user(user)
    return user["free_count"]

def is_free_limit_reached(user):
    """Check if user has crossed limit."""
    return (user.get("free_count") or 0) >= FREE_LIMIT
# --- LANGUAGE & UI CONFIG ----------------------------------------------------

LANGUAGE_BUTTONS = [
    {"id": "lang_en", "title": "English"},
    {"id": "lang_hi", "title": "Hinglish"},
    {"id": "lang_mr", "title": "Marathi"},
]

LIMIT_ACTION_BUTTONS = [
    {"id": "action_call", "title": "📞 Call NyaySetu"},
    {"id": "action_book", "title": "📅 Book Consultation"},
    {"id": "action_notice", "title": "📄 Send Legal Notice"},
    {"id": "action_visit", "title": "🌐 Visit NyaySetu"},
]

WELCOME_TEMPLATES = {
    "en": (
        "👋 Welcome to NyaySetu — The Bridge To Justice.\n"
        "Your Case ID: {case_id}\n\n"
        "Before we begin, please choose your preferred language 👇"
    ),
    "hi": (
        "👋 NyaySetu mein swagat hai — The Bridge To Justice.\n"
        "Aapka Case ID: {case_id}\n\n"
        "Shuru karne se pehle, kripya apni pasand ki bhasha chune 👇"
    ),
    "mr": (
        "👋 न्यायसेतू मध्ये स्वागत — The Bridge To Justice.\n"
        "तुमचा केस आयडी: {case_id}\n\n"
        "सुरुवात करण्यापूर्वी, कृपया तुमची पसंतीची भाषा निवडा 👇"
    ),
}

FREE_LIMIT_TEXT = {
    "en": (
        "🛑 You have used your free legal answers.\n\n"
        "To continue receiving personalised guidance, please choose an option below."
    ),
    "hi": (
        "🛑 Aapke free legal jawab complete ho chuke hain.\n\n"
        "Personalised legal guidance ke liye, kripya niche diye gaye options me se koi ek chunen."
    ),
    "mr": (
        "🛑 तुमचे मोफत कायदेशीर उत्तर पूर्ण झाले आहेत.\n\n"
        "पुढील वैयक्तिक मार्गदर्शनासाठी खालीलपैकी एक पर्याय निवडा."
    ),
}

ISSUE_PROMPT = {
    "en": "Please type your legal issue in English.",
    "hi": "Ab apna legal issue Hinglish (Hindi + English mix) me type karein.",
    "mr": "कृपया तुमचा कायदेशीर प्रश्न मराठीत लिहा.",
}

def get_lang(user):
    """Return short language code from user object."""
    lang = (user.get("language") or "en").lower()
    if lang.startswith("mr"):
        return "mr"
    if lang.startswith("hi") or "hinglish" in lang:
        return "hi"
    return "en"

def ask_language_menu(user):
    """Send welcome + language selection buttons."""
    lang = "en"  # welcome message base language (English)
    welcome_text = WELCOME_TEMPLATES[lang].format(case_id=user["case_id"])
    send_text_message(user["user_id"], welcome_text)

    # Language buttons: plain text (no flags)
    send_button_message(
        user["user_id"],
        "Choose the language you are most comfortable with 👇",
        LANGUAGE_BUTTONS,
    )

def send_free_limit_menu(user):
    """Send 4-option menu when free limit reached."""
    lang = get_lang(user)
    body = FREE_LIMIT_TEXT.get(lang, FREE_LIMIT_TEXT["en"])
    send_button_message(user["user_id"], body, LIMIT_ACTION_BUTTONS)

def set_language_from_button(user, button_id: str):
    """Update user language based on button reply id."""
    mapping = {
        "lang_en": "en",
        "lang_hi": "hi",
        "lang_mr": "mr",
    }
    lang = mapping.get(button_id, "en")
    user["language"] = lang
    user["state"] = "await_issue"
    update_user(user)

    msg = ISSUE_PROMPT.get(lang, ISSUE_PROMPT["en"])
    send_text_message(user["user_id"], msg)

# --- BOOKING RELATED (simple stub: we keep logic in this file) --------------

def start_booking_flow(user):
    """Entry point: ask user to choose date via list message."""
    user["state"] = "booking_date"
    update_user(user)

    # we send a static list for now – dates handled as simple options
    send_list_message(
        user["user_id"],
        "📅 कृपया दिनांक निवडा / Select your convenient date:",
        "Select Date",
        sections=[{
            "title": "Next 7 days",
            "rows": [
                # ids are generic; real mapping can be handled in date handler
                {"id": "DATE_TODAY", "title": "Today"},
                {"id": "DATE_TOMORROW", "title": "Tomorrow"},
                {"id": "DATE_DAY3", "title": "Day 3"},
                {"id": "DATE_DAY4", "title": "Day 4"},
                {"id": "DATE_DAY5", "title": "Day 5"},
                {"id": "DATE_DAY6", "title": "Day 6"},
                {"id": "DATE_DAY7", "title": "Day 7"},
            ]
        }],
    )

def handle_booking_interactive(user, payload_id: str):
    """
    Very simple booking flow:
    - First selection: DATE_*
    - Second selection: TIME_* (buttons)
    """
    state = user.get("state")

    # user selected a date
    if state == "booking_date" and payload_id.startswith("DATE_"):
        user["state"] = "booking_time"
        user["booking_date"] = payload_id
        update_user(user)

        send_button_message(
            user["user_id"],
            "📅 Date selected.\n\nNow choose a time slot:",
            [
                {"id": "TIME_morning", "title": "Morning (10 AM – 1 PM)"},
                {"id": "TIME_afternoon", "title": "Afternoon (1 PM – 4 PM)"},
                {"id": "TIME_evening", "title": "Evening (4 PM – 7 PM)"},
            ],
        )
        return True

    # user selected a time slot
    if state == "booking_time" and payload_id.startswith("TIME_"):
        user["state"] = "idle"
        user["booking_time"] = payload_id
        update_user(user)

        # For now we just confirm booking textually (no Razorpay here;
        # that part is already in your other app, we keep this light).
        slot_map = {
            "TIME_morning": "Morning (10 AM – 1 PM)",
            "TIME_afternoon": "Afternoon (1 PM – 4 PM)",
            "TIME_evening": "Evening (4 PM – 7 PM)",
        }
        slot_label = slot_map.get(payload_id, "your selected slot")

        lang = get_lang(user)
        if lang == "mr":
            msg = (
                f"📝 तुमचे सत्र *{slot_label}* या वेळेसाठी नोंद झाले आहे.\n"
                "आमचा प्रतिनिधी लवकरच तुम्हाला संपर्क करेल."
            )
        elif lang == "hi":
            msg = (
                f"📝 Aapka session *{slot_label}* ke liye note ho gaya hai.\n"
                "Hamari team ka representative aapse jald hi sampark karega."
            )
        else:
            msg = (
                f"📝 Your consultation request is noted for *{slot_label}*.\n"
                "Our team will contact you shortly to confirm the slot."
            )

        send_text_message(user["user_id"], msg)
        return True

    return False
# --- WEBHOOK CORE ------------------------------------------------------------

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"Incoming payload: {data}")

    # Extract message or button/list payload
    try:
        entry = data["entry"][0]["changes"][0]["value"]
    except Exception:
        return "OK", 200

    user_id = None
    message = None
    button_payload = None
    list_payload = None

    if "messages" in entry:
        msg = entry["messages"][0]
        user_id = msg.get("from")

        # interactive button
        if msg.get("type") == "interactive" and "button_reply" in msg["interactive"]:
            button_payload = msg["interactive"]["button_reply"]["id"]

        # interactive list
        if msg.get("type") == "interactive" and "list_reply" in msg["interactive"]:
            list_payload = msg["interactive"]["list_reply"]["id"]

        # normal text
        if msg.get("type") == "text":
            message = msg["text"]["body"]

    else:
        return "OK", 200

    if not user_id:
        return "OK", 200

    # Fetch / create user
    user = get_user(user_id)
    if user is None:
        user = create_user(user_id)
        logging.info(f"New user registered: {user_id} → {user['case_id']}")
        ask_language_menu(user)
        return "OK", 200

    # ----------------------------------------------------------------------
    # Handle language selection buttons
    # ----------------------------------------------------------------------
    if button_payload and button_payload.startswith("lang_"):
        set_language_from_button(user, button_payload)
        return "OK", 200

    # ----------------------------------------------------------------------
    # Handle free-limit menu actions (after limit reached)
    # ----------------------------------------------------------------------
    if button_payload and button_payload.startswith("action_"):
        if button_payload == "action_call":
            send_call_button(user["user_id"], "📞 Tap to call NyaySetu now", "+917020030080")
        elif button_payload == "action_book":
            start_booking_flow(user)
        elif button_payload == "action_notice":
            send_text_message(user["user_id"], "📄 *Coming Soon*\nLegal notice service will be activated shortly.")
        elif button_payload == "action_visit":
            send_text_message(user["user_id"], "🌐 Visit us on https://nyaysetu.in/")
        return "OK", 200

    # ----------------------------------------------------------------------
    # Booking list selection → choose time
    # ----------------------------------------------------------------------
    if list_payload:
        if handle_booking_interactive(user, list_payload):
            return "OK", 200

    # ----------------------------------------------------------------------
    # Booking button selection → confirm
    # ----------------------------------------------------------------------
    if button_payload and button_payload.startswith("TIME_"):
        if handle_booking_interactive(user, button_payload):
            return "OK", 200

    # ----------------------------------------------------------------------
    # If language not selected yet → always ask language
    # ----------------------------------------------------------------------
    if not user.get("language"):
        ask_language_menu(user)
        return "OK", 200

    # ----------------------------------------------------------------------
    # If booking session active & user sends text instead of interactive input
    # ----------------------------------------------------------------------
    if user.get("state") in ["booking_date", "booking_time"]:
        send_text_message(user["user_id"], "⚠ Please select from the on-screen options to continue booking.")
        return "OK", 200

    # ----------------------------------------------------------------------
    # Normal conversation mode
    # ----------------------------------------------------------------------
    msg = normalize_msg(message or "")

    # Restart greeting
    if is_greeting(msg):
        user["state"] = "idle"
        update_user(user)
        ask_language_menu(user)
        return "OK", 200

    # If free limit reached → show plans screen
    if is_free_limit_reached(user):
        send_free_limit_menu(user)
        return "OK", 200

    # ----------------------------------------------------------------------
    # LEGAL ANSWER FLOW (call GPT)
    # ----------------------------------------------------------------------
    lang = get_lang(user)
    send_wait_message(user["user_id"], lang)
    send_typing_indicator(user["user_id"])

    try:
        answer = get_legal_answer(message, lang)
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        send_text_message(user["user_id"], "⚠ There was an issue fetching the legal info. Please try again.")
        return "OK", 200

    send_text_message(user["user_id"], answer)
    increment_counter(user)

    # After sending answer, if limit reached on this exact reply → show menu
    if is_free_limit_reached(user):
        time.sleep(1)
        send_free_limit_menu(user)

    return "OK", 200
# --- SAFETY: FALLBACKS ------------------------------------------------------

@app.errorhandler(Exception)
def handle_exception(e):
    logging.error(f"Server Error: {e}")
    return "OK", 200


# --- ROOT ROUTES FOR RENDER HEALTH CHECK ------------------------------------

@app.route("/", methods=["GET"])
def home():
    return {"status": "NyaySetu Legal Bot Running", "version": "app10"}, 200


# --- DEBUG TRIGGER (Optional) -----------------------------------------------

@app.route("/reset/<user_id>", methods=["GET"])
def reset_user(user_id):
    """Manual reset via URL only for testing."""
    user = get_user(user_id)
    if not user:
        return {"error": "user_not_found"}, 404
    user["state"] = "idle"
    user["language"] = None
    user["free_count"] = 0
    update_user(user)
    return {"reset": "ok"}, 200
# --- START SERVER -----------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))   # Render default dynamic port
    print(f"🚀 NyaySetu Legal Bot Server started on port {port}")
    app.run(host="0.0.0.0", port=port)


