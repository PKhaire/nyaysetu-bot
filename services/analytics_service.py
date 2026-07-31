"""Privacy-conscious, best-effort product analytics writes."""

from __future__ import annotations

import enum
import json
import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from config import ANALYTICS_MAX_PROPERTY_BYTES
from db import session_scope
from models import AnalyticsEvent


logger = logging.getLogger(__name__)

# Analytics must never become a shadow store for legal intake or contact data.
_SENSITIVE_KEYS = frozenset(
    {
        "address",
        "contact",
        "email",
        "legal_issue",
        "message",
        "name",
        "phone",
        "prompt",
        "query",
        "text",
        "whatsapp_id",
        "wa_id",
    }
)
_MAX_DEPTH = 4
_MAX_COLLECTION_ITEMS = 50
_MAX_STRING_LENGTH = 500


def _safe_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if key.lower() in _SENSITIVE_KEYS:
        return "[REDACTED]"
    if depth >= _MAX_DEPTH:
        return "[MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_STRING_LENGTH]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return _safe_value(value.value, key=key, depth=depth + 1)
    if isinstance(value, Mapping):
        return {
            str(item_key)[:100]: _safe_value(
                item_value,
                key=str(item_key),
                depth=depth + 1,
            )
            for item_key, item_value in list(value.items())[
                :_MAX_COLLECTION_ITEMS
            ]
        }
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [
            _safe_value(item, depth=depth + 1)
            for item in list(value)[:_MAX_COLLECTION_ITEMS]
        ]
    return str(value)[:_MAX_STRING_LENGTH]


def _compact_properties(properties: Mapping[str, Any] | None) -> str:
    sanitized = _safe_value(properties or {})
    encoded = json.dumps(
        sanitized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    encoded_size = len(encoded.encode("utf-8"))
    if encoded_size <= ANALYTICS_MAX_PROPERTY_BYTES:
        return encoded

    return json.dumps(
        {
            "_truncated": True,
            "_original_bytes": encoded_size,
        },
        separators=(",", ":"),
    )


def record_event(
    event_name: str,
    properties: Mapping[str, Any] | None = None,
    *,
    user_id: int | None = None,
    session_id: str | None = None,
) -> bool:
    """Persist one event without ever interrupting the user-facing workflow."""

    normalized_name = (event_name or "").strip()[:100]
    if not normalized_name:
        logger.warning("Analytics event skipped because its name is empty")
        return False

    try:
        event = AnalyticsEvent(
            event_name=normalized_name,
            user_id=user_id,
            session_id=(session_id or "").strip()[:128] or None,
            properties_json=_compact_properties(properties),
        )
        with session_scope() as session:
            session.add(event)
        return True
    except Exception as exc:
        # Deliberately omit values and exception messages: both may contain PII.
        logger.warning(
            "Analytics event write failed | event=%s | error_type=%s",
            normalized_name,
            type(exc).__name__,
        )
        return False


# Friendly aliases for callers that prefer product-analytics terminology.
track_event = record_event
record_analytics_event = record_event
