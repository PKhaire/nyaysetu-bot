import requests
import logging
from config import WHATSAPP_TOKEN

API_URL = "https://graph.facebook.com/v20.0/me/messages"

headers = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}


def send_whatsapp(data):
    try:
        r = requests.post(API_URL, json=data, headers=headers, timeout=10)
        logging.info(f"WHATSAPP REQUEST: {data}")
        logging.info(f"WHATSAPP RESPONSE: {r.text}")
    except Exception as e:
        logging.error(f"WhatsApp Error: {e}")


def send_text(to, text):
    send_whatsapp({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    })


def send_buttons(to, body, buttons):
    send_whatsapp({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": btn[1], "title": btn[0]}}
                    for btn in buttons
                ]
            }
        }
    })


def send_list_picker(to, title, body, rows):
    send_whatsapp({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": title},
            "body": {"text": body},
            "action": {"sections": [{"title": "Select", "rows": rows}]}
        }
    })


def send_typing_on(to):
    send_whatsapp({"messaging_product": "whatsapp", "to": to, "type": "typing_on"})


def send_typing_off(to):
    send_whatsapp({"messaging_product": "whatsapp", "to": to, "type": "typing_off"})
