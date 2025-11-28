# config.py
import os

# OpenAI / WhatsApp / DB config (set env variables)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PRIMARY_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "verify_token_demo")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///nyaysetu.db")

# Booking & payment
PAYMENT_BASE_URL = os.getenv("PAYMENT_BASE_URL", "https://your-payments.example/checkout")
MAX_FREE_MESSAGES = int(os.getenv("MAX_FREE_MESSAGES", 5))
TYPING_DELAY_SECONDS = float(os.getenv("TYPING_DELAY_SECONDS", 1.0))

# Admin
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "adminpass")
