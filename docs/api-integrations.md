# API and Integration Specification

This document describes the interfaces implemented in the current code. It
does not imply that provider credentials, templates, webhooks, or production
data migration have been completed in any environment.

## Inbound HTTP API

### Service and health

| Route | Purpose | Success |
|---|---|---|
| `GET /` | Non-sensitive service metadata | `200` |
| `GET /health/live` | Process liveness only | `200` |
| `GET /health/ready` | Database query, production database type, and required configuration | `200`; otherwise `503` |

Readiness checks the database and expected Alembic revision and, when
`ENV=production`, rejects SQLite/automatic schema creation and validates
WhatsApp, live Razorpay, Amazon SES/recipient, support/privacy, HTTPS policy,
admin/AI-secret, and legal-review-date configuration. It enforces the current
credential contract, including 32-character WhatsApp app-secret/token and
admin/AI minimums, 16-character WhatsApp-verify and Razorpay key/secret
minimums, an `rzp_live_...` key ID, and valid SES region/from-address and AWS
credential settings (access-key ID 16 or more characters, secret access key 32
or more, and optional session token 16 or more). If present, the previous Meta
app secret must meet the 32-character minimum and the previous Razorpay webhook
secret the 16-character minimum. It does not call any external provider and
does not prove policy/legal approval.

### `GET /webhook`

Meta webhook verification uses `hub.verify_token` and returns
`hub.challenge` only when the token matches `WHATSAPP_VERIFY_TOKEN` using a
constant-time comparison. A mismatch returns `403`.

### `POST /webhook`

This is the inbound WhatsApp Cloud API webhook.

Implemented controls:

- Verifies `X-Hub-Signature-256` over the raw request body using
  `WHATSAPP_APP_SECRET` or, during a bounded rotation,
  `WHATSAPP_APP_SECRET_PREVIOUS`.
- Allows signature bypass only when `ALLOW_INSECURE_WEBHOOKS=true` and the
  environment is not production.
- Rejects bodies larger than `WEBHOOK_MAX_PAYLOAD_BYTES`.
- Safely flattens Meta `entry/change/messages` batches.
- Claims each Meta message ID in `inbound_message_events` with a bounded
  processing lease. `DONE` suppresses duplicates, an unexpired `PROCESSING`
  lease returns `503`, and an expired/failed lease can be reclaimed after a
  process crash.
- Marks an ordinary handler/database failure `FAILED` and returns `503` so Meta
  can retry. Successful work is marked `DONE` with an explicit retention expiry.
- If a user-visible text/button/list reply fails after state mutation, a
  no-request/configuration failure, connection failure, or explicit transient
  HTTP result is safe to retry: the same transaction marks the inbound event
  `DONE` and creates one deduplicated `whatsapp_conversation_delivery` outbox
  job. A Meta replay is then ignored rather than rerunning business logic.
- An ambiguous transport result, where Meta may already have accepted the
  reply, is marked `DONE` without automatic resend. An explicit permanent
  rejection also is not retried. If the terminal event/outbox transaction
  itself cannot be persisted, the endpoint returns `503`.
- Processes one unclaimed item from a multi-message batch and returns `503`
  when more remain; the next delivery drains the next unclaimed message.
- Applies per-user and global request limits before menu, support, media,
  paid-session, or other user-flow branches. A limited sender receives at most
  one user-facing limit notice per applicable window.
- Acknowledges status-only and unsupported message events without treating
  them as user messages.

Common outcomes are `200` for handled, ignored, maintenance, duplicate,
`rate_limited`, `delivery_queued`, or `delivery_not_retried` events; `400` for
invalid JSON; `403` for invalid signatures; `413` for an oversized body; and
`503` for retryable processing, terminal-state persistence, or batch-drain work.

### `POST /payment/webhook`

This endpoint accepts Razorpay `payment_link.paid` events.

The current implementation:

1. Verifies `X-Razorpay-Signature` over the exact raw bytes before JSON parsing
   using the current or optional previous webhook secret.
2. Requires `RAZORPAY_MODE` to be `test` or `live`.
3. Rejects invalid/future timestamps. A delayed correctly signed capture is
   not discarded solely for age; durable payment/event identity remains the
   replay control.
