"""WhatsApp Cloud API transport with centralized payload safeguards."""

from __future__ import annotations

import atexit
import copy
import json
import logging
import os
import re
import time
import unicodedata

import httpx

from config import WHATSAPP_TOKEN, WHATSAPP_API_URL
from db import SessionLocal
from models import Booking, BookingFulfillment, User
from services.ai_safety import safety_identifier
from services.booking_service import SLOT_MAP
from utils.date_utils import format_date_readable
from utils.i18n import t


logger = logging.getLogger("services.whatsapp_service")

HEADERS = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"} if WHATSAPP_TOKEN else {}

# WhatsApp Cloud API message constraints. IDs are validated rather than
# truncated because changing an opaque ID can break state routing.
TEXT_BODY_MAX = 4096
INTERACTIVE_BODY_MAX = 1024
BUTTON_COUNT_MAX = 3
BUTTON_TITLE_MAX = 20
BUTTON_ID_MAX = 256
LIST_HEADER_MAX = 60
LIST_BODY_MAX = 1024
LIST_ACTION_TITLE_MAX = 20
LIST_SECTION_TITLE_MAX = 24
LIST_ROW_COUNT_MAX = 10
LIST_ROW_ID_MAX = 200
LIST_ROW_TITLE_MAX = 24
LIST_ROW_DESCRIPTION_MAX = 72
DOCUMENT_CAPTION_MAX = 1024
TEMPLATE_NAME_MAX = 512
LANGUAGE_CODE_MAX = 35

_TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_UNAMBIGUOUS_TRANSPORT_FAILURES = {
    "ConnectError",
    "ConnectTimeout",
    "PoolTimeout",
}


class WhatsAppValidationError(ValueError):
    """Raised before network I/O when a message cannot be sent safely."""


def is_retryable_delivery_failure(result) -> bool:
    """Return whether another send is known not to duplicate an accepted one."""

    if not isinstance(result, dict) or result.get("ok") is True:
        return False

    error = result.get("error")
    if error == "no_whatsapp_config":
        # No provider request was attempted. A later worker run can recover
        # after configuration is restored.
        return True
    if error == "whatsapp_transport_error":
        return result.get("reason") in _UNAMBIGUOUS_TRANSPORT_FAILURES
    if error == "whatsapp_api_error":
        try:
            status_code = int(result.get("status_code"))
        except (TypeError, ValueError):
            return False
        return status_code in _TRANSIENT_STATUSES
    return False


def is_ambiguous_delivery_failure(result) -> bool:
    """Return whether Meta may have accepted a request before transport failed."""

    return bool(
        isinstance(result, dict)
        and result.get("ok") is not True
        and result.get("error") == "whatsapp_transport_error"
        and result.get("reason") not in _UNAMBIGUOUS_TRANSPORT_FAILURES
    )


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


_HTTP_CLIENT = httpx.Client(
    timeout=httpx.Timeout(
        _env_float("WHATSAPP_TIMEOUT_SECONDS", 12.0, 2.0, 60.0),
        connect=_env_float("WHATSAPP_CONNECT_TIMEOUT_SECONDS", 5.0, 1.0, 30.0),
    ),
    headers=HEADERS,
    limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
)
atexit.register(_HTTP_CLIENT.close)


def _truncate_text(value, limit: int, field: str, allow_empty: bool = False) -> str:
    if value is None:
        value = ""
    text = str(value).strip()
    if not text and not allow_empty:
        raise WhatsAppValidationError(f"{field} is required")
    if len(text) <= limit:
        return text

    clipped = text[:limit]
    # Avoid ending on a combining mark or zero-width joiner. This is a
    # dependency-free best effort for Devanagari and emoji text.
    while clipped and (
        unicodedata.combining(clipped[-1])
        or clipped[-1] in {"\u200c", "\u200d", "\ufe0f"}
    ):
        clipped = clipped[:-1]
    clipped = clipped.rstrip()
    if not clipped and not allow_empty:
        raise WhatsAppValidationError(f"{field} cannot be truncated safely")
    return clipped


def _validate_identifier(value, limit: int, field: str) -> str:
    identifier = str(value or "").strip()
    if not identifier:
        raise WhatsAppValidationError(f"{field} is required")
    if len(identifier) > limit:
        raise WhatsAppValidationError(f"{field} exceeds {limit} characters")
    return identifier


