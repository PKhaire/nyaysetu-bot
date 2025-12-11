# services/whatsapp_service.py
import os
import logging
import httpx
from config import WHATSAPP_TOKEN, WHATSAPP_API_URL

logger = logging.getLogger("services.whatsapp_service")

HEADERS = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"} if WHATSAPP_TOKEN else {}

def _send(payload: dict):
    if not WHATSAPP_API_URL or not WHATSAPP_TOKEN:
        logger.warning("WHATSAPP_API_URL or WHATSAPP_TOKEN not configured. Skipping send.")
        return {"error": "no_whatsapp_config"}
    payload = payload.copy()
    with httpx.Client(timeout=10) as client:
        resp = client.post(WHATSAPP_API_URL, headers=HEADERS, json=payload)
    logger.info("WHATSAPP REQUEST: %s", payload)
    try:
        j = resp.json()
    except Exception:
        j = {"status": resp.status_code, "text": resp.text}
    logger.info("WHATSAPP RESPONSE: %s", j)
    return j

def send_text(wa_id: str, body: str):
    payload = {"messaging_product": "whatsapp", "to": wa_id, "type": "text", "text": {"body": body}}
    return _send(payload)

def send_buttons(wa_id: str, body: str, buttons: list):
    # buttons: list of {"id": "xxx", "title":"Title"}
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": [{"type":"reply","reply":{"id":b["id"],"title": b["title"]}} for b in buttons]}
        }
    }
    return _send(payload)

def send_typing_on(wa_id: str):
    # We simulate typing — WhatsApp API doesn't support typing_state, so this is a no-op placeholder.
    logger.info("SIMULATED_TYPING_ON for %s", wa_id)
    return {"ok": True}

def send_typing_off(wa_id: str):
    logger.info("SIMULATED_TYPING_OFF for %s", wa_id)
    return {"ok": True}

def send_list_picker(wa_id: str, header: str, body: str, rows: list, section_title: str = "Options"):
    """
    rows: list of dicts with keys: id, title, description
    Builds a WhatsApp interactive list payload.
    """
    sections = [{"title": section_title, "rows": [{"id": r["id"], "title": r["title"], "description": r.get("description", "")} for r in rows]}]
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "action": {"button": "Select", "sections": sections}
        }
    }
    return _send(payload)
