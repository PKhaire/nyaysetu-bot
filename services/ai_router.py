import os
import logging

logger = logging.getLogger(__name__)

def ai_reply_router(message, user, context="general"):
    """
    Central AI router for NyaySetu
    Priority:
    1. Claude (free-first)
    2. OpenAI (paid)
    3. Safe fallback
    """

    # 1️⃣ Claude first
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from services.claude_service import claude_reply
            return claude_reply(message, user, context)
        except Exception as e:
            logger.warning("Claude failed: %s", e)

    # 2️⃣ OpenAI fallback
    if os.getenv("OPENAI_API_KEY"):
        try:
            from services.openai_service import ai_reply
            return ai_reply(message, user, context)
        except Exception as e:
            logger.error("OpenAI failed: %s", e)

    # 3️⃣ Hard fallback
    return (
        "⚖️ AI is temporarily unavailable.\n\n"
        "You can continue booking a consultation."
    )
