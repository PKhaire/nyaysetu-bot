# NyaySetu RC11 - Email-Disabled V1 Operations

**Candidate date:** 7 September 2026  
**Schema:** unchanged at `20260903_01`  
**Release decision:** internal email is outside the first production release.

## Outcome

RC11 makes the email decision explicit and fail-safe. The Render contract sets
`EMAIL_NOTIFICATIONS_ENABLED=false`; `/health/ready` reports
`email_notifications.mode=manual_operations`; and staging/production readiness
does not require Amazon SES credentials or internal recipient lists.

This change does not disable the durable outbox. WhatsApp payment confirmation,
consultation messages, reminders when approved, optional receipt work, and
Document Studio final PDF/DOCX delivery remain active. Operators use the
authenticated appointment, support, payment-reconciliation, Document Studio,
and outbox queues plus the manual-contact procedure in
`deployment-operations.md`.

## Backlog transition

When the outbox runner starts with email disabled, it changes only these
email-only kinds to terminal `CANCELLED`:

- `booking_notification`
- `support_notification`
- `payment_reconciliation_alert`

Eligible `PENDING`, `FAILED`, and `DEAD` rows are cancelled, their payloads are
replaced with a minimal reason marker, and `outbox_cancelled` is reported.
Legacy combined payment-follow-up work skips its email step but still performs
WhatsApp and separately enabled receipt steps. Non-email `DEAD` jobs remain
critical and visible to operators.

Old `COMPLETED` and `CANCELLED` outbox rows use the existing
`OUTBOX_COMPLETED_TTL_DAYS` bounded-retention policy.

## Deployment impact

- No Alembic migration is required.
- Deploy the web service, outbox cron, and payment-reconciliation cron from the
  same RC11 commit.
- Set `EMAIL_NOTIFICATIONS_ENABLED=false` on the web service and propagate that
  value to both affected crons.
- Amazon SES/AWS email credentials and internal notification recipient lists
  are not needed by this release and are intentionally absent from
  `render.yaml`.
- Keep Document Studio S3 credentials; they are unrelated to SES and remain
  required for private generated-document storage.

## Required staging proof

1. `/health/ready` returns `200` and reports email disabled/manual operations.
2. Run `python -m jobs.process_outbox`; the legacy four email-only failures
   become `CANCELLED`, `outbox_dead=0`, and the command exits successfully if no
   unrelated delivery failure exists.
3. Confirm a consultation payment still creates/sends WhatsApp success work and
   creates no booking-email job.
4. Confirm Document Studio payment still produces and delivers final PDF/DOCX
   links through WhatsApp.
5. Confirm support intake persists in the authenticated queue without an email
   job.
6. Seed or inspect a non-email `DEAD` job and confirm the cron remains critical.
7. Complete the final integrated regression and launch checklist.

## Future email enablement

Email may be enabled only in a separate tested release with verified SES
identity/domain, production access, least-privilege IAM, configuration-set
monitoring, approved recipients, provider failure tests, and an operational
bounce/complaint procedure. Changing only the flag without that complete
configuration keeps readiness closed.
