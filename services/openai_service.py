"""OpenAI-backed legal information with deterministic privacy safeguards."""

from __future__ import annotations

import atexit
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
from threading import Lock
import time
from typing import Dict, Tuple

import httpx

from config import (
    AI_RESPONSE_CACHE_TTL_SECONDS,
    OPENAI_API_KEY as CONFIG_OPENAI_API_KEY,
    OPENAI_FALLBACK_MODEL as CONFIG_OPENAI_FALLBACK_MODEL,
    OPENAI_MODEL as CONFIG_OPENAI_MODEL,
)
from services.ai_safety import (
    guardrail_response,
    language_code,
    pii_was_scrubbed,
    safety_identifier,
    scrub_pii,
)
from translations import TRANSLATIONS


logger = logging.getLogger("services.openai_service")


class OpenAIProviderError(RuntimeError):
    """Raised internally so the router can try another configured provider."""


# Kept as a module-level value because app.py imports it today.
AI_DISABLED_UNTIL = None


ADMIN_DISCLAIMERS = {
    "en": "\n\n⚠️ Disclaimer: This is general legal information, not a substitute for professional legal advice.",
    "hi": "\n\n⚠️ Disclaimer: Yeh general legal information hai, professional legal advice ka replacement nahi hai.",
    "mr": "\n\n⚠️ अस्वीकरण: ही सामान्य कायदेशीर माहिती आहे, व्यावसायिक कायदेशीर सल्ल्याचा पर्याय नाही.",
}

BOOKING_CTA = {
    "en": "If you need personalised advice, you may consider booking a consultation.",
    "hi": "Agar aapko personalised guidance chahiye, toh consultation book kar sakte ho 🙂",
    "mr": "आपल्याला वैयक्तिक मार्गदर्शन हवे असल्यास सल्ला बुक करू शकता.",
}


AI_RESPONSE_CACHE: Dict[Tuple[str, str], Tuple[float, str]] = {}
AI_CACHE_TTL = AI_RESPONSE_CACHE_TTL_SECONDS
AI_CACHE_MAX_ENTRIES = 1_000
_AI_STATE_LOCK = Lock()

_MODEL_FALLBACK_STATUSES = frozenset({400, 403, 404, 422})
_MODEL_ERROR_CODES = frozenset(
    {
        "invalid_model",
        "model_deprecated",
        "model_not_available",
        "model_not_found",
        "model_not_supported",
        "unsupported_model",
    }
)
_MODEL_ERROR_MESSAGE_MARKERS = (
    "access to this model",
    "does not exist",
    "does not have access",
    "model is deprecated",
    "model is not available",
    "model is not supported",
    "model not found",
    "unsupported model",
)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


_OPENAI_TIMEOUT = httpx.Timeout(
    _env_float("OPENAI_TIMEOUT_SECONDS", 12.0, 2.0, 60.0),
    connect=_env_float("OPENAI_CONNECT_TIMEOUT_SECONDS", 5.0, 1.0, 30.0),
)
_HTTP_CLIENT = httpx.Client(
    timeout=_OPENAI_TIMEOUT,
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)
atexit.register(_HTTP_CLIENT.close)


def _tone_instruction(user):
    lang = language_code(user)
    if lang == "hi":
        return "Use a friendly, supportive Hinglish tone."
    if lang == "mr":
        return "Use a polite and respectful Marathi tone."
    return "Use a professional and formal English tone."


def _length_instruction(user):
    lang = language_code(user)
    if lang == "hi":
        return "Keep the response medium length and conversational."
    if lang == "mr":
        return "Explain clearly with moderate detail."
    return "Keep the response concise and to the point."


def _language_instruction(user):
    lang = language_code(user)
    if lang == "hi":
        return "Reply in simple Hinglish (Hindi + English mix)."
    if lang == "mr":
        return "Reply in simple Marathi."
    return "Reply in clear English."


def _disclaimer_text(user):
    lang = language_code(user)
    return ADMIN_DISCLAIMERS.get(lang, ADMIN_DISCLAIMERS["en"])


def _booking_cta(user):
    lang = language_code(user)
    return BOOKING_CTA.get(lang, BOOKING_CTA["en"])


def _t(user, key):
    lang = language_code(user)
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(
        key,
        TRANSLATIONS["en"].get(key, ""),
    )


def _normalize_prompt(prompt: str) -> str:
    return " ".join(str(prompt or "").lower().strip().split())


def _prompt_digest(prompt: str) -> str:
    return hashlib.sha256(_normalize_prompt(prompt).encode("utf-8")).hexdigest()


