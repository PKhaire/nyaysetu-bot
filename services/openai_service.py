# services/openai_service.py
import logging
import httpx
import time
from typing import Dict, Tuple
from config import OPENAI_API_KEY


logger = logging.getLogger("services.openai_service")

# =================================================
# ADMIN CONTROLS (SAFE TO EDIT WITHOUT LOGIC CHANGE)
# =================================================

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

# =================================================
# AI RESPONSE CACHE (PER-USER, SHORT-LIVED)
# =================================================

# key: (wa_id, normalized_prompt)
# value: (timestamp, reply)
AI_RESPONSE_CACHE: Dict[Tuple[str, str], Tuple[float, str]] = {}

AI_CACHE_TTL = 20  # seconds (safe: 10–30)

# =================================================
# LANGUAGE BEHAVIOR CONTROLS
# =================================================

def _tone_instruction(user):
    """
    Controls FORMAL / FRIENDLY tone per language
    """
    lang = getattr(user, "language", "en")

    if lang == "hi":
        return "Use a friendly, supportive Hinglish tone."
    if lang == "mr":
        return "Use a polite and respectful Marathi tone."
    return "Use a professional and formal English tone."


def _length_instruction(user):
    """
    Controls response length per language
    """
    lang = getattr(user, "language", "en")

    if lang == "hi":
        return "Keep the response medium length and conversational."
    if lang == "mr":
        return "Explain clearly with moderate detail."
    return "Keep the response concise and to the point."


def _language_instruction(user):
    """
    Controls output language
    """
    lang = getattr(user, "language", "en")

    if lang == "hi":
        return "Reply in simple Hinglish (Hindi + English mix)."
    if lang == "mr":
        return "Reply in simple Marathi language."
    return "Reply in clear English."


def _disclaimer_text(user):
    lang = getattr(user, "language", "en")
    return ADMIN_DISCLAIMERS.get(lang, ADMIN_DISCLAIMERS["en"])


def _booking_cta(user):
    lang = getattr(user, "language", "en")
    return BOOKING_CTA.get(lang, BOOKING_CTA["en"])
    
def _normalize_prompt(prompt: str) -> str:
    """
    Normalize prompt to avoid cache misses due to spacing/case
    """
    return " ".join(prompt.lower().strip().split())

def _get_cached_reply(wa_id: str, prompt: str):
    key = (wa_id, _normalize_prompt(prompt))
    cached = AI_RESPONSE_CACHE.get(key)

    if not cached:
        return None

    ts, reply = cached
    if time.time() - ts > AI_CACHE_TTL:
        # expired
        AI_RESPONSE_CACHE.pop(key, None)
        return None

    return reply

def _set_cached_reply(wa_id: str, prompt: str, reply: str):
    now = time.time()
    key = (wa_id, _normalize_prompt(prompt))

    # Lazy cleanup (O(n), safe for small cache)
    expired = [
        k for k, (ts, _) in AI_RESPONSE_CACHE.items()
        if now - ts > AI_CACHE_TTL
    ]
    for k in expired:
        AI_RESPONSE_CACHE.pop(k, None)

    AI_RESPONSE_CACHE[key] = (now, reply)

# =================================================
# MAIN AI FUNCTION (FLOW UNCHANGED)
# =================================================

def ai_reply(prompt: str, user, context: str = "default"):
    """
    AI reply handler.
    - Respects user language
    - Safe before & after payment
    - No re-booking CTA after payment
    """

    if not prompt:
        return "Hi — tell me your legal question and I'll try to help."

    # 🔒 Per-user short-term cache (protects OpenAI & UX)
    wa_id = getattr(user, "whatsapp_id", None)
    
    cached = None
    if wa_id and context != "post_payment":
        cached = _get_cached_reply(wa_id, prompt)
        if cached:
            logger.debug("AI_CACHE_HIT | wa_id=%s", wa_id)
            return cached
    
    # 📊 OBSERVABILITY LOG (ADD HERE)
    logger.info(
        "AI_CALL | wa_id=%s | cached=%s | context=%s",
        wa_id,
        bool(cached),
        context,
    )

           
    # 🔒 Offline fallback (UNCHANGED)
    if not OPENAI_API_KEY:
        return f"I can help with that. (AI is offline) — you said: {prompt[:200]}"

    # 🧠 SYSTEM PROMPT (SAFE & CONTROLLED)
    system_prompt = f"""
You are NyaySetu, an Indian legal assistant.

{_language_instruction(user)}
{_tone_instruction(user)}
{_length_instruction(user)}

Rules:
- Indian legal context only
- Explain concepts, process, documents, timelines
- Do NOT give final legal advice
- Do NOT predict case outcomes
- Do NOT draft legal notices
- Be calm, respectful, and helpful
- Always remind that final advice will be given by a lawyer
"""

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 200,
        "temperature": 0.2,
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            r = client.post(url, headers=headers, json=data)
        
            # 🔁 Retry ONCE with fallback model if rate-limited
            if r.status_code == 429:
                # Paid users keep premium model, free users downgrade
                fallback_model = "gpt-3.5-turbo"
                if context == "post_payment":
                    fallback_model = "gpt-4o-mini"
            
                logger.warning(
                    "OpenAI rate-limited (429). Retrying with %s | wa_id=%s | context=%s",
                    fallback_model,
                    wa_id,
                    context,
                )
            
                fallback_data = data.copy()
                fallback_data["model"] = fallback_model
            
                r = client.post(url, headers=headers, json=fallback_data)

        
            # 🔒 HARD GUARD — still failing
            if r.status_code != 200:
                logger.error(
                    "OpenAI error | status=%s | response=%s",
                    r.status_code,
                    r.text,
                )
                raise RuntimeError("OpenAI API error")

        
            j = r.json()
        
            # 🔒 HARD GUARD — malformed response
            if "choices" not in j or not j["choices"]:
                logger.error("OpenAI malformed response: %s", j)
                raise RuntimeError("Invalid OpenAI response")
        
            reply = j["choices"][0]["message"]["content"].strip()


            # -------------------------------------------------
            # POST-PROCESSING (CRITICAL LOGIC)
            # -------------------------------------------------

            # ✅ BEFORE payment → allow booking CTA
            if context != "post_payment":
                reply += "\n\n" + _booking_cta(user)

            # ✅ ALWAYS show legal disclaimer
            reply += _disclaimer_text(user)

            # 💾 Cache reply for short duration (SUCCESS ONLY)
            if wa_id:
                _set_cached_reply(wa_id, prompt, reply)
            
            return reply


    except Exception as e:
        logger.exception("OpenAI call failed: %s", str(e))
        return "Sorry, I couldn't reach the AI service right now. Please try again later."


