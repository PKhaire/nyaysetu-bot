# services/openai_service.py
import logging
from config import OPENAI_API_KEY
import httpx

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


# =================================================
# MAIN AI FUNCTION (FLOW UNCHANGED)
# =================================================

def ai_reply(prompt: str, user):
    """
    If OPENAI_API_KEY present, call ChatCompletion.
    Otherwise return a helpful canned reply.
    """
    if not prompt:
        return "Hi — tell me your legal question and I'll try to help."

    # 🔒 Offline fallback (UNCHANGED)
    if not OPENAI_API_KEY:
        return f"I can help with that. (AI is offline) — you said: {prompt[:200]}"

    # 🧠 SYSTEM PROMPT (ENHANCED, SAFE)
    system_prompt = f"""
You are NyaySetu, an Indian legal assistant.

{_language_instruction(user)}
{_tone_instruction(user)}
{_length_instruction(user)}

Rules:
- Indian legal context only
- Do not give illegal advice
- Be clear and calm
- Do NOT scare the user
"""

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 300,
        "temperature": 0.2,
    }

    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(url, headers=headers, json=data)
            j = r.json()

            reply = j["choices"][0]["message"]["content"].strip()

            # ✅ Append CTA + Disclaimer (SAFE)
            reply += "\n\n" + _booking_cta(user)
            reply += _disclaimer_text(user)

            return reply

    except Exception as e:
        logger.exception("OpenAI call failed")
        return f"Sorry, I couldn't reach the AI service. ({e})"