def _get_cached_reply(cache_user_key: str, prompt: str):
    if AI_CACHE_TTL <= 0:
        return None

    key = (cache_user_key, _prompt_digest(prompt))
    with _AI_STATE_LOCK:
        cached = AI_RESPONSE_CACHE.get(key)
        if not cached:
            return None

        timestamp, reply = cached
        if time.time() - timestamp > AI_CACHE_TTL:
            AI_RESPONSE_CACHE.pop(key, None)
            return None
        return reply


def _set_cached_reply(cache_user_key: str, prompt: str, reply: str):
    if AI_CACHE_TTL <= 0:
        return

    now = time.time()
    key = (cache_user_key, _prompt_digest(prompt))

    with _AI_STATE_LOCK:
        expired = [
            cache_key
            for cache_key, (timestamp, _) in AI_RESPONSE_CACHE.items()
            if now - timestamp > AI_CACHE_TTL
        ]
        for cache_key in expired:
            AI_RESPONSE_CACHE.pop(cache_key, None)

        if (
            key not in AI_RESPONSE_CACHE
            and len(AI_RESPONSE_CACHE) >= AI_CACHE_MAX_ENTRIES
        ):
            oldest_key = min(
                AI_RESPONSE_CACHE,
                key=lambda cache_key: AI_RESPONSE_CACHE[cache_key][0],
            )
            AI_RESPONSE_CACHE.pop(oldest_key, None)
        AI_RESPONSE_CACHE[key] = (now, reply)


def _system_prompt(user) -> str:
    return f"""
You are NyaySetu, an Indian legal information assistant, not a lawyer.

{_language_instruction(user)}
{_tone_instruction(user)}
{_length_instruction(user)}

Rules:
- Give general Indian legal information only.
- Explain concepts, lawful processes, documents, and possible next steps.
- Do not provide a final legal opinion, predict an outcome, or invent facts or sections.
- Do not draft deceptive material or help harm someone, evade lawful authorities,
  destroy or fabricate evidence, forge documents, hack, stalk, or bribe.
- Use current criminal-law terminology: Bharatiya Nyaya Sanhita, 2023 (BNS),
  Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS), and Bharatiya Sakshya
  Adhiniyam, 2023 (BSA). Mention the legacy IPC, CrPC, or Evidence Act only
  when dates or transitional application make them relevant.
- If the applicable law, limitation period, forum, or section is uncertain,
  say that a qualified lawyer should verify it instead of guessing.
- Do not request passwords, OTPs, complete identity numbers, bank/card details,
  or unnecessary sensitive information.
- Be calm, respectful, and concise.
""".strip()


def _openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "") or CONFIG_OPENAI_API_KEY


def _local_fallback(prompt: str, user, context: str) -> str:
    from services.local_ai_service import local_ai_reply

    return local_ai_reply(scrub_pii(prompt), user, context)


def _post_openai(url: str, headers: dict, data: dict) -> httpx.Response:
    """Post with one bounded retry for connect failures or transient 5xx only."""

    max_retries = _env_int("OPENAI_HTTP_MAX_RETRIES", 1, 0, 1)
    attempt = 0
    while True:
        try:
            response = _HTTP_CLIENT.post(url, headers=headers, json=data)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            if attempt >= max_retries:
                raise OpenAIProviderError(type(exc).__name__) from exc
            attempt += 1
            continue
        except httpx.RequestError as exc:
            # A read failure may occur after a request was processed; avoid a
            # duplicate, quota-consuming call and fall back locally.
            raise OpenAIProviderError(type(exc).__name__) from exc

        if response.status_code in {500, 502, 503, 504} and attempt < max_retries:
            attempt += 1
            continue
        return response


def _configured_models() -> tuple[str, str | None]:
    """Return one primary model and at most one distinct fallback model."""

    primary = (
        os.getenv("OPENAI_MODEL", CONFIG_OPENAI_MODEL).strip()
        or CONFIG_OPENAI_MODEL
    )
    fallback = (
        os.getenv(
            "OPENAI_FALLBACK_MODEL",
            CONFIG_OPENAI_FALLBACK_MODEL,
        ).strip()
        or CONFIG_OPENAI_FALLBACK_MODEL
    )
    return primary, fallback if fallback and fallback != primary else None


