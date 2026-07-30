# Technical Architecture

## Current runtime

NyaySetu is a Flask application served by Gunicorn. It receives Meta WhatsApp
and Razorpay webhooks, persists workflow state through SQLAlchemy, calls
external providers, and records retryable side effects in a database outbox.

```text
Meta WhatsApp ----> Flask /webhook ------------+
                                                |
Razorpay --------> Flask /payment/webhook ------+--> PostgreSQL (production)
                                                |      users / bookings
Operator --------> Flask /admin/* --------------+      idempotency / analytics
                                                |      inbox / outbox / fulfilment
                                                |
                                                +--> WhatsApp Cloud API
                                                +--> Razorpay payment links
                                                +--> AI router

python -m jobs.process_outbox ----------------------> WhatsApp / SendGrid
python -m jobs.reconcile_payments -----------------> Razorpay lookup/recovery
python -m jobs.consultation_reminders -------------> durable reminder jobs
python -m jobs.maintenance -------------------------> bounded retention/risk report
```

The repository defaults to a relative SQLite database for local development
and tests. `DATABASE_URL` selects the real engine; provider-style PostgreSQL
URLs are normalized to the psycopg driver. Production is designed for managed
PostgreSQL, but migration and reconciliation of existing live data remain a
rollout prerequisite.

## Process topology

The included `gunicorn.conf.py`, `render.yaml`, and `Procfile` use exactly one
Gunicorn `gthread` worker with eight threads. The Gunicorn startup hook rejects
an accidental worker-count override. Separate cron services run a bounded
outbox batch every minute, payment reconciliation every five minutes,
consultation-reminder scheduling every ten minutes, and bounded maintenance
daily; each exits after one batch. Reminder scheduling is a no-op while all
approved template pairs are empty.

One web process is a correctness constraint because per-user ordering locks,
throttles, caches, and provider circuit breakers remain process-local.
PostgreSQL is still mandatory for production shared state. Do not increase
web workers/instances until process-local controls move to shared
infrastructure and concurrency/load/provider-limit tests pass.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `app.py` | Flask lifecycle, security headers, webhooks, conversation state, booking and payment orchestration |
| `config.py` | Typed, validated environment configuration |
| `db.py` | Engine/session setup, SQLite safety pragmas, PostgreSQL pooling, health checks |
| `models.py` | Core and operational SQLAlchemy entities |
| `admin.py` | Token-protected, audited metrics, support, fulfilment, reconciliation, outbox, availability, and audit operations |
| `migrations/` / `alembic.ini` | Versioned additive production schema and legacy backfill |
| `services/booking_service.py` | IST-aware availability/blackouts/overrides, capacity locks, booking/payment-link creation, payment mutation |
| `services/fulfillment_service.py` | Paid-consultation work item and SLA lifecycle |
| `services/payment_reconciliation_service.py` | Exact-evidence Razorpay recovery and ambiguity queue |
| `services/consultation_reminder_*.py` | Template-gated, bounded, deduplicated 24-hour/2-hour reminder scheduling and send policy |
| `services/maintenance_service.py` | Bounded retention enforcement and operational-risk reporting |
| `jobs/migrate_sqlite_to_postgres.py` | Fail-closed, one-shot frozen SQLite to empty PostgreSQL cutover |
| `services/whatsapp_service.py` | Validated WhatsApp payloads, bounded transport retries, structured delivery results |
| `services/outbox_service.py` | Durable jobs, step-level idempotency, retry/backoff, lease recovery |
| `services/email_service.py` | SendGrid booking/support notification delivery |
| `services/receipt_service.py` | Private temporary PDF receipt generation |
| `services/engagement_service.py` | Persistent home, status, preparation, guides, support, and privacy content |
| `services/ai_router.py` | Claude/OpenAI/local selection and fallback |
| `services/ai_safety.py` | Deterministic urgent/harmful guards, PII scrubbing, pseudonymous safety IDs |
| `location_service.py` | District/state lookup and fuzzy ambiguity results used by the active flow |
| `translations.py` / `utils/i18n.py` | English, Hinglish, and Marathi user text |

