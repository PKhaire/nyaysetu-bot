import os

# 🔹 WhatsApp Credentials
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")

# 💡 Fixed API URL format for Meta Cloud
WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"

# 🔹 AI / OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gpt-4o-mini")

# 🔹 Admin Dashboard / Security
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "DEFAULT_ADMIN_TOKEN")

# 🔹 Bot Settings
MAX_FREE_MESSAGES = int(os.getenv("MAX_FREE_MESSAGES", 5))
TYPING_DELAY_SECONDS = float(os.getenv("TYPING_DELAY_SECONDS", 1.2))

# 🔹 Payments
PAYMENT_BASE_URL = os.getenv("PAYMENT_BASE_URL", "https://payment.yourapp.in/pay")
