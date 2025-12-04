import os
import logging
import requests

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

API_URL = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}


def call_whatsapp_api(payload):
    logging.info(f"WHATSAPP REQUEST: {payload}")
    resp = requests.post(API_URL, headers=HEADERS, json=payload)
    try:
        logging.info(f"WHATSAPP RESPONSE: {resp.text}")
    except Exception:
        pass
    return resp


def send_text(to, message):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    return call_whatsapp_api(payload)


def send_buttons(to, text, buttons):
    """
    buttons = [ { "id": "btn1", "title": "English" }, ... ]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons
                ]
            }
        }
    }
    return call_whatsapp_api(payload)


def send_typing_on(to):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "action",
        "action": {"typing": "on"}
    }
    return call_whatsapp_api(payload)


def send_typing_off(to):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "action",
        "action": {"typing": "off"}
    }
    return call_whatsapp_api(payload)
