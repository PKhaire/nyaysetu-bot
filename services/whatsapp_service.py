import os
import httpx
import logging
from config import WHATSAPP_API_URL, WHATSAPP_TOKEN

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

def send_request(payload):
    try:
        logging.info(f"WHATSAPP REQUEST: {payload}")
        response = httpx.post(WHATSAPP_API_URL, json=payload, headers=HEADERS)
        logging.info(f"WHATSAPP RESPONSE: {response.text}")
        return response
    except Exception as e:
        logging.error(f"WhatsApp API ERROR: {str(e)}")


def send_text(to, message):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    return send_request(payload)


def send_typing_on(to):
    logging.info(f"SIMULATED_TYPING_ON for {to}")


def send_typing_off(to):
    logging.info(f"SIMULATED_TYPING_OFF for {to}")


def send_buttons(to, text, buttons):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {"buttons": buttons}
        }
    }
    return send_request(payload)


def send_list_picker(to, header, body, rows, section_title="Options"):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "action": {
                "button": "Select",
                "sections": [
                    {
                        "title": section_title,
                        "rows": rows,  # ← rows is a flat list of {id,title,description}
                    }
                ],
            },
        },
    }
    return _send(payload)

