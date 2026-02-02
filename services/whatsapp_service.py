# services/whatsapp_service.py
import os
import logging
import httpx

from config import WHATSAPP_TOKEN, WHATSAPP_API_URL, BOOKING_PRICE
from db import SessionLocal
from models import Booking, User
from utils import format_date_readable
from services.booking_service import SLOT_MAP
from utils.i18n import t

logger = logging.getLogger("services.whatsapp_service")

HEADERS = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"} if WHATSAPP_TOKEN else {}

# =================================================
# CORE SEND
# =================================================
def _send(payload: dict):
    if not WHATSAPP_API_URL or not WHATSAPP_TOKEN:
        logger.warning(
            "WHATSAPP_API_URL or WHATSAPP_TOKEN not configured. Skipping send."
        )
        return {"error": "no_whatsapp_config"}

    payload = payload.copy()

    with httpx.Client(timeout=10) as client:
        resp = client.post(
            WHATSAPP_API_URL,
            headers=HEADERS,
            json=payload
        )

    logger.info("WHATSAPP REQUEST: %s", payload)

    try:
        j = resp.json()
    except Exception:
        j = {"status": resp.status_code, "text": resp.text}

    logger.info("WHATSAPP RESPONSE: %s", j)
    return j


# =================================================
# TEXT & INTERACTIVE
# =================================================
def send_text(wa_id: str, body: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": {"body": body},
    }
    return _send(payload)


def send_buttons(wa_id: str, body: str, buttons: list):
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": b["id"],
                            "title": b["title"]
                        },
                    }
                    for b in buttons
                ]
            },
        },
    }
    return _send(payload)


def send_typing_on(wa_id: str):
    logger.info("SIMULATED_TYPING_ON for %s", wa_id)
    return {"ok": True}


def send_typing_off(wa_id: str):
    logger.info("SIMULATED_TYPING_OFF for %s", wa_id)
    return {"ok": True}


def send_list_picker(
    wa_id: str,
    header: str,
    body: str,
    rows: list,
    section_title: str = "Options",
):
    sections = [
        {
            "title": section_title,
            "rows": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "description": r.get("description", ""),
                }
                for r in rows
            ],
        }
    ]

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "action": {"button": "Select", "sections": sections},
        },
    }
    return _send(payload)


# =================================================
# PAYMENT SUCCESS (FINAL, INDUSTRY-GRADE)
# =================================================
def send_payment_success_message(booking):
    """
    Sends language-aware, audit-safe payment success message.
    """

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.whatsapp_id == booking.whatsapp_id)
            .first()
        )

        if not user:
            logger.error(
                "Payment success failed: user not found | booking_id=%s",
                booking.id,
            )
            return

        message = t(
            user,
            "payment_success",
            date=format_date_readable(booking.date),
            slot=SLOT_MAP.get(booking.slot_code, "N/A"),
            amount=BOOKING_PRICE,
        )

        send_text(booking.whatsapp_id, message)

    finally:
        db.close()


# =================================================
# DOCUMENT / RECEIPT
# =================================================
def send_document(wa_id: str, file_path: str, caption: str = ""):
    if not WHATSAPP_API_URL or not WHATSAPP_TOKEN:
        logger.warning(
            "WHATSAPP_API_URL or WHATSAPP_TOKEN not configured. Skipping document send."
        )
        return {"error": "no_whatsapp_config"}

    if not os.path.exists(file_path):
        logger.error("PDF file not found: %s", file_path)
        return {"error": "file_not_found"}

    # -----------------------------------
    # 1️⃣ Upload media
    # -----------------------------------
    media_url = WHATSAPP_API_URL.replace("/messages", "/media")

    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    with open(file_path, "rb") as f:
        files = {
            "file": (
                os.path.basename(file_path),
                f,
                "application/pdf",
            )
        }
        data = {"messaging_product": "whatsapp"}

        with httpx.Client(timeout=20) as client:
            upload_resp = client.post(
                media_url,
                headers=headers,
                files=files,
                data=data,
            )

    upload_resp.raise_for_status()
    media_id = upload_resp.json().get("id")

    if not media_id:
        logger.error("Failed to upload media: %s", upload_resp.text)
        return {"error": "media_upload_failed"}

    # -----------------------------------
    # 2️⃣ Send document
    # -----------------------------------
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "document",
        "document": {
            "id": media_id,
            "caption": caption or "",
        },
    }

    return _send(payload)


def send_payment_receipt_pdf(wa_id: str, pdf_path: str):
    """
    Sends receipt PDF and marks receipt_sent in DB.
    """

    send_document(
        wa_id=wa_id,
        file_path=pdf_path,
        caption="Payment receipt for your NyaySetu consultation.",
    )

    db = SessionLocal()
    try:
        booking = (
            db.query(Booking)
            .filter(Booking.whatsapp_id == wa_id)
            .order_by(Booking.id.desc())
            .first()
        )

        if booking:
            booking.receipt_sent = True
            db.commit()

    finally:
        db.close()
