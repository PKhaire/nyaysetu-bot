# config.py
import os

#Prevents booking/payment data loss on server restart.
ENV = os.getenv("ENV", "production")
# ===============================
# MAINTENANCE MODE
# ===============================
MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
MAINTENANCE_ADMIN_BYPASS = os.getenv("MAINTENANCE_ADMIN_BYPASS", "")

BOOKING_NOTIFICATION_EMAILS = [
    "outsidethecourt@gmail.com",
    "nyaysetu@gmail.com",
]

# WhatsApp / Facebook config
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
# choose phone id env checking multiple names
WHATSAPP_PHONE_ID = (
    os.getenv("WHATSAPP_PHONE_ID", "") or
    os.getenv("WHATSAPP_PHONE_NUMBER_ID", "") or
    os.getenv("PHONE_NUMBER_ID", "")
)
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v24.0")

WHATSAPP_API_URL = (
    f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_ID}/messages"
    if WHATSAPP_PHONE_ID
    else ""
)

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Razorpay (optional) — set both to enable real payments
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

# Booking / business settings
BOOKING_PRICE = int(os.getenv("BOOKING_PRICE", "499"))
BOOKING_CUTOFF_HOURS = float(os.getenv("BOOKING_CUTOFF_HOURS", "2"))  # no booking within N hours of slot start
BOOKING_MAX_AHEAD_DAYS = int(os.getenv("BOOKING_MAX_AHEAD_DAYS", "30"))
BOOKING_MAX_PER_DAY = int(os.getenv("BOOKING_MAX_PER_DAY", "8"))  # optional capacity per day

# Admin
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# Database url (SQLAlchemy)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nyaysetu.db")
