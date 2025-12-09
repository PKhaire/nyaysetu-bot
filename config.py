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

# Accept both naming styles from Render / Meta
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "").strip() 

print("DEBUG WHATSAPP_PHONE_ID =", repr(WHATSAPP_PHONE_ID))

WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"

# =========================
# ⚙ Bot Behaviour
# =========================
MAX_FREE_MESSAGES = int(os.getenv("MAX_FREE_MESSAGES", "6"))
TYPING_DELAY_SECONDS = float(os.getenv("TYPING_DELAY_SECONDS", "1.5"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# =========================
# 💳 Razorpay
# =========================
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
