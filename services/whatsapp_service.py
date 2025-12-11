# services/whatsapp_service.py
import os
import logging
import requests
import json
from config import WHATSAPP_API_URL, WHATSAPP_TOKEN, TYPING_DELAY_SECONDS

logger = logging.getLogger("services.whatsapp_service")

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

def _send(payload):
    url = WHATSAPP_API_URL
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        logger.info("WHATSAPP REQUEST: %s", json.dumps(payload))
        logger.info("WhatsApp API response: %s %s", resp.status_code, resp.text)
        return resp.json()
    except Exception as e:
        logger.exception("Failed sending whatsapp message: %s", e)
        return {}

def send_text(to, body):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body}
    }
    return _send(payload)

def send_buttons(to, body, buttons):
    # buttons is list of dicts {id,title}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": [{"type":"reply","reply":{"id":b["id"],"title":b["title"]}} for b in buttons]}
        }
    }
    return _send(payload)

def send_list_picker(to, header, body, rows, section_title="Options"):
    # rows: list of dict {id, title, description}
    # WhatsApp list requires: interactive->action->button + sections -> rows
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
                        "rows": [
                            {"id": r["id"], "title": r["title"], "description": r.get("description", "")}
                            for r in rows
                        ]
                    }
                ]
            }
        }
    }
    return _send(payload)

def send_typing_on(to):
    # Not all accounts support typing indicators via API, but we leave a stub for logging
    logger.info("SIMULATED_TYPING_ON for %s", to)

def send_typing_off(to):
    logger.info("SIMULATED_TYPING_OFF for %s", to)
