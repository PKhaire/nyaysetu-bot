import os
import httpx
import logging

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

logger = logging.getLogger(__name__)


# ----------------------------------------------------
# Internal unified sender
# ----------------------------------------------------
def _send(data: dict):
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    logger.info(f"WHATSAPP REQUEST: {data}")

    try:
        resp = httpx.post(WHATSAPP_API_URL, json=data, headers=headers, timeout=20)
        logger.info(f"WHATSAPP RESPONSE: {resp.text}")
        return resp
    except Exception as e:
        logger.error(f"WHATSAPP SEND ERROR: {e}", exc_info=True)
        return None


# ----------------------------------------------------
# Text message
# ----------------------------------------------------
def send_text(to, message):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": message
        }
    }
    return _send(payload)


# ----------------------------------------------------
# Buttons
# ----------------------------------------------------
def send_buttons(to, text, buttons):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                    for btn in buttons
                ]
            },
        },
    }
    return _send(payload)


# ----------------------------------------------------
# List Picker (Date & Slot Selection)
# ----------------------------------------------------
def send_list_picker(to, header, body, rows, section_title="Options"):
    """
    rows must be list of:
    [ {"id": "date_2025-12-09", "title": "09 Dec (Tue)"} , ... ]
    """

    formatted_rows = []
    for r in rows:
        formatted_rows.append({
            "id": r["id"],
            "title": r["title"],
            "description": r.get("description", "")[:70]  # optional
        })

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
                        "rows": formatted_rows
                    }
                ]
            }
        }
    }
    return _send(payload)


# ----------------------------------------------------
# Simulated typing UX (not real WhatsApp typing)
# ----------------------------------------------------
def send_typing_on(to):
    logger.info(f"SIMULATED_TYPING_ON for {to}")


def send_typing_off(to):
    logger.info(f"SIMULATED_TYPING_OFF for {to}")
