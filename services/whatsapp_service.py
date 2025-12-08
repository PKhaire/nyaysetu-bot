import os
import logging
import requests
from config import WHATSAPP_API_URL, WHATSAPP_TOKEN

logging.basicConfig(level=logging.INFO)

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}


def _send(payload):
    """Internal function to send WhatsApp API requests."""
    try:
        logging.info("WHATSAPP REQUEST: %s", payload)
        res = requests.post(WHATSAPP_API_URL, headers=HEADERS, json=payload)
        logging.info("WHATSAPP RESPONSE: %s", res.text)
        return res.json()
    except Exception as e:
        logging.error("WHATSAPP SEND ERROR: %s", str(e))


# ---------------- TEXT ----------------
def send_text(to, msg):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": msg}
    }
    return _send(payload)


# ---------------- BUTTONS ----------------
def send_buttons(to, body_text, buttons):
    """
    buttons = [
        {"id": "book", "title": "Book Consultation"},
        {"id": "help", "title": "Talk to Support"},
    ]
    """
    formatted_buttons = [
        {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
        for btn in buttons
    ]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": formatted_buttons}
        }
    }
    return _send(payload)


# ---------------- LIST PICKER (Calendar) ----------------
def send_list_picker(to, header_text, body_text, rows):
    """
    rows must be list of:
        [{"id": "date_07", "title": "Dec 07 (Sun)"}]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header_text},
            "body": {"text": body_text},
            "action": {
                "button": "Select",
                "sections": [
                    {
                        "title": "Options",
                        "rows": rows
                    }
                ]
            }
        }
    }
    return _send(payload)


# ---------------- TYPING ----------------
def send_typing_on(to):
    payload = {"messaging_product": "whatsapp", "to": to, "type": "typing_on"}
    return _send(payload)


def send_typing_off(to):
    payload = {"messaging_product": "whatsapp", "to": to, "type": "typing_off"}
    return _send(payload)
