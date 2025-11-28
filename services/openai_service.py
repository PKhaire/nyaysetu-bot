# services/openai_service.py
import time
import logging
from openai import OpenAI, RateLimitError, APIError, BadRequestError
from config import OPENAI_API_KEY, PRIMARY_MODEL

client = OpenAI(api_key=OPENAI_API_KEY)

def call_openai_chat(messages, model=PRIMARY_MODEL, max_tokens=300, temperature=0.2):
    backoff = 1.0
    for attempt in range(5):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return resp.choices[0].message.content
        except RateLimitError as e:
            logging.warning("OpenAI rate limited, retrying: %s", e)
            time.sleep(backoff)
            backoff *= 2
        except (BadRequestError, APIError) as e:
            logging.error("OpenAI API error: %s", e)
            break
        except Exception as e:
            logging.error("OpenAI unexpected error: %s", e)
            time.sleep(backoff)
            backoff *= 2
    return None

def detect_language(text):
    prompt = f"Detect the language of the following text and return only the language name (e.g., English, Hindi, Marathi):\n\n\"{text}\"\n"
    res = call_openai_chat([{"role": "user", "content": prompt}], max_tokens=20)
    return (res or "English").strip()

def detect_category(text):
    prompt = (
        "Classify this message into one word: property, police, family, business, money, other.\n"
        f"Message: {text}\nReturn only the category."
    )
    res = call_openai_chat([{"role": "user", "content": prompt}], max_tokens=10)
    return (res or "other").strip().lower()

def generate_legal_reply(text, language="English", category="other"):
    system_prompt = (
        "You are a professional legal assistant. Provide a concise, practical legal reply in 2-3 short sentences. "
        "If the question requires a lawyer, recommend booking. Keep tone polite and trustworthy."
    )
    user_msg = f"Language: {language}\nCategory: {category}\nUser: {text}"
    res = call_openai_chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg}
    ], max_tokens=180)
    return res or "Sorry, I'm unable to prepare a response right now. Please try again later."
