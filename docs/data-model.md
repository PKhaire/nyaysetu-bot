# Data Model and Governance

## Database selection

SQLAlchemy uses `DATABASE_URL`. PostgreSQL URLs are normalized to
`postgresql+psycopg`; relative SQLite paths are anchored beside the
application. SQLite enables foreign keys, WAL, a busy timeout, and normal
synchronous mode for local compatibility.

Managed PostgreSQL is the required production target. The repository includes
Alembic revision `20260729_01`, and production disables automatic
`Base.metadata.create_all()` by default. Render applies
`python -m alembic -c alembic.ini upgrade head` before a web release;
`/health/ready` rejects a production database whose revision is not current.
On an empty database, the baseline creates the application and additive
reliability/operations schema. It also retains compatibility transformations
for selected legacy columns/indexes, legacy message claims, and paid-booking
fulfilment backfills, but those paths are not used by the current fresh release.

The current launch provisions an isolated empty staging PostgreSQL database and
a different empty production PostgreSQL database. No existing users, bookings,
payments, or other legacy rows are imported or reconciled. The included
`jobs.migrate_sqlite_to_postgres` command is retained only as a non-current
contingency; it copies a frozen current-head SQLite artifact into an empty
current-head PostgreSQL target and is not a live backup or synchronization
mechanism.

## Logical relationships

```text
users.whatsapp_id 1 ---- * bookings.whatsapp_id
users.id          1 ---- * feedback.user_id
users.id          1 ---- * support_requests.user_id
users.id          1 ---- * user_consents.user_id
users.id          1 ---- * analytics_events.user_id

bookings.id        1 ---- 1 booking_fulfillments.booking_id
bookings.id        1 ---- * payment_reconciliations.booking_id
advocates.id       1 ---- * booking_fulfillments.advocate_id
bookings.id        ---- referenced inside outbox_jobs.payload_json

inbound_message_events durable lease-aware Meta message inbox
webhook_events        durable provider-event idempotency/audit
processed_messages    retained legacy Meta deduplication evidence
outbox_jobs           retryable external side effects
booking_blackouts / booking_capacity_overrides
admin_audit_events    operator mutation history
```

New operational entities declare foreign keys where the migration can enforce
them safely. Several legacy WhatsApp-ID and outbox-payload relationships remain
logical, so application code, migration checks, and reconciliation still
protect referential integrity.

## Tables

### `users`

One row per WhatsApp identifier.

| Area | Fields |
|---|---|
| Identity | `id`, unique `whatsapp_id`, unique `case_id`, `name`, `language` |
| Workflow | `flow_state`, `welcome_sent`, `session_started` |
| Location | `state_name`, `district_name`, `temp_state`, `temp_district` |
| Legal intake | `category`, `subcategory` |
| AI | `ai_enabled`, `free_ai_count`, `query_count` |
| Booking draft | `temp_date`, `temp_slot`, `last_payment_link` |
| Audit | `created_at` |

`ai_enabled` is current flow state, not the consent record; versioned grants
are stored separately in `user_consents`.
`last_payment_link` contains a provider short URL and should be treated as
sensitive.

### `bookings`

The commercial appointment and payment record.

| Area | Fields |
|---|---|
| Identity/contact | `id`, indexed `whatsapp_id`, `name`, `phone` |
| Matter | `state_name`, `district_name`, `category`, `subcategory` |
| Appointment | `date`, `slot_code`, `slot_readable` |
| Price/status | `amount`, `status`, unique `payment_token` |
| Razorpay | unique `razorpay_payment_link_id`, unique `razorpay_payment_id`, `payment_processed`, `payment_mode`, `paid_at` |
| Receipt | `receipt_generated`, `receipt_sent` |
| Audit | `created_at` |

`BookingStatus` is `PENDING`, `PAID`, `EXPIRED`, `CANCELLED`, or `COMPLETED`.
The stored `amount` is the payment webhook source of truth, so a later price
change cannot alter an existing obligation.

Indexes support WhatsApp/status and payment-token lookups. Pending capacity
counts only while the booking remains inside the payment-link lifetime.

### `category_analytics`

