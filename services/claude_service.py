"""Anthropic-backed legal information with privacy-preserving safeguards."""

from __future__ import annotations

import logging
import os
import re

from services.ai_safety import (
    guardrail_response,
    language_code,
    pii_was_scrubbed,
    safety_identifier,
    scrub_pii,
)


logger = logging.getLogger("services.claude_service")


class ClaudeProviderError(RuntimeError):
    """Raised internally so the router can try another configured provider."""


DISCLAIMER = {
    "en": (
        "\n\n⚠️ Disclaimer: This is general legal information, not legal advice. "
        "Consult a qualified lawyer for advice on your facts."
    ),
    "hi": (
        "\n\n⚠️ Disclaimer: Yeh general legal information hai, final legal advice "
        "nahi. Apne facts ke liye qualified lawyer se salah lein."
    ),
    "mr": (
        "\n\n⚠️ अस्वीकरण: ही सामान्य कायदेशीर माहिती आहे, अंतिम कायदेशीर सल्ला "
        "नाही. आपल्या परिस्थितीसाठी पात्र वकिलाचा सल्ला घ्या."
    ),
}


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


def _language_instruction(user) -> str:
    lang = language_code(user)
    if lang == "hi":
        return "Reply in clear, respectful Hinglish."
    if lang == "mr":
        return "Reply in clear, respectful Marathi."
    return "Reply in concise, respectful English."


def _system_prompt(user) -> str:
    return f"""
You are NyaySetu, an Indian legal information assistant, not a lawyer.

{_language_instruction(user)}

Rules:
- Provide general Indian legal information only.
- Explain lawful processes, documents, and possible next steps.
- Do not guarantee outcomes, provide a final legal opinion, or invent a section.
- Do not help harm someone, evade lawful authorities, destroy or fabricate
  evidence, forge documents, hack, stalk, blackmail, or bribe.
- Use current criminal-law terminology: Bharatiya Nyaya Sanhita, 2023 (BNS),
  Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS), and Bharatiya Sakshya
  Adhiniyam, 2023 (BSA). Refer to the legacy IPC, CrPC, or Evidence Act only
  where dates or transitional application make that useful.
- If a law, deadline, forum, or section is uncertain, say that a qualified
  lawyer should verify it.
- Never ask for passwords, OTPs, complete identity numbers, or bank/card data.
- Keep the answer under 220 words.
""".strip()


def _model_supports_temperature(model: str) -> bool:
    """Return whether the selected Claude model accepts sampling temperature.

    Anthropic deprecated non-default temperature for Opus 4.7 and later. A
    long numeric token immediately after ``opus-4`` is a dated Opus 4 snapshot,
    not a minor version (for example ``claude-opus-4-20250514``).
    """

    match = re.search(
        r"(?:^|-)opus-(?P<major>\d+)(?:[.-](?P<minor>\d+))?",
        model.strip().lower(),
    )
    if not match:
        return True

    major = int(match.group("major"))
    if major > 4:
        return False
    if major < 4:
        return True

    minor_token = match.group("minor")
    if not minor_token or len(minor_token) >= 6:
        return True
    return int(minor_token) < 7


def _message_request(model: str, provider_message: str, user, user_ref: str) -> dict:
    request = {
        "model": model,
        "max_tokens": _env_int("ANTHROPIC_MAX_TOKENS", 400, 100, 1000),
        "system": _system_prompt(user),
        "metadata": {"user_id": user_ref},
        "messages": [{"role": "user", "content": provider_message}],
    }
    if _model_supports_temperature(model):
        request["temperature"] = 0.2
    return request


def _local_fallback(message: str, user, context: str) -> str:
    from services.local_ai_service import local_ai_reply

    return local_ai_reply(scrub_pii(message), user, context)


def claude_reply_external(message, user, context="general"):
    """Call Anthropic or raise ``ClaudeProviderError`` for router fallback."""

    if not message:
        return "Please ask a legal question."

    guarded = guardrail_response(message, user)
    if guarded:
        return guarded

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ClaudeProviderError("missing_api_key")
    model = os.getenv("ANTHROPIC_MODEL", "").strip()
    if not model:
        # Model lifecycle and regional availability change independently of
        # this application. Production must explicitly select an approved
        # current model instead of silently using a retired identifier.
        raise ClaudeProviderError("missing_model")

    provider_message = scrub_pii(message)
    user_ref = safety_identifier(user)
    logger.info(
        "AI_CALL | provider=claude | user_ref=%s | context=%s | pii_scrubbed=%s",
        user_ref,
        context,
        pii_was_scrubbed(message, provider_message),
    )

    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise ClaudeProviderError("anthropic_package_unavailable") from exc

    try:
        client = Anthropic(
            api_key=api_key,
            max_retries=0,
            timeout=_env_float("ANTHROPIC_TIMEOUT_SECONDS", 15.0, 2.0, 60.0),
        )
        response = client.messages.create(
            **_message_request(
                model,
                provider_message,
                user,
                user_ref,
            )
        )
        answer = response.content[0].text.strip()
    except Exception as exc:
        raise ClaudeProviderError(type(exc).__name__) from exc

    if not answer:
        raise ClaudeProviderError("empty_response")

    answer = scrub_pii(answer)
    return answer + DISCLAIMER[language_code(user)]


def claude_reply(message, user, context="general"):
    """Compatibility wrapper that always returns a safe user-facing string."""

    guarded = guardrail_response(message, user)
    if guarded:
        return guarded

    try:
        return claude_reply_external(message, user, context)
    except ClaudeProviderError as exc:
        logger.warning(
            "AI_PROVIDER_FALLBACK | provider=claude | user_ref=%s | reason=%s",
            safety_identifier(user),
            str(exc),
        )
        return _local_fallback(message, user, context)
    except Exception as exc:
        logger.error(
            "AI_PROVIDER_FALLBACK | provider=claude | user_ref=%s | reason=%s",
            safety_identifier(user),
            type(exc).__name__,
        )
        return _local_fallback(message, user, context)
