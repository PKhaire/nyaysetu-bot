"""Local, non-authoritative Maharashtra PIN assistance."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path


REFERENCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "maharashtra_pincodes.json"
)


@lru_cache(maxsize=1)
def _pincodes() -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    records = payload.get("pincodes")
    return records if isinstance(records, dict) else {}


@lru_cache(maxsize=1)
def postal_reference_manifest() -> dict[str, object]:
    """Return the source identity bound into the release schema hash."""

    try:
        content = REFERENCE_PATH.read_bytes()
        payload = json.loads(content)
    except (OSError, ValueError, TypeError):
        return {
            "available": False,
            "content_hash": "",
            "record_count": 0,
            "source": {},
        }
    records = payload.get("pincodes")
    return {
        "available": isinstance(records, dict) and bool(records),
        "content_hash": hashlib.sha256(content).hexdigest(),
        "record_count": len(records) if isinstance(records, dict) else 0,
        "source": payload.get("source") or {},
    }


def lookup_maharashtra_pin(pin: object) -> dict[str, tuple[str, ...]] | None:
    """Return bounded postal hints, never a customer-confirmed address."""

    record = _pincodes().get(str(pin or "").strip())
    if not isinstance(record, dict):
        return None

    def values(key: str, limit: int) -> tuple[str, ...]:
        raw = record.get(key)
        if not isinstance(raw, list):
            return ()
        cleaned = tuple(
            str(value).strip()
            for value in raw
            if str(value).strip()
        )
        return cleaned[:limit]

    return {
        "districts": values("districts", 3),
        "talukas": values("talukas", 5),
        "offices": values("offices", 5),
    }