def _validate_recipient(value) -> str:
    recipient = str(value or "").strip()
    if not recipient or len(recipient) > 32 or not re.fullmatch(r"\+?[0-9]+", recipient):
        raise WhatsAppValidationError("recipient must be a valid WhatsApp number")
    return recipient.lstrip("+")


def _validate_button_message(interactive: dict) -> None:
    body = interactive.setdefault("body", {})
    body["text"] = _truncate_text(
        body.get("text"),
        INTERACTIVE_BODY_MAX,
        "interactive.body.text",
    )

    action = interactive.setdefault("action", {})
    buttons = action.get("buttons")
    if not isinstance(buttons, list) or not 1 <= len(buttons) <= BUTTON_COUNT_MAX:
        raise WhatsAppValidationError("reply buttons must contain between 1 and 3 items")

    seen_ids = set()
    for index, button in enumerate(buttons):
        if not isinstance(button, dict):
            raise WhatsAppValidationError(f"button {index} must be an object")
        button["type"] = "reply"
        reply = button.setdefault("reply", {})
        reply_id = _validate_identifier(
            reply.get("id"),
            BUTTON_ID_MAX,
            f"button {index} id",
        )
        if reply_id in seen_ids:
            raise WhatsAppValidationError("reply button IDs must be unique")
        seen_ids.add(reply_id)
        reply["id"] = reply_id
        reply["title"] = _truncate_text(
            reply.get("title"),
            BUTTON_TITLE_MAX,
            f"button {index} title",
        )


def _validate_list_message(interactive: dict) -> None:
    if "header" in interactive:
        header = interactive.get("header")
        if not isinstance(header, dict):
            raise WhatsAppValidationError("interactive.header must be an object")
        header["type"] = "text"
        header["text"] = _truncate_text(
            header.get("text"),
            LIST_HEADER_MAX,
            "list header",
        )

    body = interactive.setdefault("body", {})
    body["text"] = _truncate_text(
        body.get("text"),
        LIST_BODY_MAX,
        "list body",
    )

    action = interactive.setdefault("action", {})
    action["button"] = _truncate_text(
        action.get("button"),
        LIST_ACTION_TITLE_MAX,
        "list action button",
    )
    sections = action.get("sections")
    if not isinstance(sections, list) or not sections:
        raise WhatsAppValidationError("list message requires at least one section")

    row_count = 0
    seen_ids = set()
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise WhatsAppValidationError(f"section {section_index} must be an object")
        section["title"] = _truncate_text(
            section.get("title"),
            LIST_SECTION_TITLE_MAX,
            f"section {section_index} title",
        )
        rows = section.get("rows")
        if not isinstance(rows, list) or not rows:
            raise WhatsAppValidationError(f"section {section_index} requires rows")
        row_count += len(rows)

        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise WhatsAppValidationError(
                    f"section {section_index} row {row_index} must be an object"
                )
            row_id = _validate_identifier(
                row.get("id"),
                LIST_ROW_ID_MAX,
                f"section {section_index} row {row_index} id",
            )
            if row_id in seen_ids:
                raise WhatsAppValidationError("list row IDs must be unique")
            seen_ids.add(row_id)
            row["id"] = row_id
            row["title"] = _truncate_text(
                row.get("title"),
                LIST_ROW_TITLE_MAX,
                f"section {section_index} row {row_index} title",
            )
            row["description"] = _truncate_text(
                row.get("description", ""),
                LIST_ROW_DESCRIPTION_MAX,
                f"section {section_index} row {row_index} description",
                allow_empty=True,
            )

    if row_count > LIST_ROW_COUNT_MAX:
        raise WhatsAppValidationError(
            f"list messages support at most {LIST_ROW_COUNT_MAX} rows"
        )


