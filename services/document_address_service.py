"""Canonical address rendering for the single Draft Studio schema."""

from __future__ import annotations

import re


_WHITESPACE = re.compile(r"\s+")


def normalize_address_lines(value: object) -> str:
    """Return bounded customer text in a stable single-line display form."""

    return _WHITESPACE.sub(" ", str(value or "").strip()).strip(" ,")


def render_premises_address(answers: dict[str, object]) -> str:
    """Render the exact confirmed property description with state and PIN."""

    address = normalize_address_lines(answers.get("premises_address_lines"))
    pin = str(answers.get("premises_pin") or "").strip()
    if not address:
        return ""

    rendered = address
    if "maharashtra" not in address.casefold():
        rendered += ", Maharashtra"
    if pin and pin not in address:
        rendered += f" - {pin}"
    return rendered
