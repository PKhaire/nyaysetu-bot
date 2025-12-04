import requests
import os
import logging

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

API_URL = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"


def _post_to_whatsapp(payload):
    """
    Internal function to send HTTPS request to WhatsApp Cloud API.
    """
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(API_URL, json=payload, headers=headers, timeout=10)
        logging.info(f"WHATSAPP REQUEST: {payload}")
        logging.info(f"WHATSAPP RESPONSE: {r.text}")
        return r
    except Exception as e:
        logging.error(f"WHATSAPP ERROR: {e}")
        return None


# -----------------------------------------------------------------------
#  PUBLIC FUNCTIONS USED BY app.py
# -----------------------------------------------------------------------

def send_text(to, text):
    """
    Send a normal WhatsApp text message
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    return _post_to_whatsapp(payload)


def send_buttons(to, message, buttons):
    """
    Send buttons message with multiple quick-reply options.
    Format for buttons:
    [ { "id": "btn1", "title": "English" }, ... ]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": message},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons
                ]
            }
        }
    }
    return _post_to_whatsapp(payload)


def send_typing_on(to):
    """
    Show 'typing...' indicator
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "sender_action",
        "sender_action": "typing_on"
    }
    return _post_to_whatsapp(payload)


def send_typing_off(to):
    """
    Hide 'typing...' indicator
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "sender_action",
        "sender_action": "typing_off"
    }
    return _post_to_whatsapp(payload)