Stores a count by category and subcategory. It is aggregate intent data, not
the primary event stream.

### `conversations`

Contains `user_whatsapp_id`, direction, free text, and `created_at`. The active
webhook does not currently persist every conversation through this table.
Because the schema can store legal-message text, any future activation requires
explicit purpose, access, and retention controls.

### `advocates`

Contains name, email, category, district, and active flag. An authorised
operator may attach an active advocate to a paid booking's fulfilment record.
The matching helper is not automatically invoked by the payment flow; vetting,
conflict checks, staffing, and user notification remain operational duties.

### `processed_messages`

Legacy deduplication rows retained for migration compatibility and evidence.
The active webhook no longer writes this table, and conservative maintenance
does not delete it.

### `inbound_message_events`

The active durable WhatsApp inbox. Each unique Meta message ID records
`PROCESSING`, `DONE`, or `FAILED`, attempt count, a bounded processing lease,
safe error code, received/processed timestamps, and explicit expiry.

An unexpired claim prevents concurrent processing. A failed claim or expired
lease can be reclaimed after a handler/process crash. Only expired `DONE` rows
are eligible for bounded maintenance deletion; nonterminal evidence is
preserved. A known-safe post-mutation text/button/list delivery failure marks
the claim `DONE` in the same transaction that creates a deduplicated
`whatsapp_conversation_delivery` outbox job, so Meta replay cannot rerun the
state transition. Ambiguous transport delivery is also terminal `DONE` but is
not automatically resent.

### `feedback`

Stores optional `user_id`, rating, comment, source, JSON context, workflow
status, and timestamps. The active flow writes a one-to-five rating and an
optional comment after the paid consultation window.

The database does not enforce the rating range; application validation does.

### `support_requests`

Stores optional user/case references, request type, subject, message, status,
priority, assignment, SLA due time, resolution note, timestamps, and resolution
time. The WhatsApp flow creates `OPEN` requests. Authenticated operator APIs
can assign, prioritize, progress, resolve, or close them; final states require a
resolution note and create an admin audit event.

### `user_consents`

Stores purpose, policy version, grant/revoke state, source, and timestamps under
a unique user/purpose/version constraint. The current booking-payment and AI
flows record versioned grants. Privacy export/deletion/legal-hold workflows are
still separate future governance work.

### `analytics_events`

Stores event name, optional user/session references, bounded JSON properties,
and creation time. The analytics service redacts sensitive property keys and
isolates event writes from the main user transaction.

This table is product telemetry, not a financial ledger.

### `webhook_events`

Durable provider-event inbox with:

- Unique `(provider, event_id)`.
- Event type and SHA-256 payload fingerprint.
- Status, attempts, safe error code, received/processed timestamps.
- Expiry timestamp for the intended retention window.

Razorpay uses the payment ID as `event_id`. Full provider bodies are not stored.

### `outbox_jobs`

Stores job kind, JSON payload, status, attempts, next availability, safe error,
and timestamps. Current states are `PENDING`, `RUNNING`, `COMPLETED`, and
`DEAD`.

Payloads use internal record IDs and step markers. They must still be treated
as restricted application data. Old `COMPLETED` jobs are eligible for bounded
maintenance deletion; pending/running/dead evidence is preserved.

### `booking_fulfillments`

One operational record per paid booking, with lifecycle status, optional
advocate/named assignee, scheduled start, SLA due time, operator notes, and
assignment/confirmation/completion/feedback timestamps. Payment acceptance and
exact reconciliation recovery both ensure this record exists.

The audited admin API enforces explicit status transitions and assignment for
`ASSIGNED`/`CONFIRMED`. A paid reschedule is capacity-checked. Direct
`UNASSIGNED` to `CANCELLED` is not allowed; the reviewed refund path uses
`REFUND_REVIEW` then terminal `REFUNDED`. That terminal fulfilment change sets
the booking to `CANCELLED` but preserves `payment_processed`, stored amount,
payment ID, and link ID. Paid user state is cleared only when no other `PAID`
booking remains. The same mutation terminalizes or creates the exact
`REFUNDED` payment reconciliation. Booking, matching review rows, fulfilment,
and user state are locked in a fixed order before the cross-booking entitlement
recomputation. The table supports operational delivery tracking; it does not by
itself prove advocate eligibility, conflict review, provider refund execution,
or that a consultation channel was staffed.