def _validate_template_message(template: dict) -> None:
    if not isinstance(template, dict):
        raise WhatsAppValidationError("template must be an object")
    name = _validate_identifier(
        template.get("name"),
        TEMPLATE_NAME_MAX,
        "template name",
    )
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise WhatsAppValidationError(
            "template name must contain lowercase letters, numbers, and underscores"
        )
    template["name"] = name

    language = template.setdefault("language", {})
    code = _validate_identifier(
        language.get("code"),
        LANGUAGE_CODE_MAX,
        "template language code",
    )
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:_[A-Za-z]{2})?", code):
        raise WhatsAppValidationError("invalid template language code")
    language["code"] = code

    components = template.get("components", [])
    if not isinstance(components, list):
        raise WhatsAppValidationError("template components must be a list")
    try:
        json.dumps(components)
    except (TypeError, ValueError) as exc:
        raise WhatsAppValidationError("template components must be JSON serializable") from exc


def _validate_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise WhatsAppValidationError("payload must be an object")

    normalized = copy.deepcopy(payload)
    normalized["messaging_product"] = "whatsapp"
    normalized["to"] = _validate_recipient(normalized.get("to"))
    message_type = str(normalized.get("type") or "").strip()

    if message_type == "text":
        text = normalized.setdefault("text", {})
        text["body"] = _truncate_text(
            text.get("body"),
            TEXT_BODY_MAX,
            "text body",
        )
    elif message_type == "interactive":
        interactive = normalized.get("interactive")
        if not isinstance(interactive, dict):
            raise WhatsAppValidationError("interactive message body is required")
        interactive_type = interactive.get("type")
        if interactive_type == "button":
            _validate_button_message(interactive)
        elif interactive_type == "list":
            _validate_list_message(interactive)
        else:
            raise WhatsAppValidationError(
                f"unsupported interactive message type: {interactive_type}"
            )
    elif message_type == "document":
        document = normalized.get("document")
        if not isinstance(document, dict):
            raise WhatsAppValidationError("document message body is required")
        document["id"] = _validate_identifier(
            document.get("id"),
            256,
            "document media ID",
        )
        document["caption"] = _truncate_text(
            document.get("caption", ""),
            DOCUMENT_CAPTION_MAX,
            "document caption",
            allow_empty=True,
        )
    elif message_type == "template":
        _validate_template_message(normalized.get("template"))
    else:
        raise WhatsAppValidationError(f"unsupported message type: {message_type}")

    return normalized


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        raw_retry_after = response.headers.get("Retry-After", "")
        try:
            return min(2.0, max(0.0, float(raw_retry_after)))
        except (TypeError, ValueError):
            pass
    return min(1.0, 0.25 * (2**attempt))


