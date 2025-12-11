# services/openai_service.py
import os, logging
from config import OPENAI_API_KEY
import httpx

logger = logging.getLogger("services.openai_service")

def ai_reply(prompt: str, user):
    """
    If OPENAI_API_KEY present, call ChatCompletion. Otherwise return a helpful canned reply.
    """
    if not prompt:
        return "Hi — tell me your legal question and I'll try to help."
    if not OPENAI_API_KEY:
        # fallback short reply
        return f"I can help with that. (AI is offline) — you said: {prompt[:200]}"
    # call OpenAI
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    data = {
        "model": "gpt-4o-mini",  # best-effort; change if you don't have access
        "messages": [{"role":"system","content":"You are a concise legal assistant. Provide short actionable advice and ask if user wants a paid consult."},
                     {"role":"user","content": prompt}],
        "max_tokens": 300,
        "temperature": 0.2,
    }
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(url, headers=headers, json=data)
            j = r.json()
            return j["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.exception("OpenAI call failed")
        return f"Sorry, I couldn't reach the AI service. ({e})"
