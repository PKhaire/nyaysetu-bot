# Local AI Demo

This demo shows how NyaySetu can answer legal questions without OpenAI or Claude.

The demo has two modes:

1. Zero-setup mode:
   - No API keys.
   - No external AI service.
   - Uses a small local legal knowledge base inside
     `services/local_ai_service.py`.

2. Optional Ollama mode:
   - Runs a local open-source model on your machine or server.
   - Still no OpenAI or Claude key.
   - Uses `http://localhost:11434/api/generate`.

## Run Zero-Setup Demo

From the project folder:

```powershell
python -m demo_local_ai
```

Ask one custom question:

```powershell
python -m demo_local_ai "My employer terminated me and did not pay salary"
```

## Optional Ollama Demo

Install Ollama and pull a model:

```powershell
ollama pull llama3.1:8b
```

Run Ollama, then set:

```powershell
$env:LOCAL_AI_PROVIDER="ollama"
$env:OLLAMA_MODEL="llama3.1:8b"
python -m demo_local_ai
```

If Ollama is not running, the demo safely falls back to local knowledge answers.

## How This Fits WhatsApp

Current live AI path:

```text
WhatsApp user
-> /webhook
-> ai_reply_router()
-> Claude/OpenAI
-> WhatsApp reply
```

Future local AI path:

```text
WhatsApp user
-> /webhook
-> ai_reply_router()
-> local_ai_reply()
-> local knowledge base or local Ollama model
-> WhatsApp reply
```

## What This Removes

The future production change can remove dependency on:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- OpenAI API billing
- Claude API billing

## What It Does Not Remove

If the bot remains on WhatsApp, you still need:

- `WHATSAPP_TOKEN`
- `WHATSAPP_PHONE_ID`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_APP_SECRET`

Those are required because WhatsApp messages must pass through Meta's WhatsApp
Business Platform.

## Production Recommendation

For the client, do not rely only on a raw model. Use:

```text
Local legal knowledge base
+ local LLM
+ strict legal disclaimer
+ lawyer consultation CTA
```

That gives better control, lower cost, and safer legal answers.
