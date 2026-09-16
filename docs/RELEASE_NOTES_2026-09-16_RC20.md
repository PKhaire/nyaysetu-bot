# NyaySetu RC20 - First-release Customer Beta Boundary

**Date:** 16 September 2026  
**Database schema:** `20260911_01` (unchanged)  
**Release status:** local candidate; production configuration required

## Outcome

RC20 keeps Booking Consultation as the only live paid customer service while
making the residential Draft Studio and Cheque-bounce Notice questionnaires
available for controlled real-user beta feedback.

## Enforced boundary

- New document orders are durably stamped `BETA` and carry no price.
- Residential beta completion stops before preview, payment and artifact
  generation.
- Cheque beta completion stops at `BETA_COMPLETE`, before evidence handling,
  advocate triage, quote, payment, notice creation, signing or dispatch.
- Preview, payment-request and verified-payment fulfillment interfaces reject
  beta orders even if called outside the WhatsApp journey.
- Existing pre-beta commercial drafts are abandoned rather than silently
  resumed after the release-mode change.
- Beta answer revisions are redacted under the existing unpaid-draft retention
  schedule.
- WhatsApp catalogue, selection, help, launch and completion messages repeat
  the beta/non-commercial boundary and direct legal needs to Book Consultation.

## Production activation contract

- `DOCUMENT_STUDIO_CUSTOMER_MODE=beta`
- Both beta product codes are present in the global product allowlist.
- `CHEQUE_NOTICE_STAGING_UAT_ENABLED=false` in production.
- The cheque Meta Flow is uploaded from the RC20 JSON, published, attached to
  the configured endpoint and backed by the matching private key.
- Production readiness rejects an allowlisted cheque beta unless the Flow ID
  is numeric, mode is `published` and the private key is valid.

## Automated evidence

- Complete local regression: 485 passed.
- Coverage: 72.00%, above the required 60% gate.
- Ruff, JSON parsing and diff whitespace checks pass.