4. Validates bounded provider identifiers and preserves any terminal manual
   reconciliation disposition (`RESOLVED`, `REFUND_INITIATED`, `REFUNDED`, or
   `IGNORED`) before continuing.
5. Requires the signed event snapshot to contain a captured payment and paid
   payment-link entity.
6. Resolves the booking by its stored Razorpay payment-link ID, then requires
   INR and compares provider paise against that booking's stored amount, not
   the current global price.
7. Outside the database transaction, independently fetches the current
   authenticated Payment Link and Payment resources. It then locks and
   revalidates the booking plus every matching payment/link review row in a
   fixed order, retaining those locks through the entitlement commit.
8. Requires exact current link identity, booking reference/ID/token notes,
   amount/currency, partial-payment-disabled configuration, exactly one full
   captured payment with the event's payment ID, `captured=true`, and zero/no
   refund state.
9. Uses the Razorpay payment ID as a durable `webhook_events` idempotency key.
   A provider lookup failure returns `503` without entitlement so Razorpay can
   retry.
10. Preserves unmatched evidence and returns `503`. Invalid current evidence,
    amount/currency changes, or a different prior payment are durable review
    cases acknowledged with `202`; none marks the booking paid.
11. Atomically marks an exact payment paid, updates the user, completes the
    webhook event, creates the fulfilment work item, and inserts separate
    outbox jobs.

Duplicate completed events return `200` and do not repeat payment mutation or
outbox insertion. A signed but non-final event returns `409`; payment conflicts
enter durable review and return `202`. Invalid signatures and malformed
payloads return `400`. A terminal manual disposition is recorded on the
webhook event as `MANUAL_DISPOSITION`, returns `202`, creates no entitlement or
outbox work, and is checked again after provider lookup to close an
operator/webhook race.

### Admin console and API

Human operators use `GET/POST /admin/login` and the appointment board at
`GET /admin/appointments`. Login requires the shared `ADMIN_PASSWORD` plus a
stable operator ID. Signed browser sessions expire after two hours and unsafe
requests require the session CSRF token. Five failed logins from one service
address within 15 minutes temporarily throttle that address.

Machine clients continue to use `Authorization: Bearer <ADMIN_TOKEN>` or
`X-Admin-Token: <ADMIN_TOKEN>`; unsafe methods additionally require
`X-Operator-ID`. When the admin token is absent, protected routes return `404`;
invalid credentials return `401`. Responses carry no-cache, frame-denial and
restrictive content-security headers. Every successful mutation records
before/after values and the operator ID in `admin_audit_events`.

| Route | Operation |
|---|---|
| `GET/POST /admin/login`, `POST /admin/logout` | Browser session lifecycle |
| `GET /admin/appointments` | Responsive appointment queue for paid-consultation operations |
| `GET /admin/fulfillment-workflow` | Server-authoritative fulfilment transitions used by the console |
| `GET /admin/metrics` | Aggregate product and operational counts, including inbound claims, fulfilment and reconciliation risk |
| `GET /admin/support?limit=25&status=OPEN` | Support queue |
| `PATCH /admin/support/<ticket_id>` | Assign, prioritize, resolve, or close a ticket; closing requires a resolution note |
| `GET /admin/fulfillments?status=UNASSIGNED` | SLA-ordered paid-consultation queue |
| `PATCH /admin/fulfillments/<booking_id>` | Audited assignment, status transition, capacity-checked paid reschedule, or reviewed refund recording |
| `GET /admin/payment-reconciliations?status=OPEN` | Captured-payment review queue |
| `PATCH /admin/payment-reconciliations/<id>` | Audited disposition with a required resolution note |
| `GET /admin/outbox` | Outbox inspection |
| `POST /admin/outbox/<job_id>/retry` | Controlled retry of a terminal failed job |
| `GET /admin/availability?from=YYYY-MM-DD&to=YYYY-MM-DD` | Active blackouts and capacity overrides |
| `POST/DELETE /admin/availability/blackouts[...]` | Activate/deactivate date or slot blackouts |
| `POST/DELETE /admin/availability/capacity[...]` | Activate/deactivate date or slot capacity overrides |
| `GET /admin/audit` | Recent operator mutation audit |