def _request_with_retries(method: str, url: str, operation: str, **kwargs):
    max_retries = _env_int("WHATSAPP_HTTP_MAX_RETRIES", 1, 0, 2)
    attempt = 0
    while True:
        try:
            response = _HTTP_CLIENT.request(method, url, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            if attempt >= max_retries:
                raise
            logger.warning(
                "WHATSAPP_RETRY | operation=%s | attempt=%s | reason=%s",
                operation,
                attempt + 1,
                type(exc).__name__,
            )
            time.sleep(_retry_delay(None, attempt))
            attempt += 1
            continue
        except httpx.RequestError:
            # Avoid retrying read failures because Meta may already have accepted
            # the message, which could create a duplicate user-visible send.
            raise

        if response.status_code in _TRANSIENT_STATUSES and attempt < max_retries:
            logger.warning(
                "WHATSAPP_RETRY | operation=%s | attempt=%s | status=%s",
                operation,
                attempt + 1,
                response.status_code,
            )
            time.sleep(_retry_delay(response, attempt))
            attempt += 1
            continue
        return response


_TOKEN_RE = re.compile(r"(?i)\b(bearer|token|secret|key)\s*[:=]\s*\S+")
_LONG_DIGIT_RE = re.compile(r"(?<!\d)\+?\d{7,}(?!\d)")


def _redact_error_text(value) -> str:
    text = str(value or "")
    text = _TOKEN_RE.sub(r"\1=[REDACTED]", text)
    text = _LONG_DIGIT_RE.sub("[REDACTED]", text)
    return _truncate_text(text, 300, "error text", allow_empty=True)


def _safe_api_error(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        return {"message": "Non-JSON response from WhatsApp"}

    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    if not isinstance(error, dict):
        return {"message": "Unknown WhatsApp API error"}
    return {
        "message": _redact_error_text(error.get("message", "WhatsApp API error")),
        "type": str(error.get("type", ""))[:80],
        "code": error.get("code"),
        "error_subcode": error.get("error_subcode"),
        "fbtrace_id": str(error.get("fbtrace_id", ""))[:100],
    }


def _response_result(response: httpx.Response) -> dict:
    if 200 <= response.status_code < 300:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        result = dict(payload) if isinstance(payload, dict) else {}
        result["ok"] = True
        result["status_code"] = response.status_code
        return result

    return {
        "ok": False,
        "error": "whatsapp_api_error",
        "status_code": response.status_code,
        "details": _safe_api_error(response),
    }


def _send(payload: dict):
    if not WHATSAPP_API_URL or not WHATSAPP_TOKEN:
        logger.warning("WhatsApp transport is not configured; send skipped")
        return {"ok": False, "error": "no_whatsapp_config"}

    normalized = _validate_payload(payload)
    message_type = normalized["type"]
    recipient_ref = safety_identifier(normalized["to"])
    logger.info(
        "WHATSAPP_SEND | type=%s | recipient_ref=%s",
        message_type,
        recipient_ref,
    )

    try:
        response = _request_with_retries(
            "POST",
            WHATSAPP_API_URL,
            operation=f"send_{message_type}",
            json=normalized,
        )
    except httpx.RequestError as exc:
        logger.error(
            "WHATSAPP_TRANSPORT_ERROR | type=%s | recipient_ref=%s | reason=%s",
            message_type,
            recipient_ref,
            type(exc).__name__,
        )
        return {
            "ok": False,
            "error": "whatsapp_transport_error",
            "reason": type(exc).__name__,
        }

    result = _response_result(response)
    if result["ok"]:
        logger.info(
            "WHATSAPP_SENT | type=%s | recipient_ref=%s | status=%s",
            message_type,
            recipient_ref,
            response.status_code,
        )
    else:
        logger.error(
            "WHATSAPP_API_ERROR | type=%s | recipient_ref=%s | status=%s | code=%s",
            message_type,
            recipient_ref,
            response.status_code,
            result["details"].get("code"),
        )
    return result


def send_text(wa_id: str, body: str):
    return _send(
        {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "text",
            "text": {"body": body},
        }
    )


def send_buttons(wa_id: str, body: str, buttons: list):
    return _send(
        {
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
                                "id": button["id"],
                                "title": button["title"],
                            },
                        }
                        for button in buttons
                    ]
                },
            },
        }
    )


def send_typing_on(wa_id: str):
    logger.debug("SIMULATED_TYPING_ON | recipient_ref=%s", safety_identifier(wa_id))
    return {"ok": True}


def send_typing_off(wa_id: str):
    logger.debug("SIMULATED_TYPING_OFF | recipient_ref=%s", safety_identifier(wa_id))
    return {"ok": True}


def send_list_picker(
    wa_id: str,
    header: str,
    body: str,
    rows: list,
    section_title: str = "Options",
    button_title: str = "Select",
):
    return _send(
        {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": header},
                "body": {"text": body},
                "action": {
                    "button": button_title,
                    "sections": [
                        {
                            "title": section_title,
                            "rows": [
                                {
                                    "id": row["id"],
                                    "title": row["title"],
                                    "description": row.get("description", ""),
                                }
                                for row in rows
                            ],
                        }
                    ],
                },
            },
        }
    )


def send_template(
    wa_id: str,
    template_name: str,
    language_code: str = "en",
    components: list | None = None,
):
    """Send an approved template, including outside the 24-hour service window."""

    template = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if components:
        template["components"] = components
    return _send(
        {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "template",
            "template": template,
        }
    )


def send_approved_template(
    wa_id: str,
    template_name: str,
    language_code: str,
    components: list | None = None,
):
    """Explicit transactional alias for a Meta-approved template send."""

    return send_template(
        wa_id,
        template_name,
        language_code=language_code,
        components=components,
    )


def send_payment_success_message(booking):
    """Send a localized payment-success message without logging personal data."""

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
            return {"ok": False, "error": "user_not_found"}

        fulfillment = (
            db.query(BookingFulfillment)
            .filter(BookingFulfillment.booking_id == booking.id)
            .first()
        )
        translation_key = (
            "payment_success_reschedule_review"
            if fulfillment
            and getattr(fulfillment, "status", None)
            == "RESCHEDULE_REQUIRED"
            else "payment_success"
        )
        message = t(
            user,
            translation_key,
            date=format_date_readable(booking.date),
            slot=SLOT_MAP.get(booking.slot_code, "N/A"),
            amount=booking.amount,
        )
        return send_text(booking.whatsapp_id, message)
    finally:
        db.close()


