# NyaySetu RC7 — Conversation UX Hardening

Date: 13 August 2026

## User-facing improvements

- Typed booking requests and typed legal questions now work at the initial
  “Ask a Legal Question / Book Consultation” choice.
- Unknown messages receive a helpful recovery response and Home menu instead
  of appearing unanswered.
- Edited or outdated Ask an Advocate messages receive safe retry instructions;
  malformed legal intake is still never stored.
- Invalid and stale date/time selections redisplay the correct picker.
- Restart immediately returns the user to Home.
- List action buttons and consultation ratings are localized for English,
  Hindi/Hinglish, and Marathi.

## Reliability fixes

- All booking subcategory lists now remain within WhatsApp's ten-row limit.
- Incomplete paid-booking data produces a safe support path rather than a
  silent response.
- Delivery/read callbacks remain provider acknowledgements and do not generate
  unnecessary user messages.

## Changed files

- `app.py`
- `translations.py`
- `services/whatsapp_service.py`
- `tests/test_app_flows.py`
- `tests/test_whatsapp_service.py`
- `docs/NYAYSETU_BOT_UX_ARCHITECTURE_AUDIT_2026-08-13.md`
- `docs/RELEASE_NOTES_2026-08-13_RC7.md`

## Verification

- `pytest -q`: 289 passed
- Focused UX/transport/translation tests: 34 passed
- `ruff check`: passed
- `compileall`: passed

No schema migration is required for RC7.
