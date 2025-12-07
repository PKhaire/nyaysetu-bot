import requests
import logging
import json
from config import WHATSAPP_TOKEN, WHATSAPP_PHONE_ID

API_URL = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}


# =======================================================
# CORE SEND FUNCTION
# =======================================================
def send_whatsapp(payload):
    try:
        logging.info(f"WHATSAPP REQUEST: {payload}")
        response = requests.post(API_URL, headers=HEADERS, json=payload)
        logging.info(f"WHATSAPP RESPONSE: {response.text}")
    except Exception as e:
        logging.error(f"WHATSAPP SEND ERROR: {e}")


# =======================================================
# BASIC MESSAGE TYPES
# =======================================================
def send_text(to, text):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    send_whatsapp(payload)


def send_image(to, image_url, caption=None):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {"link": image_url}
    }
    if caption:
        payload["image"]["caption"] = caption
    send_whatsapp(payload)


# =======================================================
# BUTTONS (for menu selections)
# =======================================================
def send_buttons(to, body_text, buttons):
    """
    buttons = [
        ("btn_id_1", "Button Text 1"),
        ("btn_id_2", "Button Text 2"),
    ]
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
                    {"type": "reply", "reply": {"id": b_id, "title": title}}
                    for b_id, title in buttons
                ]
            }
        }
    }
    send_whatsapp(payload)


# =======================================================
# LIST MENU (for many options)
# =======================================================
def send_list(to, header, body, sections):
    """
    sections format:
    [
        {
            "title": "Section A",
            "rows": [
                {"id": "a1", "title": "Option 1"},
                {"id": "a2", "title": "Option 2"}
            ]
        }
    ]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "action": {"sections": sections}
        }
    }
    send_whatsapp(payload)


# =======================================================
# TYPING INDICATOR (SIMULATED ONLY — avoids WhatsApp API error)
# =======================================================
def send_typing_on(to):
    logging.info(f"SIMULATED_TYPING_ON for {to}")  # no API call — safe


def send_typing_off(to):
    logging.info(f"SIMULATED_TYPING_OFF for {to}")  # no API call — safe


# =======================================================
# PAYMENT BUTTONS (if needed later)
# =======================================================
def send_payment_button(to, amount, pay_url):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"Consultation Fee: ₹{amount}"},
            "action": {
                "buttons": [
                    {"type": "url", "url": pay_url, "title": "Pay Now"}
                ]
            }
        }
    }
    send_whatsapp(payload)


# =======================================================
# RATING BUTTONS (after call completion)
# =======================================================
def send_rating_buttons(to):
    buttons = [
        ("rating_5", "⭐⭐⭐⭐⭐"),
        ("rating_4", "⭐⭐⭐⭐"),
        ("rating_3", "⭐⭐⭐"),
        ("rating_2", "⭐⭐"),
        ("rating_1", "⭐"),
    ]
    send_buttons(to, "How was your consultation experience?", buttons)

# =======================================================
# BACKWARD COMPATIBILITY — required by app.py
# =======================================================
def send_list_picker(to, header, body, sections):
    """
    Wrapper alias kept only because app.py imports send_list_picker.
    Internally uses send_list().
    """
    return send_list(to, header, body, sections)

