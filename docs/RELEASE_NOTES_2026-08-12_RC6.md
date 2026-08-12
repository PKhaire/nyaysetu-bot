# NyaySetu RC6 — Website Advocate Intake Routing Fix

Release date: 12 August 2026

## Outcome

Structured questions prepared by the public **Ask an Advocate** page are now
recognized by the WhatsApp backend. The request is recorded as an advocate
intake ticket and the user receives an immediate acknowledgement with a ticket
reference.

## Root cause

The website correctly opened WhatsApp with a structured intake message, but the
backend previously recognized only short commands such as `hi`, `menu`, and
`book`. A valid structured intake therefore reached the default `ignored`
branch and produced no reply.

## New behavior

- Validates the exact public-site intake contract, including approved category,
  language, timing, summary length, and limitation notice.
- Records the request with type `ADVOCATE_INTAKE` in the existing support-ticket
  table; no schema migration is required.
- Uses the selected English, Hindi, or Marathi preference for the acknowledgement.
- Queues the existing privacy-minimised operations email notification when
  support recipients are configured.
- Returns a ticket reference and clearly states that intake is not a confirmed
  booking or advocate-client relationship.
- Suppresses accidental duplicate submissions of the identical request from the
  same user for ten minutes.
- Preserves any active payment flow and does not generate automated legal advice.

## Files in the upload package

- `app.py`
- `translations.py`
- `tests/test_app_flows.py`
- `docs/RELEASE_NOTES_2026-08-12_RC6.md`

## Verification completed

- Ruff static analysis: passed.
- Dependency consistency (`pip check`): passed.
- SBOM consistency: passed.
- Focused advocate-intake tests: 3 passed.
- Application-flow suite: 17 passed.
- Full repository suite: 285 passed.
- Coverage: 64.96%, above the required 60% gate.

## Deployment and smoke test

1. Upload the four files while preserving their paths and commit to `main`.
2. Wait for NyaySetu CI to pass.
3. Trigger the Render deployment for the new commit.
4. Confirm `/health/live` and `/health/ready` return HTTP 200.
5. Submit one harmless Ask an Advocate question from the public website.
6. Confirm WhatsApp returns an `NSH-...` ticket acknowledgement.
7. Confirm one `ADVOCATE_INTAKE` item is visible in the authenticated admin
   support queue and, if enabled, one operations notification is delivered.

Do not use real identity numbers, evidence, payment credentials, or sensitive
case facts in the smoke test.
