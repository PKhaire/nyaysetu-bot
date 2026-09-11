# NyaySetu RC19 - Phase E Staging Intake Slice

**Date:** 11 September 2026  
**Database schema:** `20260911_01` (unchanged)  
**Release status:** local candidate; staging-only and disabled by default

## Outcome

RC19 connects the approved private cheque-notice package to a controlled
WhatsApp Flow for synthetic staging intake. It does not publish the product
and it does not enable evidence upload, an advocate portal, a quote, payment,
notice creation, signing or dispatch.

## Implemented boundary

- Adds one encrypted Meta Flow endpoint and the matching Flow JSON 7.3 asset.
- Presents the existing approved 18-response schema as six shorter visual
  sections; it does not create a second legal schema or alter package hashes.
- Saves each completed section server-side and resumes from the next section.
- Validates every section and the complete confirmed snapshot on the server.
- Creates one immutable answer revision only after the final confirmation.
- Routes supported facts to `EVIDENCE_PENDING` and unsupported/uncertain facts
  to `ROUTED_OUT` before evidence, quote or payment.
- Uses a signed, expiring, order/product/schema-bound Flow token and row locking
  to reject cross-user, stale, tampered and out-of-sequence submissions.
- Uses RSA-OAEP SHA-256 and AES-GCM for the Meta data-exchange contract, with
  bounded payloads, generic client errors and no fact values in logs.
- Adds a bounded request-rate guard to the encrypted endpoint.

## Deliberate gates

- `CHEQUE_NOTICE_STAGING_UAT_ENABLED` defaults to `false`.
- The endpoint returns 404 outside `ENV=staging`.
- Staging readiness fails if the cheque product is allowlisted without the
  explicit switch, numeric Meta Flow ID and valid 2048-bit-or-stronger RSA
  private key.
- Production readiness fails if this first Phase E slice is allowlisted.
- The production Render blueprint retains the residential-only allowlist and
  leaves the Phase E switch off.
- The success screen and WhatsApp acknowledgement state that no payment is
  available and no notice has been created or issued.

## Automated evidence

- Complete local regression: 466 passed.
- Coverage: 71.60%, above the required 60% gate.
- Focused tests cover encryption round-trip/tamper rejection, the Meta send
  shape, Flow asset-to-schema alignment, six-section completion, save/resume,
  route-out, cross-user/out-of-sequence denial, staging-only HTTP behavior,
  production prohibition and no quote/payment/evidence creation.
- Ruff and Python compilation pass; the migration head remains
  `20260911_01`.

## Still blocked

Do not add the cheque product to the production allowlist. Before any real
matter, Phase E still requires Meta Flow upload/endpoint validation and mobile
UAT, a production malware scanner, private evidence-upload journey, dedicated
scoped advocate interface, advocate quote and test-payment journey, signing
and dispatch simulation, translations, security/privacy review, restore and
rollback evidence, full provider regression, and a recorded global GO
decision.