The advocate helper is not automatically invoked, but authorised operators can
assign an active advocate or a named fulfiller through the fulfilment API.
Credential/conflict review and the actual consultation channel remain business
operations.

## WhatsApp request lifecycle

1. Assign or validate a request ID and apply the payload-size limit.
2. Verify Meta's raw-body HMAC unless an explicit non-production bypass is
   enabled.
3. Extract message envelopes and skip `DONE` Meta message IDs.
4. Claim one message ID in `inbound_message_events` with a bounded processing
   lease.
5. Load/create the user and process the persisted state machine.
6. Persist state transitions as required and send validated WhatsApp payloads.
7. On an ordinary handler/database failure, roll back current work, mark the
   claim `FAILED`, and return `503`; failed or expired leases can be reclaimed.
8. If a text/button/list reply fails after state mutation and no provider
   request occurred, connection setup failed, or Meta returned an explicit
   transient status, atomically mark the claim `DONE` and enqueue one
   deduplicated `whatsapp_conversation_delivery` job. Meta replay is ignored.
9. If transport failure is ambiguous because Meta may have accepted the reply,
   mark the claim `DONE` without automatic resend. A permanent rejection is
   likewise not retried.
10. If the Meta delivery contained additional unclaimed messages, return `503`
   after the first success so a retry drains the next item.

The state machine includes language, AI consent, booking-scope review, identity
and location collection, category/subcategory, date/slot, booking review,
payment waiting, paid AI, support, and feedback states. `home`/`menu` is
persistent and does not erase an in-progress draft.

## Booking and capacity lifecycle

All user-facing date/slot calculations are timezone-aware for Asia/Kolkata.
Database timestamps remain naive UTC for backward schema compatibility.

Availability:

- Includes today when a slot remains outside the configured cutoff.
- Enforces a configurable future horizon.
- Hides expired/past and full dates or slots.
- Counts paid bookings and non-expired pending bookings against capacity.

Creation:

1. Revalidate the date, slot, and required details.
2. Acquire a transaction-scoped PostgreSQL advisory lock for the date
   (SQLite uses a write-lock fallback).
3. Recheck per-day and per-slot capacity.
4. Insert a pending booking with its own amount and unique token.
5. Create the Razorpay payment link.
6. Store the provider link ID and commit.
7. Roll back and best-effort cancel an orphan provider link on failure.

The user reviews all booking details before step 1, so simply selecting a slot
does not create a booking or payment link.

## Razorpay payment lifecycle

The payment webhook verifies the raw-body signature before parsing and accepts
only final paid/captured event snapshots. It finds the booking by stored
payment-link ID and compares the provider amount against `booking.amount`, but
does not treat that signed snapshot as sufficient entitlement evidence.

Before any entitlement mutation, it releases the read transaction and makes
bounded authenticated reads of the current Razorpay Payment Link and Payment
resources. It then locks and revalidates the booking. Exact acceptance requires
link identity, booking reference/ID/token notes, amount/currency, a single full
capture with the event's payment ID, current `captured=true`, and zero/no refund
state. Terminal manual reconciliation statuses (`RESOLVED`,
`REFUND_INITIATED`, `REFUNDED`, and `IGNORED`) are authoritative and are checked
both before and after provider reads. The webhook and scheduled reconciler lock
the booking and all matching open/terminal payment/link review rows in the same
order and hold them through entitlement commit.

Within one database transaction it:

- Claims/updates a `webhook_events` record keyed by provider and payment ID.
- Conditionally changes the intended booking from unprocessed to paid.
- Stores payment ID, mode, and paid timestamp.
- Updates the user's state and clears the active short link.
- Inserts independent outbox jobs for configured external side effects.
- Marks the durable webhook event done.

An unmatched captured payment creates review evidence and returns `503`. A
provider lookup failure also returns `503`, records a privacy-minimised failed
event when possible, and grants no entitlement. Invalid current evidence,
amount/currency changes, or a different prior payment create review evidence
and return `202` without paying the booking, avoiding an endless provider retry
storm. Exact accepted payments create a fulfilment work item. Malformed/invalid
events are rejected; duplicate completed events are idempotent. A terminal
manual disposition returns `202` without entitlement or outbox work.

