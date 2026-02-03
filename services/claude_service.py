import os
from anthropic import Anthropic
import logging

logger = logging.getLogger(__name__)

client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

SYSTEM_PROMPT = """
You are NyaySetu, an Indian legal information assistant.

Rules:
- Provide general legal information only
- Do not guarantee outcomes
- Do not encourage illegal actions
- Prefer Indian laws (IPC, CrPC, CPC, NI Act)
- Always add a legal disclaimer
"""

def claude_reply(message, user, context="general"):
    if not message:
        return "Please ask a legal question."

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=400,
        temperature=0.3,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": message}
        ],
    )

    answer = response.content[0].text.strip()

    return (
        answer +
        "\n\n⚠️ Disclaimer: This is general legal information, "
        "not legal advice. Consult a lawyer."
    )
