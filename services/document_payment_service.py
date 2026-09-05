"""Razorpay adapter dedicated to Document Studio payment links."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import (
    PAYMENT_LINK_TTL_MINUTES,
    RAZORPAY_API_TIMEOUT_SECONDS,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
)
from models import DocumentOrder, User


_RAZORPAY_REFERENCE_ID_MAX_LENGTH = 40
_PAYMENT_TOKEN_BYTES = 24


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def validate_current_document_capture(
    order: DocumentOrder,
    payment_id: str,
    payment_link_entity: dict[str, Any],
    payment_entity: dict[str, Any],
) -> str | None:
    """Validate current Razorpay evidence against the immutable order."""

    expected_amount = order.price_minor
    if not expected_amount or not order.razorpay_payment_link_id:
        return "DOCUMENT_PAYMENT_CONFIGURATION_MISSING"
    if payment_link_entity.get("id") != order.razorpay_payment_link_id:
        return "DOCUMENT_PAYMENT_LINK_ID_MISMATCH"
    if payment_link_entity.get("entity") != "payment_link":
        return "DOCUMENT_PAYMENT_LINK_ENTITY_MISMATCH"
    if str(payment_link_entity.get("status") or "").lower() != "paid":
        return "DOCUMENT_PAYMENT_LINK_NOT_PAID"
    if _integer(payment_link_entity.get("amount")) != expected_amount:
        return "DOCUMENT_PAYMENT_LINK_AMOUNT_MISMATCH"
    if _integer(payment_link_entity.get("amount_paid")) != expected_amount:
        return "DOCUMENT_PAYMENT_LINK_PAID_AMOUNT_MISMATCH"
    if str(payment_link_entity.get("currency") or "").upper() != order.currency:
        return "DOCUMENT_PAYMENT_LINK_CURRENCY_MISMATCH"
    if payment_link_entity.get("reference_id") != order.payment_token:
        return "DOCUMENT_PAYMENT_TOKEN_MISMATCH"

    notes = payment_link_entity.get("notes")
    if not isinstance(notes, dict):
        return "DOCUMENT_PAYMENT_NOTES_MISSING"
    expected_notes = {
        "document_order_ref": order.public_ref,
        "revision_number": str(order.active_revision_number),
        "preview_manifest_hash": order.preview_manifest_hash,
        "product_code": order.product_code,
    }
    if any(str(notes.get(key) or "") != str(value or "") for key, value in expected_notes.items()):
        return "DOCUMENT_PAYMENT_NOTES_MISMATCH"

    payments = payment_link_entity.get("payments")
    if not isinstance(payments, list) or len(payments) != 1:
        return "DOCUMENT_CAPTURE_COUNT_MISMATCH"
    link_payment = payments[0]
    if not isinstance(link_payment, dict):
        return "DOCUMENT_CAPTURE_INVALID"
    link_payment_id = str(
        link_payment.get("payment_id") or link_payment.get("id") or ""
    )
    if link_payment_id != payment_id:
        return "DOCUMENT_CAPTURE_PAYMENT_ID_MISMATCH"
    if str(link_payment.get("status") or "").lower() != "captured":
        return "DOCUMENT_CAPTURE_NOT_CAPTURED"
    if _integer(link_payment.get("amount")) != expected_amount:
        return "DOCUMENT_CAPTURE_AMOUNT_MISMATCH"

    if payment_entity.get("id") != payment_id:
        return "DOCUMENT_PAYMENT_ID_MISMATCH"
    if payment_entity.get("entity") != "payment":
        return "DOCUMENT_PAYMENT_ENTITY_MISMATCH"
    if str(payment_entity.get("status") or "").lower() != "captured":
        return "DOCUMENT_PAYMENT_NOT_CAPTURED"
    if payment_entity.get("captured") is not True:
        return "DOCUMENT_PAYMENT_NOT_CAPTURED"
    if _integer(payment_entity.get("amount")) != expected_amount:
        return "DOCUMENT_PAYMENT_AMOUNT_MISMATCH"
    if str(payment_entity.get("currency") or "").upper() != order.currency:
        return "DOCUMENT_PAYMENT_CURRENCY_MISMATCH"
    if _integer(payment_entity.get("amount_refunded")) != 0:
        return "DOCUMENT_PAYMENT_ALREADY_REFUNDED"
    if payment_entity.get("refund_status") is not None:
        return "DOCUMENT_PAYMENT_ALREADY_REFUNDED"
    return None


def _client() -> httpx.Client:
    return httpx.Client(
        base_url="https://api.razorpay.com",
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "NyaySetu-Document-Studio/1.0",
        },
        follow_redirects=False,
        timeout=httpx.Timeout(
            RAZORPAY_API_TIMEOUT_SECONDS,
            connect=min(RAZORPAY_API_TIMEOUT_SECONDS, 5.0),
        ),
    )


def create_document_payment_link(
    order: DocumentOrder,
    user: User,
    *,
    client: httpx.Client | None = None,
) -> str:
    """Create one exact-amount link bound to order/revision/manifest."""

    if order.state != "PREVIEW_READY" or not order.preview_manifest_hash:
        raise ValueError("document_preview_not_ready")
    if not order.active_revision_number or not order.price_minor:
        raise ValueError("document_payment_configuration_incomplete")
    if order.razorpay_payment_link_id:
        raise ValueError("document_payment_link_already_exists")
    current_token = str(order.payment_token or "")
    if not current_token or len(current_token) > _RAZORPAY_REFERENCE_ID_MAX_LENGTH:
        order.payment_token = secrets.token_urlsafe(_PAYMENT_TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=PAYMENT_LINK_TTL_MINUTES
    )
    payload = {
        "amount": int(order.price_minor),
        "currency": order.currency,
        "accept_partial": False,
        "expire_by": int(expires_at.timestamp()),
        "reference_id": order.payment_token,
        "description": "NyaySetu Document Studio final PDF and DOCX",
        "customer": {
            "name": str(getattr(user, "name", None) or "NyaySetu customer")[:120],
            "contact": str(user.whatsapp_id),
        },
        "notify": {"sms": False, "email": False},
        "notes": {
            "document_order_ref": order.public_ref,
            "revision_number": str(order.active_revision_number),
            "preview_manifest_hash": order.preview_manifest_hash,
            "product_code": order.product_code,
        },
    }
    owns_client = client is None
    client = client or _client()
    try:
        response = client.post("/v1/payment_links", json=payload)
        response.raise_for_status()
        data = response.json()
    finally:
        if owns_client:
            client.close()
    if not isinstance(data, dict):
        raise RuntimeError("razorpay_document_link_invalid_response")
    link_id = str(data.get("id") or "")
    short_url = str(data.get("short_url") or "")
    if not link_id.startswith("plink_") or not short_url.startswith("https://"):
        raise RuntimeError("razorpay_document_link_missing_fields")
    order.razorpay_payment_link_id = link_id
    order.state = "PAYMENT_PENDING"
    return short_url
