"""Shared safety policy for outbound consultation reminders.

The scheduler and outbox worker intentionally resolve the same live
configuration. A queued reminder therefore stops being sendable immediately
when an operator clears its template configuration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from config import CONSULTATION_REMINDER_TEMPLATES
from utils.date_utils import format_date_readable


REMINDER_HORIZONS = {
    "2h": timedelta(hours=2),
    "24h": timedelta(hours=24),
}

# Exception/review states are deliberately excluded even though they are not
# terminal: a reminder while a refund or reschedule is being reviewed can
# mislead the user. UNASSIGNED remains eligible so an assignment delay does
# not suppress an otherwise valid paid appointment reminder.
REMINDER_ELIGIBLE_FULFILLMENT_STATUSES = frozenset(
    {"UNASSIGNED", "ASSIGNED", "CONFIRMED"}
)

_HINDI_LANGUAGE_VALUES = frozenset({"hi", "hindi", "hinglish"})
_MARATHI_LANGUAGE_VALUES = frozenset(
    {
        "mr",
        "marathi",
        "मराठी",
        # Preserve compatibility with historical mojibake values already
        # accepted by the bot's i18n layer.
        "à¤®à¤°à¤¾à¤ à¥€",
    }
)


def as_naive_utc(value: datetime) -> datetime:
    """Normalize a datetime to the database's naive-UTC convention."""

    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def normalized_language(value: Any) -> str:
    """Return one of the reminder configuration language keys."""

    normalized = str(value or "en").strip().lower()
    if normalized in _HINDI_LANGUAGE_VALUES:
        return "hi"
    if normalized in _MARATHI_LANGUAGE_VALUES:
        return "mr"
    return "en"


def configured_template(
    reminder_kind: str,
    user_language: Any,
) -> tuple[str, str] | None:
    """Return an exact configured template pair; never cross-language fallback."""

    language = normalized_language(user_language)
    reminder_templates = CONSULTATION_REMINDER_TEMPLATES.get(
        reminder_kind,
        {},
    )
    values = reminder_templates.get(language, {})
    name = str(values.get("name") or "").strip()
    language_code = str(values.get("language_code") or "").strip()
    if not name or not language_code:
        return None
    return name, language_code


def configured_variant_count() -> int:
    """Count fully configured variants without exposing their identifiers."""

    return sum(
        1
        for reminder_kind in REMINDER_HORIZONS
        for values in CONSULTATION_REMINDER_TEMPLATES.get(
            reminder_kind,
            {},
        ).values()
        if str(values.get("name") or "").strip()
        and str(values.get("language_code") or "").strip()
    )


def reminder_due_window(
    scheduled_start_at: datetime,
    reminder_kind: str,
    catchup_minutes: int,
) -> tuple[datetime, datetime]:
    """Return the inclusive due time and exclusive stale cutoff."""

    horizon = REMINDER_HORIZONS[reminder_kind]
    due_at = as_naive_utc(scheduled_start_at) - horizon
    return due_at, due_at + timedelta(minutes=catchup_minutes)


def template_components(booking: Any) -> list[dict[str, Any]]:
    """Build the documented two-positional-variable template contract."""

    date_text = format_date_readable(getattr(booking, "date", None))
    slot_text = str(getattr(booking, "slot_readable", "") or "").strip()
    if not slot_text:
        slot_text = "Scheduled time"
    return [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": date_text[:100]},
                {"type": "text", "text": slot_text[:100]},
            ],
        }
    ]