These routes expose sensitive operational data. Keep them behind TLS and
platform access controls. The console records a supplied operator identity but
still uses a shared password; it does not yet provide individually verified
credentials, application RBAC, or application MFA.

A paid cancellation cannot be recorded directly from `UNASSIGNED`. The
reviewed refund path records `REFUND_REVIEW` and then `REFUNDED`; that terminal
fulfilment state changes the booking to `CANCELLED` while retaining its amount,
processed-payment flag, and provider IDs. If the user has no other `PAID`
booking, paid AI/session state is cleared. The mutation also terminalizes or
creates the exact `REFUNDED` payment-reconciliation row. Booking, review,
fulfilment, and user state are locked/recomputed in a fixed order. This API
records an externally reviewed, operator-attested refund outcome; the
application neither independently verifies that provider action nor calls
Razorpay to execute it.

For an accepted payment, the reconciliation endpoint permits
`REFUND_INITIATED` only after fulfilment is in `REFUND_REVIEW`, and permits
`REFUNDED` only after fulfilment is `REFUNDED` and the booking is `CANCELLED`.
This prevents financial refund status from coexisting with paid entitlement.

## Outbound WhatsApp Cloud API

`services/whatsapp_service.py` sends text, reply-button, list, template,
document, payment-success, and receipt messages.

Implemented transport behavior:

- Validates and bounds WhatsApp field lengths before sending.
- Uses a shared `httpx` client with bounded timeout and retry settings.
- Returns a structured result with an explicit `ok` flag.
- Logs a privacy-preserving recipient reference rather than a phone number or
  message body.
- Treats provider rejection as failure; callers in the webhook and outbox
  convert failures into retryable processing.

Required configuration is `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`,
`WHATSAPP_VERIFY_TOKEN`, and `WHATSAPP_APP_SECRET`. The optional
`WHATSAPP_APP_SECRET_PREVIOUS` supports a bounded signature-secret rotation.
The Graph API version is set by `WHATSAPP_API_VERSION`.

Production prerequisite: configure the Meta app and callback, verify the phone
number, validate the selected API version, and obtain approval for every
business-initiated template before using reminders or campaigns.

## Razorpay

`services/booking_service.py` creates payment links only after the user reviews
their name, matter, location, date, time, and fee.

The link:

- Uses the amount stored on the newly created booking.
- Uses INR and disables partial payment.
- Has a configurable expiry of at least 16 minutes.
- Carries unique booking token/ID metadata.
- Is cancelled on a best-effort basis if the database transaction fails after
  provider creation.

Required configuration is `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
`RAZORPAY_WEBHOOK_SECRET`, and `RAZORPAY_MODE`. The optional
`RAZORPAY_WEBHOOK_SECRET_PREVIOUS` supports a bounded webhook-secret rotation;
it is not a second API key.

Production prerequisite: run signed scenarios against the isolated, empty
staging database with Razorpay test-mode credentials. Then configure separate
live credentials and a live webhook for the different, empty production
database. The current release imports no legacy bookings or payments: reconcile
only staging test transactions, and confirm production contains no synthetic
or legacy rows before traffic. Any future import requires the separately
approved contingency migration and reconciliation plan.

## Amazon SES

`services/email_service.py` sends:

- Confirmed-booking notifications.
- Support-ticket notifications.
- Compatibility messages used by the daily appointment job.

Booking recipients come from comma-separated
`BOOKING_NOTIFICATION_EMAILS`; support recipients come from
`SUPPORT_NOTIFICATION_EMAILS`; and payment-review alerts go only to
`PAYMENT_RECONCILIATION_EMAILS`. This separation prevents ordinary support or
booking mailboxes from receiving financial-review metadata. There is no
hard-coded recipient. The sender is `SES_FROM_EMAIL`.
Recipients are placed in BCC and a send is rejected before the provider call
when the deduplicated list exceeds Amazon SES's 50-destination limit.

`services/email_service.py` uses the boto3 SES v2 client over HTTPS in
`SES_REGION`. It uses `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, plus
optional `AWS_SESSION_TOKEN`. Staging and production require
`SES_CONFIGURATION_SET` so provider events can be monitored. Connect and read
timeouts are bounded by
`SES_CONNECT_TIMEOUT_SECONDS` (default `5`) and
`SES_READ_TIMEOUT_SECONDS` (default `15`). Immediate SDK retries are disabled:
an ambiguous timeout may have followed provider acceptance, so retry ownership
stays with the durable outbox instead of an in-process retry loop. SES
`SendEmail` has no idempotency token, so an ambiguous accepted request can be
delivered again after an outbox retry. NyaySetu therefore explicitly uses
at-least-once email delivery; the stable event type and record ID in the
subject/tags let operators identify a duplicate without putting user data in
the message.