def _is_model_fallback_error(response: httpx.Response) -> bool:
    """Allow a second model only when the provider identifies a model problem.

    Authentication, quota, safety, malformed-input, and transient provider
    failures are deliberately excluded. Those errors should continue through
    the existing provider router/local fallback instead of consuming a second
    model request.
    """

    if response.status_code not in _MODEL_FALLBACK_STATUSES:
        return False

    try:
        payload = response.json()
    except (TypeError, ValueError):
        return False

    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return False

    code = str(error.get("code") or "").strip().lower()
    parameter = str(error.get("param") or "").strip().lower()
    message = " ".join(str(error.get("message") or "").lower().split())

    if parameter == "model" or code in _MODEL_ERROR_CODES:
        return True
    return "model" in message and any(
        marker in message for marker in _MODEL_ERROR_MESSAGE_MARKERS
    )


def _request_data(model: str, provider_prompt: str, user, user_key: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt(user)},
            {"role": "user", "content": provider_prompt},
        ],
        "max_completion_tokens": _env_int(
            "OPENAI_MAX_TOKENS",
            240,
            80,
            800,
        ),
        "temperature": 0.2,
        "safety_identifier": user_key,
    }


def openai_reply_external(prompt: str, user, context: str = "default") -> str:
    """Call OpenAI or raise ``OpenAIProviderError`` for router fallback."""

    global AI_DISABLED_UNTIL

    if not prompt:
        return "Hi — tell me your legal question and I'll try to help."

    guarded = guardrail_response(prompt, user)
    if guarded:
        return guarded

    with _AI_STATE_LOCK:
        disabled_until = AI_DISABLED_UNTIL
    if disabled_until and _utc_now_naive() < disabled_until:
        raise OpenAIProviderError("circuit_breaker_open")

    api_key = _openai_key()
    if not api_key:
        raise OpenAIProviderError("missing_api_key")

    provider_prompt = scrub_pii(prompt)
    user_key = safety_identifier(user)

    if context != "post_payment":
        cached = _get_cached_reply(user_key, provider_prompt)
        if cached:
            logger.debug("AI_CACHE_HIT | user_ref=%s", user_key)
            return cached

    logger.info(
        "AI_CALL | provider=openai | user_ref=%s | context=%s | pii_scrubbed=%s",
        user_key,
        context,
        pii_was_scrubbed(prompt, provider_prompt),
    )

    url = os.getenv(
        "OPENAI_API_URL",
        "https://api.openai.com/v1/chat/completions",
    )
    model, fallback_model = _configured_models()
    data = _request_data(model, provider_prompt, user, user_key)
    headers = {"Authorization": f"Bearer {api_key}"}

    response = _post_openai(url, headers, data)
    if fallback_model and _is_model_fallback_error(response):
        logger.warning(
            "AI_MODEL_FALLBACK | provider=openai | user_ref=%s | status=%s",
            user_key,
            response.status_code,
        )
        data = _request_data(
            fallback_model,
            provider_prompt,
            user,
            user_key,
        )
        response = _post_openai(url, headers, data)

    if response.status_code == 429:
        with _AI_STATE_LOCK:
            AI_DISABLED_UNTIL = _utc_now_naive() + timedelta(
                minutes=_env_int("OPENAI_BREAKER_MINUTES", 30, 1, 120)
            )
        logger.warning(
            "AI_PROVIDER_RATE_LIMIT | provider=openai | user_ref=%s",
            user_key,
        )
        raise OpenAIProviderError("rate_limited")

    if response.status_code < 200 or response.status_code >= 300:
        logger.warning(
            "AI_PROVIDER_ERROR | provider=openai | user_ref=%s | status=%s",
            user_key,
            response.status_code,
        )
        raise OpenAIProviderError(f"http_{response.status_code}")

    try:
        payload = response.json()
        reply = payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise OpenAIProviderError("malformed_response") from exc

    if not reply:
        raise OpenAIProviderError("empty_response")

    reply = scrub_pii(reply)
    if context != "post_payment":
        reply += "\n\n" + _booking_cta(user)
    reply += _disclaimer_text(user)

    if context != "post_payment":
        _set_cached_reply(user_key, provider_prompt, reply)
    return reply


def ai_reply(prompt: str, user, context: str = "default"):
    """Compatibility wrapper that always returns a safe user-facing string."""

    guarded = guardrail_response(prompt, user)
    if guarded:
        return guarded

    try:
        return openai_reply_external(prompt, user, context)
    except OpenAIProviderError as exc:
        logger.warning(
            "AI_PROVIDER_FALLBACK | provider=openai | user_ref=%s | reason=%s",
            safety_identifier(user),
            str(exc),
        )
        return _local_fallback(prompt, user, context)
    except Exception as exc:
        logger.error(
            "AI_PROVIDER_FALLBACK | provider=openai | user_ref=%s | reason=%s",
            safety_identifier(user),
            type(exc).__name__,
        )
        return _local_fallback(prompt, user, context)
