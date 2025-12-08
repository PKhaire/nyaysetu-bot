import os

# =========================
# 🔐 OpenAI / AI Settings
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gpt-4.1-mini")

# =========================
# 💬 WhatsApp Settings
# =========================
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

# We support either:
#   WHATSAPP_PHONE_NUMBER_ID  (recommended)
#   PHONE_NUMBER_ID           (fallback, matches Meta dashboard wording)
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("PHONE_NUMBER_ID")

if not WHATSAPP_PHONE_NUMBER_ID:
    # Fail fast so you immediately see the problem in logs
    raise RuntimeError(
        "WhatsApp phone number ID is not set. "
        "Please add WHATSAPP_PHONE_NUMBER_ID (or PHONE_NUMBER_ID) in Render env."
    )

WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

# =========================
# 👤 App Behaviour
# =========================
MAX_FREE_MESSAGES = int(os.getenv("MAX_FREE_MESSAGES", "6"))
TYPING_DELAY_SECONDS = float(os.getenv("TYPING_DELAY_SECONDS", "1.5"))

# Admin token for protected actions (/webhook?admin_token=...)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# =========================
# 💳 Payments (Razorpay)
# =========================
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

# Optional: base URL (if you ever need it)
BASE_URL = os.getenv("BASE_URL", "https://api.nyaysetu.in")
