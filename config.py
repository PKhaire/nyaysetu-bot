import os

# =========================
# 🔐 OpenAI / AI Settings
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gpt-4.1-mini")

# ------------------------------
# WhatsApp API Credentials
# ------------------------------

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "").strip()
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v19.0")

# Fix for Phone ID not loading in Render (supports ALL possible names)
WHATSAPP_PHONE_ID = (
    os.getenv("WHATSAPP_PHONE_ID")
    or os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    or os.getenv("PHONE_NUMBER_ID")
    or os.getenv("WA_PHONE_ID")
    or ""
).strip()

WHATSAPP_API_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_ID}/messages"


# ------------------------------
# Webhook Verify Token
# ------------------------------
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()


# ------------------------------
# Admin Settings
# ------------------------------
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()


# ------------------------------
# Chat Logic Settings
# ------------------------------
MAX_FREE_MESSAGES = int(os.getenv("MAX_FREE_MESSAGES", 6))
TYPING_DELAY_SECONDS = float(os.getenv("TYPING_DELAY_SECONDS", 1.2))


# ------------------------------
# Debug Logs on Startup
# ------------------------------
print("⚙️ DEBUG CONFIG VALUES — WhatsApp")
print("🔑 WHATSAPP_TOKEN:", "SET" if bool(WHATSAPP_TOKEN) else "❌ MISSING")
print("📞 WHATSAPP_PHONE_ID:", WHATSAPP_PHONE_ID if WHATSAPP_PHONE_ID else "❌ MISSING")
print("🌐 WHATSAPP_API_URL:", WHATSAPP_API_URL)
print("🔐 WHATSAPP_VERIFY_TOKEN:", "SET" if WHATSAPP_VERIFY_TOKEN else "❌ MISSING")
print("👑 ADMIN_TOKEN:", "SET" if ADMIN_TOKEN else "❌ MISSING")

if not WHATSAPP_PHONE_ID:
    print("\n🚨 ERROR: WHATSAPP_PHONE_ID is missing — messages CANNOT be sent to WhatsApp.")
    print("➡️ Fix in Render → Environment → Add variable: WHATSAPP_PHONE_ID = 813668075170472\n")
