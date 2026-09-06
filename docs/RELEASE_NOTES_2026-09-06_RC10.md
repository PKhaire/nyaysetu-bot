# NyaySetu RC10 - Document Studio Operations Hardening

**Candidate date:** 6 September 2026  
**Schema:** unchanged at `20260903_01`  
**Release status:** implementation complete; staging evidence and the integrated
production checklist remain mandatory.

## Outcome

RC10 closes the code-level gap between a successful Document Studio payment
and staffed production operations. The existing consultation reconciliation
cron now also runs an isolated Document Studio scan. Only current, exact
Razorpay Payment Link and Payment evidence can recover a final PDF/DOCX release.
Unpaid links are unchanged; partial, mismatched, malformed, or ambiguous
evidence grants no entitlement and remains in `NEEDS_ATTENTION`.

Final WhatsApp delivery is now a durable outbox side effect. The committed job
contains only the document-order database ID. Fresh presigned PDF/DOCX URLs are
created in memory at delivery time, never stored in the database or logs, and
the order ID is scrubbed from the job after Meta accepts the message.

## Operator controls

All mutations require existing admin authentication, a valid `X-Operator-ID`,
and the normal CSRF control for browser sessions.

| Route | Purpose |
|---|---|
| `GET /admin/document-orders/<ref>` | Inspect privacy-safe state and recent audit events |
| `POST /admin/document-orders/<ref>/reconcile` | Re-fetch Razorpay evidence and recover one exact capture |
| `POST /admin/document-orders/<ref>/refund-review` | Record the explicit decision to stop release and pursue a manual refund |
| `POST /admin/document-orders/<ref>/redeliver` | Queue fresh links with a reason and caller idempotency key |

The application does not execute a Razorpay refund. An operator performs the
refund in Razorpay; the reconciler changes `REFUND_REVIEW` to `REFUNDED` only
after current evidence shows the exact full amount and `refund_status=full`.

## Scheduled behavior

`python -m jobs.reconcile_payments --limit 100` now prints separate
`consultations` and `document_studio` results. One scan can report failure
without preventing the other from running. Exit `2` covers provider,
configuration, or document final-release failures; human-review results alone
do not make the cron fail.

## Deployment impact

- No new environment-variable values. The outbox and payment-reconciliation
  cron services must inherit the existing Document Studio S3 settings; the
  reconciler must also inherit the existing price/final-retention settings.
- No Alembic migration; schema remains `20260903_01`.
- The existing five-minute reconciliation cron command is unchanged.
- The existing outbox cron processes the new `document_final_delivery` kind.
- Web and both affected cron services must deploy the same Git SHA.

## Required staging proof before regression sign-off

1. Miss one test webhook and confirm the reconciliation cron releases exactly
   one final entitlement and one delivery job.
2. Supply unpaid and mismatched test evidence and confirm no entitlement.
3. Force WhatsApp failure, then confirm outbox retry and terminal payload
   scrubbing without a stored signed URL.
4. Use admin redelivery twice with the same idempotency key and confirm one job.
5. Record refund review, complete a full Razorpay test refund, and confirm state
   becomes `REFUNDED` only after provider verification.
6. Confirm `/health/ready` remains `200` and run the complete regression suite.
