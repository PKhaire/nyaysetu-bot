# services/local_ai_service.py
"""
Local AI demo service for NyaySetu.

This file intentionally does not depend on OpenAI, Claude, or any paid API.
It has two modes:

1. Zero-setup local knowledge mode:
   Uses a small built-in legal FAQ/routing knowledge base.

2. Optional Ollama mode:
   If LOCAL_AI_PROVIDER=ollama is set, it calls a locally running Ollama server.
   If Ollama is not available, it safely falls back to the built-in answers.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


LEGAL_TOPICS = [
    {
        "id": "unpaid_salary",
        "title": "Unpaid salary or employment dispute",
        "keywords": [
            "salary",
            "unpaid",
            "termination",
            "fired",
            "job",
            "employer",
            "company",
            "pf",
            "gratuity",
        ],
        "answer": (
            "For unpaid salary, first collect your appointment letter, salary "
            "slips, attendance records, resignation or termination emails, bank "
            "statements, and all written communication. You can send a formal "
            "written demand to the employer. Depending on your role and state, "
            "remedies may include approaching the labour department, filing a "
            "claim under wage laws, or sending a legal notice through a lawyer."
        ),
    },
    {
        "id": "divorce_family",
        "title": "Divorce or family matter",
        "keywords": [
            "divorce",
            "maintenance",
            "alimony",
            "custody",
            "wife",
            "husband",
            "marriage",
            "family",
            "domestic violence",
        ],
        "answer": (
            "In a family matter, the next step depends on whether it is mutual "
            "divorce, contested divorce, maintenance, custody, or domestic "
            "violence. Keep marriage proof, address proof, income details, child "
            "documents if applicable, and any relevant messages or evidence. A "
            "lawyer can help choose the correct petition or response."
        ),
    },
    {
        "id": "consumer_refund",
        "title": "Consumer complaint or refund issue",
        "keywords": [
            "refund",
            "consumer",
            "product",
            "defect",
            "service",
            "delivery",
            "seller",
            "online order",
            "ecommerce",
        ],
        "answer": (
            "For a consumer refund or service issue, preserve invoice, payment "
            "proof, order details, screenshots, complaint tickets, and seller "
            "communication. First raise a written complaint with the seller or "
            "service provider. If unresolved, a consumer complaint may be filed "
            "before the appropriate consumer commission."
        ),
    },
    {
        "id": "cheque_bounce",
        "title": "Cheque bounce",
        "keywords": [
            "cheque",
            "check bounce",
            "cheque bounce",
            "ni act",
            "dishonour",
            "bank memo",
        ],
        "answer": (
            "For cheque bounce, preserve the cheque, bank return memo, invoice "
            "or loan proof, and communication with the drawer. In many cases, a "
            "statutory notice must be sent within the legal timeline after the "
            "bank return memo. A lawyer should verify dates before any action."
        ),
    },
    {
        "id": "cyber_fraud",
        "title": "Cyber fraud or online scam",
        "keywords": [
            "cyber",
            "fraud",
            "scam",
            "upi",
            "otp",
            "bank transfer",
            "unauthorized",
            "online fraud",
        ],
        "answer": (
            "For cyber fraud, act quickly. Save transaction IDs, screenshots, "
            "phone numbers, links, account details, and chat history. Inform your "
            "bank immediately and request blocking or reversal if possible. You "
            "can also report the incident on the national cybercrime portal or "
            "with the cyber police station."
        ),
    },
    {
        "id": "property_dispute",
        "title": "Property dispute",
        "keywords": [
            "property",
            "land",
            "flat",
            "builder",
            "possession",
            "sale deed",
            "partition",
            "tenant",
            "rent",
        ],
        "answer": (
            "For a property dispute, collect title documents, sale deed, property "
            "tax records, possession proof, agreement copies, payment records, "
            "and any notices. The correct action may be a legal notice, civil "
            "suit, injunction, consumer complaint against builder, or tenancy "
            "proceeding depending on facts."
        ),
    },
    {
        "id": "police_case",
        "title": "Police case or criminal matter",
        "keywords": [
            "police",
            "fir",
            "bail",
            "arrest",
            "criminal",
            "false case",
            "notice",
            "summons",
        ],
        "answer": (
            "For a police or criminal matter, do not ignore any notice or summons. "
            "Preserve copies of FIR, notice, complaint, call records, messages, "
            "and identity documents. Avoid making detailed statements without "
            "legal guidance. A lawyer can assess bail, anticipatory bail, or "
            "response strategy."
        ),
    },
]


DISCLAIMER = {
    "en": (
        "Disclaimer: This is general legal information, not final legal advice. "
        "Please consult a qualified lawyer for advice on your specific facts."
    ),
    "hi": (
        "Disclaimer: Yeh general legal information hai, final legal advice nahi. "
        "Apne specific case ke liye qualified lawyer se consult karein."
    ),
}


BOOKING_CTA = {
    "en": "If you want personalised guidance, you can book a lawyer consultation.",
    "hi": "Agar aapko personalised guidance chahiye, lawyer consultation book kar sakte hain.",
}


def _language(user: Any) -> str:
    raw = getattr(user, "language", "en") if user else "en"
    return "hi" if raw in ("hi", "Hindi", "Hinglish") else "en"


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()


def _find_topic(message: str) -> Optional[Dict[str, Any]]:
    normalized = _normalize(message)
    best_topic = None
    best_score = 0

    for topic in LEGAL_TOPICS:
        score = 0
        for keyword in topic["keywords"]:
            if keyword in normalized:
                score += len(keyword.split()) + 1

        if score > best_score:
            best_score = score
            best_topic = topic

    return best_topic


def _fallback_reply(message: str, user: Any, context: str) -> str:
    lang = _language(user)
    topic = _find_topic(message)

    if topic:
        answer = f"{topic['title']}\n\n{topic['answer']}"
    else:
        answer = (
            "I can help with general legal information for common Indian legal "
            "issues such as family matters, police cases, property disputes, "
            "job issues, consumer complaints, cheque bounce, and cyber fraud. "
            "Please share the issue, city/district, and what has happened so far."
        )

    parts = [answer, DISCLAIMER.get(lang, DISCLAIMER["en"])]

    if context != "post_payment":
        parts.append(BOOKING_CTA.get(lang, BOOKING_CTA["en"]))

    return "\n\n".join(parts)


def _ollama_reply(message: str, user: Any, context: str) -> Optional[str]:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    topic = _find_topic(message)
    knowledge = topic["answer"] if topic else "No exact local FAQ match found."
    lang = _language(user)

    prompt = f"""
You are NyaySetu, an Indian legal information assistant.

Rules:
- Give general legal information only.
- Do not give final legal advice.
- Do not predict case outcomes.
- Do not draft legal notices.
- Ask the user to consult a qualified lawyer for case-specific advice.
- Keep the answer under 180 words.

User language: {lang}
Context: {context}

Local legal knowledge:
{knowledge}

User question:
{message}
""".strip()

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 220,
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

    parts = [reply, DISCLAIMER.get(lang, DISCLAIMER["en"])]
    if context != "post_payment":
        parts.append(BOOKING_CTA.get(lang, BOOKING_CTA["en"]))

    return "\n\n".join(parts)


def local_ai_reply(message: str, user: Any = None, context: str = "general") -> str:
    if not message or not message.strip():
        return "Please share your legal question in one or two lines."

    provider = os.getenv("LOCAL_AI_PROVIDER", "").lower().strip()

    if provider == "ollama":
        reply = _ollama_reply(message, user, context)
        if reply:
            return reply

    return _fallback_reply(message, user, context)