def send_document(wa_id: str, file_path: str, caption: str = ""):
    if not WHATSAPP_API_URL or not WHATSAPP_TOKEN:
        logger.warning("WhatsApp transport is not configured; document send skipped")
        return {"ok": False, "error": "no_whatsapp_config"}

    if not os.path.exists(file_path):
        logger.error("Document send failed: file not found")
        return {"ok": False, "error": "file_not_found"}

    recipient = _validate_recipient(wa_id)
    media_url = WHATSAPP_API_URL.replace("/messages", "/media")
    try:
        with open(file_path, "rb") as file_handle:
            file_content = file_handle.read()
    except OSError as exc:
        logger.error("Document read failed | reason=%s", type(exc).__name__)
        return {
            "ok": False,
            "error": "file_read_failed",
            "reason": type(exc).__name__,
        }

    files = {
        "file": (
            os.path.basename(file_path),
            file_content,
            "application/pdf",
        )
    }
    try:
        upload_response = _request_with_retries(
            "POST",
            media_url,
            operation="upload_document",
            files=files,
            data={"messaging_product": "whatsapp"},
        )
    except httpx.RequestError as exc:
        logger.error(
            "WHATSAPP_MEDIA_TRANSPORT_ERROR | recipient_ref=%s | reason=%s",
            safety_identifier(recipient),
            type(exc).__name__,
        )
        return {
            "ok": False,
            "error": "media_transport_error",
            "reason": type(exc).__name__,
        }

    upload_result = _response_result(upload_response)
    if not upload_result["ok"]:
        logger.error(
            "WHATSAPP_MEDIA_API_ERROR | recipient_ref=%s | status=%s",
            safety_identifier(recipient),
            upload_response.status_code,
        )
        return {
            "ok": False,
            "error": "media_upload_failed",
            "status_code": upload_response.status_code,
            "details": upload_result.get("details", {}),
        }

    media_id = upload_result.get("id")
    if not media_id:
        logger.error(
            "WHATSAPP_MEDIA_RESPONSE_INVALID | recipient_ref=%s",
            safety_identifier(recipient),
        )
        return {"ok": False, "error": "media_id_missing"}

    return _send(
        {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "document",
            "document": {
                "id": media_id,
                "caption": caption or "",
            },
        }
    )


def send_payment_receipt_pdf(
    wa_id: str,
    pdf_path: str,
    *,
    booking_id: int | None = None,
):
    """Send a receipt and track only the explicitly identified booking.

    Legacy callers may omit ``booking_id`` and manage their own exact booking
    transaction. The transport must never infer a booking from the user's most
    recent record because a user can have multiple paid consultations.
    """

    result = send_document(
        wa_id=wa_id,
        file_path=pdf_path,
        caption="Payment receipt for your NyaySetu consultation.",
    )
    if not isinstance(result, dict) or result.get("ok") is not True:
        return result

    tracked_result = dict(result)
    tracked_result["receipt_status_recorded"] = False
    if booking_id is None:
        return tracked_result

    # The provider has accepted the document. A local tracking failure must not
    # turn that accepted send into an automatic duplicate. Durable outbox
    # callers also mark their exact booking in the outbox transaction.
    db = None
    try:
        db = SessionLocal()
        updated = (
            db.query(Booking)
            .filter(
                Booking.id == booking_id,
                Booking.whatsapp_id == wa_id,
            )
            .update(
                {Booking.receipt_sent: True},
                synchronize_session=False,
            )
        )
        if updated == 1:
            db.commit()
            tracked_result["receipt_status_recorded"] = True
        else:
            db.rollback()
            tracked_result["receipt_status_recorded"] = False
    except Exception as exc:
        if db is not None:
            db.rollback()
        # Database/provider exception strings can contain private request
        # details. The class name is sufficient for operational grouping.
        logger.error(
            "Receipt delivery tracking failed | reason=%s",
            type(exc).__name__,
        )
        tracked_result["receipt_status_recorded"] = False
    finally:
        if db is not None:
            db.close()
    return tracked_result