The audited fulfilment API supports capacity-checked paid rescheduling and a
reviewed `REFUND_REVIEW` to `REFUNDED` transition. Recording `REFUNDED` changes
the booking service status to `CANCELLED` while preserving its processed flag,
amount, payment ID, and link ID. It clears paid user session/AI state only when
no other `PAID` booking remains and terminalizes or creates the exact
`REFUNDED` reconciliation. The admin path uses the same booking-to-reviews lock
order, then locks fulfilment and user state before cross-booking entitlement
recomputation. This records an external refund outcome; no Razorpay refund
request or independent refund verification is made.

## Outbox and delivery architecture

The committed outbox is the source of truth after payment. A daemon thread may
attempt immediate processing, but the web fast-path executor is capped at 32
queued/in-flight tasks and safely skips new kicks when saturated. Process loss
or fast-path saturation cannot remove the committed job; the one-minute cron
remains authoritative.

Supported job kinds are:

- `payment_success_message`
- `booking_notification`
- `payment_receipt`
- `support_notification`
- `payment_reconciliation_alert`
- `consultation_reminder`
- `whatsapp_conversation_delivery`
- A compatibility composite `payment_followup`

Each job is atomically claimed from `PENDING`, moved through `RUNNING`, and
completed only after an explicit provider success. Failures use bounded
exponential backoff and eventually become `DEAD`. Step markers prevent a
completed WhatsApp action from repeating if a later composite step fails.
Conversation-delivery jobs retry only a known-safe failed send and never rerun
the inbound state machine. Their actionable payload contains the recipient and
reply temporarily; completion or terminal death scrubs it to a minimal marker.
Ambiguous transport outcomes become terminal rather than risking a duplicate
user-visible reply.

Receipt files are created with randomized names in the system temporary
directory, best-effort owner-only permissions, and deletion after every
delivery attempt. Automatic receipt jobs are disabled unless
`AUTO_SEND_RECEIPTS=true`.

## Scheduled reconciliation, reminders, and maintenance

`python -m jobs.reconcile_payments --limit 100` independently checks recent
unprocessed payment links through authenticated Razorpay Payment Link and
current Payment-resource lookups. It automatically recovers only one exact,
captured, non-refunded INR payment whose link, booking reference/notes, amount,
and payment identity all match. Recovery creates fulfilment and deduplicated
outbox work; ambiguity is preserved in `payment_reconciliations` for an audited
operator disposition/alert. It runs every five minutes and exits `2` on
provider/configuration errors.

`python -m jobs.consultation_reminders` runs every ten minutes and schedules
deduplicated 24-hour/2-hour reminder jobs only for exact configured
user-language template pairs and eligible paid fulfilments. With all template
pairs empty it is inert. The outbox rechecks the live template, booking,
fulfilment, schedule, and catch-up window immediately before sending, so
clearing a pair or changing the appointment safely suppresses queued work.

`python -m jobs.maintenance --batch-size 500 --fail-on-risk` applies a narrow,
bounded retention policy and emits a PII-free JSON report. It can expire stale
pending bookings and remove only eligible completed inbox/webhook/outbox and
old analytics rows. Financial, fulfilment, support, user, feedback,
conversation, failed, and legacy evidence is preserved. `--dry-run` rolls back
changes; the scheduled `--fail-on-risk` returns `2` after a successful
transaction when overdue fulfilment, support, or stale payment-review signals
require attention.

## AI architecture

The conversation layer requires user consent before AI. The router applies
deterministic safety checks, then tries the configured provider order and
always retains the built-in local legal-information provider as a fallback.

Third-party prompts have common high-risk identifiers scrubbed and use a
non-reversible safety identifier. Responses include legal-information
disclaimers; external prompts use current BNS/BNSS/BSA terminology. Provider
timeouts and retry counts are bounded.

Limitations:

- PII pattern matching cannot guarantee full de-identification.
- Per-user/global limits run before menu, support, media, and paid-session
  branches, and rate-limit notices are deduplicated per window. Rate-limit and
  maintenance-notice state plus the AI response cache are lock-protected,
  pruned, and hard-bounded for long-lived threaded operation; they and the
  circuit breakers remain process-local.