Delivery failures return `False`. Logs and alerts may contain only the provider
exception class, provider error code, and recipient count—never recipient
addresses, message bodies, credentials, or provider response bodies.
Booking, support, and payment-review notifications are retried by the durable
outbox when configured.

Production prerequisites:

- Verify the sending identity/domain in the configured SES region.
- Publish and validate DKIM, SPF, and DMARC records.
- Move the SES account/region out of the sandbox before sending to unverified
  operational recipients.
- Grant the runtime identity only the required `ses:SendEmail` permission and
  only for the intended identity where policy scoping permits.
- Configure `SES_CONFIGURATION_SET` and monitor bounce, complaint, and delivery
  events through approved destinations and alerts.
- Explicitly approve recipients and establish access and retention rules for
  operational alert metadata. Case narratives and direct contact details must
  remain in the authenticated operations interface, not email.

## Durable outbox

Payment confirmation creates independent jobs for WhatsApp success,
booking-notification email, and, when `AUTO_SEND_RECEIPTS=true`, a receipt.
Support email uses a support-notification job. The outbox runner:

```text
python -m jobs.process_outbox
```

claims a bounded batch, retries with exponential backoff, recovers expired
running leases, and marks exhausted jobs `DEAD`. The web request may start a
best-effort fast-path task, but that executor admits no more than 32
queued/in-flight tasks and skips the optional kick when saturated. The
committed database row and one-minute cron remain the recovery source.

Production prerequisite: run the outbox command on a one-minute schedule
against the same PostgreSQL database and provider settings as the web service,
and alert on queue age and `DEAD` jobs.

The outbox also handles deduplicated `whatsapp_conversation_delivery` jobs for
user-flow text/button/list replies whose original failure is known safe to
retry. It never re-enters the inbound state machine. Recipient and reply content
exist only while delivery remains actionable; a `COMPLETED` or `DEAD`
conversation-delivery job replaces that payload with a minimal delivery marker.
Ambiguous transport delivery is never automatically resent.

## Payment reconciliation

The independent safety-net command is:

```text
python -m jobs.reconcile_payments --limit 100
```

It checks a recent-first bounded set of `PENDING`/`EXPIRED`, unprocessed
payment links. For a possible capture it fetches both the authenticated Payment
Link summary and current Payment resource. It automatically marks a booking
paid only when link identity, reference/notes, INR amount, single full capture,
payment identity/status, `captured=true`, and zero refund state all match
exactly. Exact recovery also creates fulfilment and deduplicated follow-up
jobs. Ambiguous evidence is preserved in `payment_reconciliations` for an
audited operator disposition and can enqueue an operator alert when notification
recipients are configured. Manual `RESOLVED`, `REFUND_INITIATED`, `REFUNDED`,
and `IGNORED` dispositions are terminal; scheduled reconciliation never
reopens them.

The command prints privacy-minimised JSON and exits `2` on configuration or
provider errors; otherwise it exits `0`, including when review items were
created. The Render Blueprint schedules one bounded run every five minutes.
Alert on nonzero runs and stale/open review items, and rehearse the operator
disposition path before launch.

## Consultation reminders

The bounded scheduler is:

```text
python -m jobs.consultation_reminders
```

Render invokes it every ten minutes. Empty template configuration makes the
run a successful no-op. When an exact Meta-approved name and language code are
configured for a 24-hour or 2-hour/user-language combination, it enqueues
deduplicated outbox work only for `PAID` bookings with eligible active
fulfilment status and a due scheduled start. Imminent 2-hour work is scanned
first.

The outbox rechecks live template configuration, booking/fulfilment state,
scheduled time, and catch-up window immediately before sending. Clearing a
template pair disables both future scheduling and already queued sends.
Templates take exactly two positional body values: formatted appointment date
and time. Keep all pairs empty until purpose-specific opt-in, Meta utility
template approval, English/Hindi/Marathi rendering, reschedule/refund
suppression, and frequency-policy tests pass.

