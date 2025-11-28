# services/whatsapp_service.py
import requests
import logging
from config import WHATSAPP_PHONE_ID, WHATSAPP_ACCESS_TOKEN

def _headers():
    return {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"}

def whatsapp_url():
    return f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"

def send_text(to, text):
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        r = requests.post(whatsapp_url(), json=payload, headers=_headers(), timeout=10)
        logging.info("WhatsApp send_text %s %s", r.status_code, r.text)
        return r
    except Exception as e:
        logging.exception("WhatsApp send_text error")
        return None

def send_typing_on(to):
    payload = {"messaging_product": "whatsapp", "to": to, "type": "typing_on"}
    try:
        requests.post(whatsapp_url(), json=payload, headers=_headers(), timeout=6)
    except Exception:
        pass

def send_typing_off(to):
    payload = {"messaging_product": "whatsapp", "to": to, "type": "typing_off"}
    try:
        requests.post(whatsapp_url(), json=payload, headers=_headers(), timeout=6)
    except Exception:
        pass

def send_buttons(to, body, replies):
    """
    replies: list of {"id": "value", "title": "Label"}
    This function converts to WhatsApp 'reply' buttons format.
    """
    buttons = [{"type": "reply", "reply": r} for r in replies]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {"type": "button", "body": {"text": body}, "action": {"buttons": buttons}}
    }
    try:
        r = requests.post(whatsapp_url(), json=payload, headers=_headers(), timeout=10)
        logging.info("WhatsApp send_buttons %s %s", r.status_code, r.text)
        return r
    except Exception:
        logging.exception("WhatsApp send_buttons error")
        return None
