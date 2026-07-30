"""Configurable, privacy-preserving AI provider router."""

from __future__ import annotations

import logging
import os

from services.ai_safety import guardrail_response, safety_identifier, scrub_pii


logger = logging.getLogger("services.ai_router")

_SUPPORTED_PROVIDERS = {"claude", "openai", "local"}


def _provider_order():
    selected = os.getenv("AI_PROVIDER", "auto").strip().lower()
    if selected in {"anthropic", "claude"}:
        return ["claude", "local"]
    if selected in {"openai"}:
        return ["openai", "local"]
    if selected in {"local", "offline", "none"}:
        return ["local"]

    configured = os.getenv(
        "AI_PROVIDER_ORDER",
        "claude,openai,local",
    )
    order = []
    for raw_provider in configured.split(","):
        provider = raw_provider.strip().lower()
        if provider == "anthropic":
            provider = "claude"
        if provider in _SUPPORTED_PROVIDERS and provider not in order:
            order.append(provider)
    if "local" not in order:
        order.append("local")
    return order


def _local_reply(message, user, context):
    from services.local_ai_service import local_ai_reply

    # LOCAL_AI_PROVIDER may point to an Ollama host, so redact before this
    # boundary as well.
    return local_ai_reply(scrub_pii(message), user, context)


def ai_reply_router(message, user, context="general"):
    """Return a safe answer from the configured provider or local knowledge."""

    guarded = guardrail_response(message, user)
    if guarded:
        return guarded

    user_ref = safety_identifier(user)
    for provider in _provider_order():
        if provider == "local":
            return _local_reply(message, user, context)

        if provider == "claude":
            if not os.getenv("ANTHROPIC_API_KEY"):
                continue
            try:
                from services.claude_service import claude_reply_external

                return claude_reply_external(message, user, context)
            except Exception as exc:
                reason = (
                    str(exc)
                    if exc.__class__.__name__ == "ClaudeProviderError"
                    else type(exc).__name__
                )
                logger.warning(
                    "AI_PROVIDER_FAILED | provider=claude | user_ref=%s | reason=%s",
                    user_ref,
                    reason,
                )
                continue

        if provider == "openai":
            if not os.getenv("OPENAI_API_KEY"):
                continue
            try:
                from services.openai_service import openai_reply_external

                return openai_reply_external(message, user, context)
            except Exception as exc:
                reason = (
                    str(exc)
                    if exc.__class__.__name__ == "OpenAIProviderError"
                    else type(exc).__name__
                )
                logger.warning(
                    "AI_PROVIDER_FAILED | provider=openai | user_ref=%s | reason=%s",
                    user_ref,
                    reason,
                )
                continue

    # Defensive fallback if an invalid provider order somehow becomes empty.
    return _local_reply(message, user, context)