## Maintenance and retention

Run a read-only rehearsal with:

```text
python -m jobs.maintenance --dry-run --batch-size 500 --fail-on-risk
```

The bounded job expires stale pending bookings and deletes only eligible
completed webhook/inbound events, old analytics, and completed outbox jobs.
It reports overdue/missing-SLA fulfilment and support work plus stale payment
reviews without deleting that evidence. Exit `1` means the maintenance
transaction failed. With `--fail-on-risk`, exit `2` means the run succeeded but
the JSON report requires operator attention; without that flag, inspect
`operational_risks.summary.alert_required`.

Render's daily command includes `--fail-on-risk`, so either a transaction
failure or an actionable risk makes the cron run nonzero.

## AI providers

`services/ai_router.py` selects Claude, OpenAI, or the built-in local provider.
`AI_PROVIDER` can force one provider; `AI_PROVIDER_ORDER` controls automatic
ordering. The local provider is always the final fallback.

Before routing, deterministic checks:

- Return a safety response for detected immediate-danger or harmful requests.
- Scrub common phone, email, Aadhaar, PAN, UPI, secret, and long-number
  patterns.
- Derive a non-reversible provider safety identifier.

OpenAI uses `OPENAI_API_KEY` and configurable `OPENAI_MODEL`; Claude uses
`ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`. Provider calls have bounded timeouts
and fall back to local content on failure. The WhatsApp product also asks for
AI consent before enabling the AI flow and limits the free flow to five
questions.

These controls are best effort, not a legal, privacy, or clinical assurance.
Production use of a third-party AI provider requires approved notices,
purpose/retention rules, vendor terms, multilingual safety evaluation, and
legal review of prompts and content.

## Configuration groups

The authoritative defaults and validation rules are in `config.py` and
`.env.example`. Important groups are:

- Runtime: `ENV`, `APP_TIMEZONE`, `LOG_LEVEL`, `DATABASE_URL`.
- WhatsApp: `WHATSAPP_*`, current/previous signing secret, webhook size, lease,
  replay, and retention settings.
- Razorpay: `RAZORPAY_*`, current/previous webhook secret,
  `PAYMENT_LINK_TTL_MINUTES`, and reconciliation lookback.
- Booking: price, cutoff, horizon, daily capacity, and per-slot capacity.
- Delivery: Amazon SES region/sender/AWS credentials, configuration set
  (required in staging/production), bounded connect/read timeouts, notification
  recipients, outbox retry
  settings, `AUTO_SEND_RECEIPTS`, and exact per-language 24-hour/2-hour Meta
  reminder template pairs plus catch-up/batch bounds.
- Product trust: support SLA, privacy/terms/refund/cancellation URLs, consent
  versions, admin token, and AI safety settings.

Never put secrets in committed files, URLs, request logs, or analytics
properties.

## Rollout verification

Before production traffic:

- `/health/ready` reports a healthy PostgreSQL backend.
- Invalid Meta and Razorpay signatures are rejected.
- A signed test payment confirms the matching booking and stored amount once.
- Amount mismatch and unmatched-capture fixtures create review evidence without
  falsely confirming the booking.
- An injected database/handler failure is reclaimed through Meta retry without
  duplicate side effects.
- A known-safe post-mutation reply failure becomes one conversation-delivery
  outbox job while Meta replay is ignored; an ambiguous transport failure is
  not resent, and terminal conversation payloads are scrubbed.
- The outbox cron drains jobs and exposes no PII in logs.
- The reconciliation command and maintenance dry-run return reviewed results;
  operator mutation/audit endpoints are access-tested.
- With reminder templates empty, the reminder cron is a no-op. With staging
  templates approved, each 24-hour/2-hour reminder is deduplicated and becomes
  unsendable after cancellation/reschedule/review or template removal.
- Amazon SES identity/domain, DKIM/SPF/DMARC, production access,
  least-privilege permission, configuration-set monitoring, recipients, and
  Meta templates are explicitly approved.
- Fresh-production backup/restore, staging test-transaction reconciliation,
  retention, privacy, refund, and support procedures are signed off.