### `payment_reconciliations`

Privacy-minimised captured-payment exceptions keyed by provider/payment
identity. Rows record the link/booking reference, stable reason, expected and
received amount/currency, status, bounded provider facts, and audited
resolution. Exact authenticated-provider recovery may close an item as
`AUTO_RESOLVED` only after Payment Link and current Payment resources agree on
an exact captured, non-refunded INR payment; ambiguous evidence remains open
until an operator records a disposition. Manual terminal statuses `RESOLVED`,
`REFUND_INITIATED`, `REFUNDED`, and `IGNORED` remain authoritative: neither a
delayed webhook nor scheduled reconciliation reopens them. Payment webhook,
scheduled reconciliation, and admin resolution share booking-to-review lock
ordering so concurrent decisions serialize without losing the disposition.

### `booking_blackouts` and `booking_capacity_overrides`

Active date-wide or slot-specific availability rules. Blackouts suppress
booking choices; overrides replace effective daily/slot capacity, including
zero. Operator create/deactivate actions are audited.

### `admin_audit_events`

Append-only application-level history for admin mutations, including operator
ID, action, target, before/after JSON, request ID, and timestamp. This improves
traceability but does not replace individually authenticated platform access,
RBAC, MFA, or provider/database audit logs.

## Data lifecycle

### User and intake

The user row is created on the first processable WhatsApp message. Profile and
workflow values are updated in place. The current application has no
user-requested export, erasure, or anonymisation function.

### Booking

```text
Review confirmed
  -> PENDING booking + Razorpay link
  -> PAID on exact valid webhook/reconciliation evidence
  -> booking_fulfillments work item
  -> COMPLETED only after an operator records completed fulfilment

PENDING -> EXPIRED after link lifetime
PENDING -> pre-payment cancellation currently clears the draft before a
           booking exists
PAID    -> capacity-checked operator reschedule is supported
PAID    -> REFUND_REVIEW -> REFUNDED fulfilment + CANCELLED booking
           (payment evidence retained; user paid state clears only when no
           other PAID booking remains)
```

The webhook/reconciler records payment, fulfilment, and outbox state
transactionally. Payment exceptions and fulfilment status are modeled;
provider settlement and chargeback import and Razorpay refund execution are
not. `REFUNDED` is an audited, operator-attested record of an external outcome,
not proof that this application verified or initiated the provider action.

### Receipt

A receipt is generated in an unpredictable system temporary path, marks
`receipt_generated`, and is deleted after the send attempt. Successful delivery
marks `receipt_sent`. Automatic generation is optional.

### Support and feedback

Support moves through an audited operator-managed lifecycle with SLA reporting.
Feedback moves from the initial rating to completed after comment or skip.
Neither is deleted by the conservative maintenance job.

### Webhook, message, analytics, and outbox records

`python -m jobs.maintenance --batch-size 500 --fail-on-risk` applies the
approved narrow maintenance policy in one bounded transaction:

- expire stale `PENDING` bookings without deleting financial records;
- delete expired `DONE` webhook and inbound-inbox events;
- delete analytics older than `ANALYTICS_EVENT_TTL_DAYS`; and
- delete old `COMPLETED` outbox jobs.

It reports overdue/missing-SLA fulfilment and support work and stale open
payment reviews. It preserves legacy `processed_messages`, users, bookings,
fulfilments, payment reviews, support, feedback, conversations, dead/failed
outbox work, failed/unmatched webhooks, and nonterminal inbound claims.
Data-subject deletion/anonymisation, legal holds, and backup-retention
enforcement are not implemented.

A pending/running `whatsapp_conversation_delivery` job temporarily contains the
recipient and exact reply needed for retry. On completion or terminal death,
the worker replaces that content with a minimal delivery marker; retained
terminal outbox history does not preserve the conversation payload.

## Sensitive data

The data set can include:

- Phone/WhatsApp identifiers, names, and location.
- Legal matter classification and support free text.
- Appointment and payment identifiers.
- Feedback comments.
- Provider short links and operational delivery metadata.

Controls implemented in code include credential-redacted database URLs,
privacy-minimised logs and analytics, no raw Razorpay body persistence, and
private temporary receipt files. Platform encryption, backup access, database
roles, audit logs, and deletion enforcement remain deployment/governance tasks.

## Fresh-release database gates

1. Provision an isolated, empty managed PostgreSQL staging database.
2. Set the staging `DATABASE_URL` and `AUTO_CREATE_SCHEMA=false`; run Alembic
   `upgrade head`, `current`, and `check`, then verify `/health/ready`.
3. Populate staging only with synthetic/test data and complete the signed
   webhook, payment, fulfilment, reconciliation, reminder, maintenance, and
   operator acceptance tests.
4. Prove the staging backup/restore procedure against a separate isolated
   restore target.
5. Provision production on a different, empty managed PostgreSQL database with
   separate credentials, roles, backup policy, and provider configuration.
6. Apply and verify the same Alembic head in production before traffic, then
   prove its backup/restore procedure against an isolated restore target.
7. Point the web service and all four crons to that one production database and
   verify that no staging, test, or legacy rows are present.
8. Keep `NYAYSETU_CUTOVER_TARGET_URL` unset. Do not run the SQLite importer or
   perform legacy user, booking, or payment reconciliation for this release.

Production must use Alembic, not `create_all()`, as the upgrade mechanism.

### Contingency: future legacy import (not part of the current release)

The following workflow applies only if a recorded business decision changes
the fresh-release scope and a separately reviewed migration, reconciliation,
rollback, and data-governance plan authorizes an existing SQLite data import:

1. Inventory the live schema, enum values, duplicates, nulls, and orphaned
   payment records.
2. Stop every writer, create the source through SQLite's Online Backup API or
   CLI `.backup`, and prove restore. Never raw-copy a live WAL database.
3. Set `DATABASE_URL` explicitly to a separate disposable working backup and
   `AUTO_CREATE_SCHEMA=false`; run Alembic `upgrade head`, `current`, and
   `check`; then clear both variables. Never run Alembic against the untouched
   restore artifact. After every process closes, use SQLite's backup mechanism
   again to create a different frozen regular non-symlink artifact with no
   adjacent WAL/journal sidecars.
4. Apply and verify the same Alembic head on an empty PostgreSQL target with
   `current` and `check`.
5. Set `NYAYSETU_CUTOVER_TARGET_URL` to a short-lived managed PostgreSQL
   credential and run the default read-only preflight:

   ```text
   python -m jobs.migrate_sqlite_to_postgres --source-sqlite <frozen-backup.db>
   ```

6. Only after `status=ready` and recorded approval, run the atomic import:

   ```text
   python -m jobs.migrate_sqlite_to_postgres --source-sqlite <frozen-backup.db> --confirm-import IMPORT_SQLITE_COPY_INTO_EMPTY_POSTGRESQL
   ```

   Clear `NYAYSETU_CUTOVER_TARGET_URL` immediately. Never put the target URL on
   the command line; the utility deliberately ignores application
   `DATABASE_URL`.
7. Validate row counts, sampled records, IDs, sequences, constraints,
   timestamps, fulfilment/inbound-claim backfills, and capacity.
8. Reconcile every pending/paid/completed booking against Razorpay.
9. Point the web service and all four crons to the same intended PostgreSQL URL.
10. Test signed webhooks, operator queues, reminders, reconciliation,
    maintenance dry-run, and rollback before live cutover.

## Future schema work

- Booking status-transition/audit history.
- Automated advocate matching, eligibility/conflict evidence, and user
  notification.
- User-requested reschedule/cancellation and controlled provider refund,
  settlement, and chargeback workflows.
- Support comments and individually authenticated actor identity/RBAC.
- Data-subject requests and deletion/anonymisation ledger.
- Extend reviewed retention to additional categories with legal holds.
- Strong foreign keys where migration analysis confirms safe relationships.