- The local knowledge content is static, not a source-cited retrieval system.
- No model output is a substitute for a qualified lawyer or emergency service.

## Persistence and schema

Core tables are `users`, `bookings`, `category_analytics`, `conversations`, and
`advocates`. Operational tables include `inbound_message_events`,
`processed_messages` (legacy), `user_consents`, `feedback`,
`support_requests`, `analytics_events`, `webhook_events`, `outbox_jobs`,
`booking_fulfillments`, `payment_reconciliations`, availability
blackouts/overrides, and `admin_audit_events`.

Alembic revision `20260729_01` is the production baseline. It creates additive
schema, upgrades selected legacy columns/constraints, and backfills durable
inbound claims and paid-booking fulfilments. Render runs
`python -m alembic -c alembic.ini upgrade head` before the web release;
production readiness checks the applied revision and requires automatic schema
creation to be disabled. `init_db()`/`create_all()` remains a non-production
local compatibility path only.

The baseline does not prove a live cutover. The one-shot
`jobs.migrate_sqlite_to_postgres` utility requires a frozen, current-head
SQLite backup, a schema-current empty PostgreSQL target, and a target URL in
the dedicated `NYAYSETU_CUTOVER_TARGET_URL` environment variable. Its default
mode validates SQLite integrity/foreign keys, full table/column shape, source
stability, target emptiness, and per-table counts without writing. The exact
confirmation mode locks the target tables, copies deterministic bounded
batches, verifies counts, resets integer-key sequences, and commits atomically.
It never reads application `DATABASE_URL` and is not a backup or live-sync
design. Operators must still create and restore-test the backup through
SQLite's backup mechanism, rehearse in staging, validate constraints/backfills,
reconcile payments, and preserve a rollback snapshot.

## Health, admin, and observability

- `/health/live` proves the process can answer.
- `/health/ready` checks the database, production database type, expected
  Alembic revision, disabled automatic schema creation, required configuration,
  credential prefixes, and minimum secret/token lengths.
- `/admin/metrics` exposes aggregate operational counts.
- `/admin/*` exposes authenticated queues and audited mutations for support,
  fulfilment, payment review, outbox recovery, and availability.
- Request IDs are returned to callers.
- Logs avoid raw WhatsApp bodies, phones, email recipients, database
  credentials, and outbox payloads.
- `analytics_events` stores bounded, redacted product events separately from
  the active user transaction.

Readiness does not call Meta, Razorpay, SendGrid, or AI, and it does not verify
provider reachability, outbox freshness, backup status, or webhook dashboard
health. Those require external monitoring.

## Implemented versus rollout work

Implemented in code:

- Environment-selected PostgreSQL/SQLite persistence.
- Alembic release baseline and production schema-readiness gate.
- Fail-closed one-shot SQLite-to-PostgreSQL cutover command.
- Correct IST slot mapping and capacity-aware booking.
- Lease-aware durable WhatsApp claims and signed/idempotent Razorpay processing.
- Stored-price payment validation and transactional outbox creation.
- Persistent home/self-service, support, feedback, privacy, and AI consent.
- Exact-evidence payment recovery and human reconciliation queue.
- Paid-consultation fulfilment/SLA records and availability controls.
- Token-protected, audited operator APIs and bounded retention/risk maintenance.

Required before production cutover:

- Rehearsed execution of the included cutover command, backup/restore evidence,
  managed PostgreSQL validation, and payment reconciliation.
- One-worker web plus outbox, reconciliation, reminder, and maintenance
  deployments with isolated production secrets and alerts.
- Signed Meta/Razorpay staging tests and approved SendGrid recipients.
- Privacy/legal review, support/fulfilment and refund policies, approved
  retention scope, alerting, and runbooks.

Future architecture:

- Distributed throttling and high-throughput queueing if horizontal scale is
  required.
- Automatic advocate matching/user notification, provider refund execution,
  and CRM integration.
- Per-operator identity/RBAC/MFA and expanded settlement/chargeback workflows.
- Reviewed, source-backed legal retrieval and AI quality monitoring.
