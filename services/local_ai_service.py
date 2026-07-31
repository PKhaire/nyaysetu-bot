"""Deterministic local legal guidance with an optional Ollama enhancement.

The default path does not call any third-party AI service. It routes a question
to versioned, lawyer-reviewable guidance in English, Hinglish, or Marathi.
Ollama is optional; any failure falls back to the same deterministic guide.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from services.legal_knowledge import (
    find_guide,
    guide_message,
    language_code,
    ui,
)


def _fallback_reply(message: str, user: Any, context: str) -> str:
    category, subcategory = find_guide(message)
    answer = guide_message(
        user,
        category,
        subcategory,
        include_feedback_prompt=False,
    )
    if context != "post_payment":
        answer += (
            "\n\n"
            + {
                "en": "For advice on your facts, you can book a lawyer consultation.",
                "hi": "Apne specific facts par advice ke liye lawyer consultation book kar sakte hain.",
                "mr": "आपल्या विशिष्ट तथ्यांवरील सल्ल्यासाठी वकिलांची सल्लामसलत बुक करू शकता.",
            }[language_code(user)]
        )
    return answer


def _ollama_reply(message: str, user: Any, context: str) -> Optional[str]:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    category, subcategory = find_guide(message)
    knowledge = guide_message(
        user,
        category,
        subcategory,
        include_feedback_prompt=False,
    )
    lang = language_code(user)

    prompt = f"""
You are NyaySetu, an Indian legal information assistant.

Rules:
- Use only the reviewed local guidance below.
- Give general legal information, never personalised legal advice.
- Do not invent statutes, limitation periods, authorities, addresses, or outcomes.
- Do not predict a case outcome or draft a legal notice.
- Preserve the safety escalation and disclaimer.
- If the guidance is insufficient, say so and recommend a qualified lawyer.
- Keep the answer under 220 words.

User language: {lang}
Context: {context}

Reviewed local guidance:
{knowledge}

User question:
{message}
""".strip()

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 280,
        },
    }
    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    reply = (data.get("response") or "").strip()
    if not reply:
        return None

    reply += f"\n\n⚠️ {ui(user, 'disclaimer')}"
    if context != "post_payment":
        reply += (
            "\n\n"
            + {
                "en": "For advice on your facts, you can book a lawyer consultation.",
                "hi": "Apne specific facts par advice ke liye lawyer consultation book kar sakte hain.",
                "mr": "आपल्या विशिष्ट तथ्यांवरील सल्ल्यासाठी वकिलांची सल्लामसलत बुक करू शकता.",
            }[lang]
        )
    return reply


def local_ai_reply(
    message: str,
    user: Any = None,
    context: str = "general",
) -> str:
    if not message or not message.strip():
        return {
            "en": "Please share your legal question in one or two lines.",
            "hi": "Apna legal question ek ya do lines mein batayein.",
            "mr": "आपला कायदेशीर प्रश्न एक किंवा दोन ओळींत सांगा.",
        }[language_code(user)]

    if os.getenv("LOCAL_AI_PROVIDER", "").lower().strip() == "ollama":
        reply = _ollama_reply(message, user, context)
        if reply:
            return reply

    return _fallback_reply(message, user, context)
