# config.py
import os

# WhatsApp / Facebook Graph
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")  # Your page token
WHATSAPP_PHONE_ID = (
    os.getenv("WHATSAPP_PHONE_ID", "") or
    os.getenv("WHATSAPP_PHONE_NUMBER_ID", "") or
    os.getenv("PHONE_NUMBER_ID", "")
)
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL",
                             f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "changeme_verify_token")

# App / Admin
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "admintoken")

# OpenAI (optional; used for AI replies)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # optional for ai_reply stub
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gpt-4.1-mini")
#check why PRIMARY_MODEL required

# Razorpay keys (optional — used for webhook signature verification and real integration)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

# Booking behavior
BOOKING_PRICE = int(os.getenv("BOOKING_PRICE", "499"))  # in INR
BOOKING_CUTOFF_HOURS = int(os.getenv("BOOKING_CUTOFF_HOURS", "4"))  # minimum hours before slot
MAX_FREE_MESSAGES = int(os.getenv("MAX_FREE_MESSAGES", "20"))
TYPING_DELAY_SECONDS = float(os.getenv("TYPING_DELAY_SECONDS", "0.6"))

# Database URL (sqlite by default)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nyaysetu.db")
