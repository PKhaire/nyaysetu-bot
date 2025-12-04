import os
import httpx
import logging

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

API_URL = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
}


def _send(payload):
    try:
        response = httpx.post(API_URL, json=payload, headers=HEADERS, timeout=15)
        logging.info(f"WA Response {response.status_code}: {response.text}")
    except Exception as e:
        logging.error(f"WA SEND ERROR: {e}")


def send_text_message(to, message):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    _send(payload)


def send_typing(to, seconds=2):
    """Shows typing indicator on WhatsApp."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "typing_on"
    }
    _send(payload)


def send_button_message(to, message, buttons):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": message},
            "action": {"buttons": buttons},
        },
    }
    _send(payload)


def send_list_message(to, message, sections):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": message},
            "action": {
                "button": "Select",
                "sections": sections,
            },
        },
    }
    _send(payload)


def send_call_button(to, message, phone_number):
    buttons = [
        {
            "type": "phone_number",
            "phone_number": phone_number,
            "text": "📞 Call NyaySetu"
        }
    ]
    send_button_message(to, message, buttons)
