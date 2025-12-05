import openai
from config import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY

def ai_reply(message, lang):
    system = "You are a legal advisor in India. Provide lawful general guidance, not legal representation."
    prompt = f"User language: {lang}\nUser query: {message}\nReply politely and concisely."

    res = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}]
    )
    return res.choices[0].message.content
