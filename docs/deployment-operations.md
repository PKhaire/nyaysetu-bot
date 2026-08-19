# Deployment and Operations Runbook

This runbook is the release gate for NyaySetu. It assumes the repository root
contains `app.py`, `render.yaml`, and `.python-version`.

The approved launch path is a fresh first release: create a new empty managed
PostgreSQL database and do not import old-bot users, bookings, or payment
records. The SQLite cutover section remains documented only as a contingency
if that business decision changes.

## Target topology

```text
Internet
  |-- Meta WhatsApp --> Render web service --|
  |-- Razorpay ------> Render web service ----+--> managed PostgreSQL
                                              |
Render cron: python -m jobs.process_outbox --|
                                              +--> Amazon SES v2
                                              +--> Meta document delivery (optional)
Render cron: python -m jobs.reconcile_payments --> Razorpay API + review queue
Render cron: python -m jobs.consultation_reminders -> durable reminder jobs
Render cron: python -m jobs.maintenance ---------> retention/risk report
```

Production requirements:

- Python 3.11.15.
- Gunicorn using `gunicorn --config gunicorn.conf.py app:app`, with exactly one
  `gthread` worker and eight threads.
- Managed PostgreSQL in the same Render region as the services.
- A separate outbox cron run every minute.
- A bounded payment-reconciliation cron run every five minutes.
- A bounded reminder scheduler run every ten minutes; it is inert until
  approved template pairs are configured.
- A separate bounded maintenance cron run daily.
- Separate staging and production credentials and databases.
- Central logs, actionable alerts, database backups, and an on-call owner.

SQLite is limited to local development and tests. Do not attach a persistent
disk as a substitute for PostgreSQL: webhook idempotency, slot capacity, and
outbox claiming require shared transactional state.

Python 3.11 is retained as the compatibility line for this release, but it is
already in security-fixes-only support through October 2027. Schedule and
complete a tested newer-Python upgrade well before that date.

## Environment separation

Use distinct resources for each environment:

| Resource | Staging | Production |
| --- | --- | --- |
| Meta app/number | test app or test number | approved production app/number |
| Razorpay | test keys and webhook | live keys and webhook |
| Database | staging PostgreSQL | production PostgreSQL |
| Amazon SES | verified staging identity/destination in the selected region | verified production identity/domain, production access, and approved operational recipients |
| AI | local first; provider test key if approved | separately approved key/model |
| Admin access | unique token/password/signing secret | distinct production token/password/signing secret |

Never point a staging webhook at the production database or reuse a live
Razorpay webhook secret in staging.

## Local development

PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m flask --app app run
```

The Flask CLI loads `.env`; Gunicorn does not. Keep the local database and all
real credentials out of source control.

Minimum non-integration local values:

```text
ENV=development
DATABASE_URL=sqlite:///./nyaysetu.db
AI_PROVIDER=local
RAZORPAY_MODE=test
ALLOW_INSECURE_WEBHOOKS=false
```

Set `ALLOW_INSECURE_WEBHOOKS=true` only to replay unsigned fixtures on a local
machine. Signed fixtures are preferred.

## Render Blueprint

`render.yaml` defines:

- `nyaysetu-bot-backend`: existing public web service with
  `api.nyaysetu.in` and `/health/ready`.
- `nyaysetu-outbox`: one-minute cron that processes a bounded outbox batch and
  exits.
- `nyaysetu-payment-reconciliation`: five-minute exact-evidence Razorpay safety
  net.
- `nyaysetu-consultation-reminders`: ten-minute, template-gated reminder
  scheduler.
- `nyaysetu-maintenance`: daily cron that runs one bounded housekeeping/risk
  batch and exits.

All five services are declared in Singapore with
`autoDeployTrigger: off`. Release the same approved commit manually. The exact
process contract is:

| Phase/service | Command |
| --- | --- |
| Build | `python -m pip install --disable-pip-version-check --no-deps -r requirements.lock && python -m pip check` |
| Web pre-deploy | `python -m alembic -c alembic.ini upgrade head` |
| Web | `gunicorn --config gunicorn.conf.py app:app` |
| Outbox | `python -m jobs.process_outbox` |
| Payment reconciliation | `python -m jobs.reconcile_payments --limit 100` |
| Consultation reminders | `python -m jobs.consultation_reminders` |
| Maintenance | `python -m jobs.maintenance --batch-size 500 --fail-on-risk` |

`requirements.lock` pins the complete production dependency graph. `--no-deps`
prevents resolver drift during deploy, and `pip check` fails the build if the
lock is incomplete or inconsistent. Update and audit the lock through a
reviewed dependency change; do not hand-install a missing package in a running
service.

`sbom.cdx.json` is the deterministic CycloneDX 1.5 offline inventory for that
lock. Regenerate it through `python -m jobs.generate_sbom` when the lock changes;
CI uses `python -m jobs.generate_sbom --check` to reject stale or mismatched
inventory. SBOM generation does not contact an advisory service and does not
report whether a component is vulnerable. The scheduled weekly `pip-audit`
against `requirements.lock` remains the time-sensitive vulnerability gate.

The Blueprint does not declare a database. `DATABASE_URL` is deliberately
`sync: false` so an infrastructure sync cannot attach a new empty database to
a live bot. On an existing Blueprint, Render ignores newly added `sync: false`
variables; add or rotate them in the Dashboard.

`RAZORPAY_MODE` is also operator-supplied so a newly created staging service
cannot silently inherit live mode. Enter `test` in staging and `live` only in
the approved production service.

Cron database and least-privilege operational values use Render `fromService`
references to the web service. This prevents accidental divergence without
giving every cron every credential. Render refreshes these references on
Blueprint sync, so after a shared secret/value rotation, sync/redeploy every
affected service and verify it before closing the change.

The declared region is Singapore. Place PostgreSQL in the same region after
legal/privacy review of the real data flow. Render cannot change the region of
an existing service in place, so an existing service elsewhere requires a
separately rehearsed migration rather than an in-place Blueprint edit.

The one-process, threaded Gunicorn configuration is a correctness constraint,
not a sizing suggestion. `gunicorn.conf.py` sets `workers = 1`, retains bounded
threaded I/O concurrency, and its startup hook rejects a worker-count override.
Within that process, rate-limit/cooldown and maintenance-notice state plus the
AI response cache are lock-protected, pruned, and hard-bounded for long-lived
operation. Before adding any web worker or instance, move per-user ordering
locks, those state stores, caches, and circuit breakers to shared
infrastructure and load-test signed webhook traffic.

### Separate Render staging setup

The committed `render.yaml` is production-only: it deliberately sets
`ENV=production` on all five services. Do not sync that Blueprint into a
staging environment and then merely replace the payment key.

Create a separate Render staging environment from the same immutable release
commit:

1. Create a staging web service with the same build, pre-deploy and start
   commands shown above and set its health path to `/health/ready`.
2. Set `ENV=staging`, `AUTO_CREATE_SCHEMA=false`,
   `ALLOW_INSECURE_WEBHOOKS=false`, `RAZORPAY_MODE=test`, an isolated staging
   PostgreSQL `DATABASE_URL`, and staging-only Meta, Razorpay, Amazon SES,
   policy/contact and random admin/AI-safety values.
3. Leave both legal-review values empty while the candidate is under review,
   or set both to the same currently approved content version/date. A partial
   or stale pair is rejected.
4. Create separate staging cron services from the same commit using the exact
   outbox, reconciliation, reminder and maintenance commands/schedules above.
   Give them only their documented staging values, and point every cron at the
   staging database.
5. Require staging `/health/ready` to return `200`, report
   `environment=staging`, `backend=postgresql`, the expected Alembic revision,
   and `configuration=ok`. It rejects SQLite, automatic schema creation, live
   Razorpay mode/keys and unsigned-webhook mode.
6. Connect only staging provider webhooks and synthetic test users. Never use
   the production domain, number, keys, recipients or database.

After staging acceptance, deploy the committed production Blueprint separately
with live-only values and the approved legal-content review pair.

## Production configuration

### Core provider/database settings

```text
ENV=production
DATABASE_URL=postgresql://...
AUTO_CREATE_SCHEMA=false
WHATSAPP_TOKEN=...
WHATSAPP_PHONE_ID=...
WHATSAPP_VERIFY_TOKEN=...
WHATSAPP_APP_SECRET=...
WHATSAPP_APP_SECRET_PREVIOUS=
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
RAZORPAY_WEBHOOK_SECRET_PREVIOUS=
RAZORPAY_MODE=live
BOOKING_PRICE=499
```

The database URL is normalised to the Psycopg 3 SQLAlchemy driver by the
application. Prefer the provider's internal connection string. Require TLS
according to the database provider's instructions and restrict external
database access.

### Additional production-readiness and operational settings

```text
SES_REGION=ap-south-1
SES_FROM_EMAIL=...
SES_CONFIGURATION_SET=...
SES_CONNECT_TIMEOUT_SECONDS=5
SES_READ_TIMEOUT_SECONDS=15
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=
BOOKING_NOTIFICATION_EMAILS=...
SUPPORT_NOTIFICATION_EMAILS=...
PAYMENT_RECONCILIATION_EMAILS=...
SUPPORT_PHONE=...
SUPPORT_EMAIL=...
PRIVACY_EMAIL=...
PRIVACY_POLICY_URL=...
TERMS_OF_SERVICE_URL=...
REFUND_POLICY_URL=...
CANCELLATION_POLICY_URL=...
AI_CONSENT_VERSION=...
BOOKING_TERMS_VERSION=...
CASE_BRIEF_CONSENT_VERSION=case-brief-sharing-2026-08
LEGAL_CONTENT_VERSION=...
LEGAL_CONTENT_REVIEWED_VERSION=...
LEGAL_CONTENT_REVIEWED_ON=YYYY-MM-DD
ADMIN_TOKEN=...
ADMIN_PASSWORD=...
SECRET_KEY=...
AI_SAFETY_IDENTIFIER_SECRET=...
SUPPORT_SLA_HOURS=24
PAYMENT_RECONCILIATION_LOOKBACK_DAYS=14
OUTBOX_COMPLETED_TTL_DAYS=30
CASE_BRIEF_UNATTACHED_TTL_DAYS=7
```

Production `/health/ready` requires both groups. It also validates live
Razorpay mode and an `rzp_live_...` key ID of at least 16 characters; minimum
lengths of 32 for the WhatsApp app secret/token, admin token, browser-session
signing secret and AI secret, 16 for the admin password, WhatsApp verify token,
and Razorpay API/webhook secrets; valid SES
region/from-address, an AWS access-key ID of at least 16 characters, an AWS
secret access key of at least 32 characters, and an optional session token of at
least 16 characters; a numeric WhatsApp phone ID; valid email addresses; HTTPS
policy URLs; current Alembic revision; disabled automatic schema creation; and a
legal-content reviewed version exactly matching the configured content version
with a valid non-future review date. A nonempty
`WHATSAPP_APP_SECRET_PREVIOUS` must be at least 32 characters and a nonempty
`RAZORPAY_WEBHOOK_SECRET_PREVIOUS` at least 16. This is configuration
validation, not evidence that counsel approved the content or that any provider
is reachable.

### Amazon SES production setup

The application calls Amazon SES API v2 over HTTPS through boto3; it does not
require an SMTP username/password or a locally installed mail server.

1. Select `SES_REGION` first. SES identities, sandbox/production status, and
   configuration sets are regional, so create and test all of them in that same
   region.
2. Verify `SES_FROM_EMAIL` or, preferably, its domain. Publish the SES DKIM
   records and establish SPF and DMARC for the sending domain.
3. Request production access for that SES account/region. While it remains in
   the sandbox, both sender and recipient restrictions prevent a real
   operational launch.
4. Create a runtime IAM identity with only `ses:SendEmail`, scoped to the
   intended identity where the IAM policy supports it. Store
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and any temporary
   `AWS_SESSION_TOKEN` only in Render's secret environment.
5. Create `SES_CONFIGURATION_SET` with approved event destinations and alert on
   bounces, complaints, rejects, delays, and sustained delivery failures.
   NyaySetu requires this value in staging and production.
6. Send only to approved operational mailboxes. The service deduplicates
   recipients, places them in BCC, and rejects more than 50 destinations before
   calling SES.
7. Exercise success, provider rejection, timeout, bounce, and complaint cases
   in staging. The boto3 client performs no immediate SDK retry; a failed or
   ambiguous attempt returns to the durable outbox so retry timing remains
   auditable and bounded. SES `SendEmail` does not provide an idempotency token:
   if a network timeout happens after provider acceptance, a later outbox retry
   can create a duplicate. The approved delivery contract is therefore
   at-least-once; operators use the stable event type/record ID in the subject
   and SES tags to recognise duplicates.

Provider-error logs and alerts must remain privacy-minimised: retain the
exception class, safe provider error code, recipient count, and aggregate
event/status only. Do not record recipient addresses, subject/body content,
credentials, raw provider responses, or outbox payloads.

The web and outbox cron must share the exact same `DATABASE_URL`,
`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, WhatsApp API version, Amazon SES values,
AWS credentials, notification recipients, and `AI_SAFETY_IDENTIFIER_SECRET`. The Blueprint
inherits them from the web service. They let the outbox finish durable
payment-success messages, email, optional receipt delivery, and stable
pseudonymous log correlation. Razorpay API and webhook secrets are not required
by the outbox and should remain scoped to the web service. Keep
`AUTO_SEND_RECEIPTS=false` until document delivery and temporary-file deletion
pass staging.

The maintenance cron shares the database and receives the same retention,
support-SLA, payment-lookback, and payment-link-expiry policy values as the web
service. The payment-reconciliation cron additionally receives
`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, mode, timeout, lookback, and
notification settings; keep the API credentials out of the outbox, reminder,
and maintenance services. The reminder scheduler and outbox share catch-up and
exact per-language template pairs so a cleared template disables scheduling
and sending.

### AI settings

Safe initial production setting:

```text
AI_PROVIDER=local
```

Optional provider settings:

```text
AI_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

or:

```text
AI_PROVIDER=claude
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=...
```

`AI_PROVIDER=auto` follows `AI_PROVIDER_ORDER` and ends with the local fallback.
Model names, prices, retention, and availability change; review them before
each change instead of relying indefinitely on the sample defaults.

Third-party AI may be enabled only after:

- legal counsel approves prompts, disclaimers, and supported use cases;
- privacy review covers purpose, consent, data transfer, provider terms, and
  retention;
- red-team and factual evaluation passes in English, Hindi, and Marathi; and
- cost, latency, provider-error, and emergency-escalation alerts exist.

PII scrubbing is best effort. Users must be told not to submit identity
documents, evidence, privileged communications, or unnecessary case facts.

## Fresh PostgreSQL launch path

The current release is a clean first release and does not import the old bot's
SQLite data:

1. Provision separate empty managed PostgreSQL databases for staging and
   production in the approved region.
2. Set `AUTO_CREATE_SCHEMA=false`; run Alembic `upgrade head`, `current`, and
   `check` against staging.
3. Complete the full staging acceptance suite with synthetic records and
   Razorpay test mode.
4. Apply the same Alembic revision to the still-empty production database.
   Never copy staging rows into production and never point staging services at
   the production connection.
5. Point the production web service and all four production cron jobs to that
   one production connection. Require `/health/ready` to report PostgreSQL,
   the expected revision, complete live configuration, and the exact approved
   legal-content review version/date.
6. Enable the managed backup policy for new production data and prove a
   restore in an isolated environment after launch. This is operational
   protection for new users, not an import of the old bot.

## Legacy SQLite import contingency (not authorised for this launch)

Production uses baseline revision `20260729_01` and current head
`20260818_01`; automatic `create_all()` is disabled and `/health/ready`
requires the expected head. The baseline is additive and contains
compatibility/backfill logic for pre-Alembic databases.
The following utility is retained only for a separately approved future
legacy-data project. It is not part of the clean first-release procedure above
and must not be run against production under the current launch approval.

### One-shot cutover utility contract

`jobs.migrate_sqlite_to_postgres` is a fail-closed copier, not a backup tool and
not a recurring sync:

- Never point `--source-sqlite` at the live mutable database. During the
  maintenance window, first use SQLite's Online Backup API or the SQLite CLI
  `.backup` command to create a separate artifact, close every connection, and
  retain an untouched restore copy.
- Prepare a separate working backup at Alembic head, then create the frozen
  import artifact from that working copy with the SQLite backup mechanism.
  The utility requires the source and target to have revision `20260818_01`
  and the full current table/column shape.
- The source must be a regular non-symlink file with no adjacent `-wal`,
  `-journal`, or `-shm` sidecar. It is opened immutable/read-only and checked
  with SQLite integrity/foreign-key checks plus a before/after fingerprint.
- The PostgreSQL target must be a managed-style URL with host, database,
  username, and password, already migrated to Alembic head, and all application
  tables must be empty.
- The utility never reads `DATABASE_URL` and never accepts the target URL as a
  command argument. Supply it only through the dedicated
  `NYAYSETU_CUTOVER_TARGET_URL` environment variable and clear that variable
  immediately after the controlled session.

Prepare the current-head source in an isolated operator shell. First use
SQLite's backup mechanism to derive a disposable working copy from the
restore-tested backup. Select that working copy explicitly before running
Alembic:

```powershell
$env:DATABASE_URL = 'sqlite:///C:/secure-cutover/nyaysetu-working.db'
$env:AUTO_CREATE_SCHEMA = 'false'
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current
python -m alembic -c alembic.ini check
Remove-Item Env:DATABASE_URL
Remove-Item Env:AUTO_CREATE_SCHEMA
```

Never run that sequence against the untouched restore artifact. After every
Alembic process has exited, verify no process holds the working database, then
use SQLite's Online Backup API or CLI `.backup` again to produce a different
frozen import artifact. Close the backup process and verify that the frozen
artifact has no WAL, SHM, or journal sidecars.

In a separate clean shell, select the empty managed target explicitly, apply
and verify Alembic head, and clear the application variable before invoking the
cutover utility:

```powershell
$env:DATABASE_URL = '<short-lived-managed-postgresql-url>'
$env:AUTO_CREATE_SCHEMA = 'false'
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current
python -m alembic -c alembic.ini check
Remove-Item Env:DATABASE_URL
Remove-Item Env:AUTO_CREATE_SCHEMA
```

PowerShell preflight (default, no writes):

```powershell
$env:NYAYSETU_CUTOVER_TARGET_URL = '<short-lived-managed-postgresql-url>'
python -m jobs.migrate_sqlite_to_postgres --source-sqlite <frozen-backup.db>
```

Only after the JSON preflight reports `status=ready`, backup restore is proven,
the target is confirmed disposable/empty, and the go/no-go owner approves,
perform the import:

```powershell
python -m jobs.migrate_sqlite_to_postgres --source-sqlite <frozen-backup.db> --confirm-import IMPORT_SQLITE_COPY_INTO_EMPTY_POSTGRESQL
Remove-Item Env:NYAYSETU_CUTOVER_TARGET_URL
```

If preflight or import fails, clear `NYAYSETU_CUTOVER_TARGET_URL` before
investigating or opening another shell; never leave the cutover credential in a
general operator environment.

Import takes transaction-scoped exclusive locks on all target application
tables, copies in deterministic bounded batches, verifies every source/target
count, resets PostgreSQL integer-key sequences, and commits atomically. Any
failure rolls back the target transaction and returns privacy-safe JSON with
exit `2`; preflight/import success returns `0`. A successful target is no
longer empty, so the command refuses an accidental second import.

### Legacy import rehearsal

1. Create an isolated staging PostgreSQL database.
2. Enter a simulated maintenance window and create/restore-test an untouched
   SQLite backup through SQLite's backup mechanism; never copy an active WAL
   file set ad hoc.
3. Follow the explicit working-copy environment sequence above; never upgrade
   the untouched restore artifact. Close all processes and use SQLite's backup
   mechanism again to make the distinct frozen current-head import artifact.
4. Follow the explicit target environment sequence above to apply and verify
   Alembic head on the empty staging PostgreSQL target.

5. Run the cutover utility preflight, review its per-table counts, then run the
   exact confirmed import against the still-empty staging target.
6. Validate foreign keys, enum/status values, timestamps, unique constraints,
   sequence values, inbound-claim backfill, and paid-fulfilment backfill.
7. Compare table counts and sampling hashes where appropriate.
8. Run `python -m jobs.reconcile_payments --limit 100` in test mode and
   reconcile every pending, paid, and completed booking against Razorpay.
9. Run `python -m jobs.maintenance --dry-run --batch-size 500 --fail-on-risk`
   and review every reported risk/deletion category.
10. Start staging against PostgreSQL and run the full acceptance suite.
11. Restore the untouched backup into a separate environment to prove recovery.

### Legacy import cutover

1. Announce and enable a short maintenance window.
2. Stop web and all cron writers, then confirm no process holds the SQLite
   database.
3. Capture a final restorable SQLite backup with the backup mechanism; record
   checksum/location and preserve it unchanged.
4. Follow the explicit working-copy sequence above, never the untouched
   artifact; close every process, use SQLite's backup mechanism to create the
   distinct frozen import artifact, and verify no sidecars remain.
5. Apply Alembic head to the empty PostgreSQL target, run preflight, obtain
   go/no-go approval, and execute the exact confirmed one-shot import.
6. Verify the current revision/model parity and reconcile bookings/payments
   before accepting traffic.
7. Set the same PostgreSQL `DATABASE_URL` on web, outbox, reconciliation,
   reminder, and maintenance services.
8. Deploy and require `/health/ready` to report `backend=postgresql` and the
   expected schema revision.
9. Test one signed Meta message and one Razorpay controlled flow.
10. Run a maintenance dry-run; do not enable destructive policy outside the
   approved retention scope.
11. Disable maintenance mode and monitor closely.
12. Retain the untouched SQLite backup and old environment read-only through
    the agreed rollback window.

Do not perform a dual-write cutover without implementing and testing an
explicit consistency design.

Every later schema-changing release must add a frozen, reviewed Alembic
revision and rehearse upgrade, compatibility rollback, and re-upgrade. Never
edit revisions `20260729_01` or `20260818_01` after either has been applied to
a shared environment.

## Webhook configuration

### Meta WhatsApp

URL:

```text
https://<host>/webhook
```

Configure the same `WHATSAPP_VERIFY_TOKEN` in Meta and Render. Production POST
requests must carry a valid `X-Hub-Signature-256` generated with
`WHATSAPP_APP_SECRET` or the temporarily configured
`WHATSAPP_APP_SECRET_PREVIOUS`.

Subscribe only to required WhatsApp events. Preserve Meta message IDs in test
fixtures to verify duplicate delivery. Monitor 4xx signature failures and 5xx
processing failures separately.

`WHATSAPP_API_VERSION` is pinned operationally, not forever. Review Meta's
version lifecycle at least quarterly and regression-test before changing it.

### Razorpay

URL:

```text
https://<host>/payment/webhook
```

Subscribe to the exact payment-link paid event expected by the application.
Use a webhook secret that is different from the API key secret. Validate:

- signed raw payload verification;
- independent authenticated GETs of the current Payment Link and Payment before
  entitlement;
- exact paid-link/captured-payment identity, single full capture,
  `captured=true`, and zero/no refund state;
- INR, stored booking amount, reference, booking ID/token notes, and
  payment-link ownership;
- event/payment idempotency;
- terminal manual payment-review dispositions remain authoritative over delayed
  events;
- delayed and duplicate delivery; and
- provider/current-resource failure returns `503` without entitlement, while
  invalid current evidence enters durable review and returns `202`.

Start in `RAZORPAY_MODE=test`. Do not switch to live keys until the complete
payment, notification, duplicate, and reconciliation scenarios pass.

### Zero-downtime signing-secret rotation

Dual-secret validation applies only to Meta app signatures and Razorpay
webhook signatures:

1. Put the currently active secret in the corresponding `_PREVIOUS` variable
   and the new secret in the primary variable. The previous Meta app secret must
   remain at least 32 characters and the previous Razorpay webhook secret at
   least 16, or production readiness will remain closed.
2. Deploy and verify that deliveries signed with the old secret still pass.
3. Change the provider dashboard to the new secret and verify newly signed
   deliveries plus duplicate/retry behavior.
4. Keep the previous value only through the agreed provider retry/rollback
   window.
5. Clear the `_PREVIOUS` variable, redeploy, and confirm old signatures fail.

The Blueprint predeclares both previous-secret variables as operator-supplied
web-service secrets. On an existing Blueprint, add them manually in the
Dashboard because newly added `sync: false` values are not populated by a
sync. Keep them empty except during the controlled rotation window. These
signing secrets are not shared with any cron.

Never use the previous-secret slots as indefinite fallback credentials. The
Meta verification token, WhatsApp access token, Razorpay API key secret,
database, AWS/SES, admin, and AI secrets require their own provider-specific
rotation procedures.

## Durable outbox

Payment/support side effects and user-flow replies whose failed send is known
safe to retry are recorded in PostgreSQL. The web process may attempt immediate
delivery, and the cron recovers jobs left behind after a restart or provider
failure. A conversation-delivery retry sends only the committed reply; it never
re-enters the inbound business flow. The web fast path permits at most 32
queued/in-flight tasks; saturation safely skips that optional kick because the
durable one-minute cron remains authoritative.

Manual drain:

```text
python -m jobs.process_outbox
```

Operational checks:

- cron runs once per minute and exits successfully;
- web and cron use the same database;
- eligible `PENDING` jobs are moving to `COMPLETED`;
- retries respect `OUTBOX_MAX_ATTEMPTS` and exponential backoff;
- `DEAD` jobs page an operator and are reconciled manually;
- ambiguous conversational transport outcomes are not automatically resent;
- completed/dead `whatsapp_conversation_delivery` payloads contain no recipient
  or reply body; and
- email/provider errors do not expose the job payload or user PII in logs.

The runner handles 25 eligible jobs per invocation by default. Alert on queue
age as well as queue length. If sustained volume exceeds the bounded drain,
implement a continuously polling worker with transactional claiming rather
than increasing cron overlap.

Exit `2` means eligible work still remains or at least one job is `DEAD`; a
future-scheduled retry alone is reported as deferred and exits `0`.

## Payment reconciliation

Controlled run:

```text
python -m jobs.reconcile_payments --limit 100
```

The job examines at most 200 recent-first unprocessed `PENDING`/`EXPIRED` links
inside `PAYMENT_RECONCILIATION_LOOKBACK_DAYS`. For a possible capture it fetches
both the Payment Link summary and current Payment resource. It automatically
recovers only one exact captured, non-refunded INR payment whose provider link,
reference/notes, amount, payment identity/status, and capture/refund state match
the booking. Every ambiguous observation is preserved in
`payment_reconciliations`; it never guesses from a screenshot, partial/refunded
capture, malformed response, or user text.

Manual `RESOLVED`, `REFUND_INITIATED`, `REFUNDED`, and `IGNORED` dispositions
are terminal and authoritative. Neither this command nor a delayed webhook
reopens them.

The command prints privacy-minimised JSON. Exit `0` means all provider lookups
completed, including when human review is required. Exit `2` means a
configuration/provider error occurred. Review open items through
`GET /admin/payment-reconciliations`; disposition mutations require
`X-Operator-ID` and a resolution note.

`render.yaml` schedules one bounded run every five minutes with the web
database and scoped Razorpay API credentials. Alert on command exit `2`, stale
open items, and any recovered capture; retain a staffed owner for every review
and incident.

## Consultation reminders

Dry-run:

```text
python -m jobs.consultation_reminders --dry-run --batch-size 100
```

The Blueprint invokes `python -m jobs.consultation_reminders` every ten minutes.
With all reminder template pairs empty, this is a successful no-op. When an
exact Meta-approved template name and language code are configured for a
24-hour or 2-hour/user-language combination, the scheduler enqueues
deduplicated work only for due `PAID` bookings whose fulfilment is
`UNASSIGNED`, `ASSIGNED`, or `CONFIRMED`; imminent 2-hour work is prioritized.
It prints a PII-free JSON report, exits `0` for success/no-op, and exits `1`
after a scheduling failure and rollback.

The outbox rechecks the live template pair, paid/fulfilment state, scheduled
time, and catch-up window immediately before sending. Rescheduled, completed,
cancelled, refund-review, stale, or newly unconfigured work completes without a
send. The template contract has exactly two positional body variables:
formatted appointment date and time.

Do not populate a template pair until the exact language/purpose is approved by
Meta, purpose-specific opt-in and suppression policy are approved, and staging
proves localized rendering, deduplication, reschedule/refund suppression, and
quality monitoring. Clearing a pair is the immediate send-disable control.

## Retention maintenance and operational-risk signal

Dry-run before the first scheduled mutation and after every retention-policy
change:

```text
python -m jobs.maintenance --dry-run --batch-size 500 --fail-on-risk
```

The daily Blueprint command is:

```text
python -m jobs.maintenance --batch-size 500 --fail-on-risk
```

One transaction expires stale pending bookings and deletes only eligible
unattached case briefs, `DONE` webhook/inbound events, old analytics, and old
`COMPLETED` outbox jobs. A case brief attached to a booking is preserved. It
also preserves users, bookings, fulfilment/payment/support evidence, feedback,
conversations, dead/failed jobs, unmatched/failed webhooks, nonterminal inbound
claims, and legacy message claims.

The JSON report also counts overdue/missing-SLA fulfilment and support work and
stale payment reviews. Exit codes are:

- `0`: successful run;
- `1`: maintenance failed and rolled back; and
- `2`: successful run with `--fail-on-risk`, but
  `operational_risks.summary.alert_required` is true.

The scheduled Blueprint command includes `--fail-on-risk`; Render therefore
records a failed cron run when the maintenance transaction fails or the
successful report requires operator attention. Route exit `2` and the JSON
`alert_required` detail to the fulfilment/support/payment-review owner.

## Operator appointment-console procedure

Human operators open `https://api.nyaysetu.in/admin/login`, enter their stable
operator ID and the separately stored `ADMIN_PASSWORD`, then work the
responsive appointment queue at `/admin/appointments`. The signed session
expires after two hours. The console masks contact numbers and never marks an
appointment complete merely because its scheduled time passed. A contact
number is shown only after a stable operator supplies a valid operational
purpose; the reveal is audited. The console also shows the confirmed case brief
and manual contact history.

For every paid booking:

1. Open **Unassigned**, confirm the paid record, scheduled time, consented case
   brief, urgency, and safety flag. Do not request or download identity or
   evidence files through this release.
2. Register or select an active, independently verified advocate. Complete
   eligibility, subject-fit, availability, and conflict checks before
   assignment.
3. Reveal advocate/client contact only for the stated handover purpose.
   Manually notify both parties and record each attempt, channel, outcome,
   notes, and follow-up time. Manual communication is the release path, so Meta
   outbound-template approval is not a launch dependency.
4. Move it to **Confirmed** only after both sides acknowledge the consultation
   arrangement.
5. After the consultation, explicitly choose **Completed** and record a useful
   operator note. This is the authoritative trigger that closes fulfilment and
   enables the user feedback follow-up.
6. For exceptions, record **No show**, **Reschedule required**, or
   **Refund review** with explanatory notes. A refund is terminal only after
   external Razorpay evidence is checked and the reviewed `REFUNDED` action is
   recorded.

The browser password is shared, so restrict distribution and retain operator
IDs for audit attribution. Rotate `SECRET_KEY` to invalidate all active browser
sessions after suspected exposure.

## Operator API procedure

Machine API calls require the shared bearer or `X-Admin-Token`. Every `PATCH`,
`POST`, or `DELETE` additionally requires a stable, non-secret
`X-Operator-ID`; successful mutations append `admin_audit_events` with
before/after state and request ID. Never put the admin token in a URL. Place all
admin routes behind TLS, platform access control, MFA, and restricted operator
network/access policy because application credentials remain shared.

Core queues and actions:

- Support: list and assign/prioritize/progress/resolve tickets; closing requires
  a resolution note.
- Fulfilment: work the SLA-ordered paid-booking queue, assign an active advocate
  or named fulfiller, record allowed state transitions, and capacity-check any
  paid reschedule. Exception/final states require operator notes. Do not record
  a paid cancellation directly from `UNASSIGNED`; use the reviewed
  `REFUND_REVIEW` to `REFUNDED` path after external refund evidence is verified.
  `REFUNDED` sets the booking to `CANCELLED`, preserves payment evidence, and
  clears paid user state only when no other `PAID` booking remains. It also
  terminalizes or creates the exact `REFUNDED` payment review.
- Payment review: inspect captured-payment exceptions and record an explicit
  resolution/refund/ignore disposition with notes. This endpoint records a
  decision; it does not execute a Razorpay refund.
- Availability: create/deactivate date-wide or slot blackouts and capacity
  overrides. Capacity `0` closes that scope. Verify the user-facing date/slot
  list immediately after every change.
- Outbox: inspect state and retry only a terminal failed/dead job after the
  underlying provider/configuration fault is fixed.
- Audit: review recent mutations and correlate them with platform logs/request
  IDs.

Do not mutate production tables directly for routine operations. Restrict
direct database access to incident recovery under an approved, recorded
procedure.

## WhatsApp templates and engagement

Interactive replies within the user-initiated customer-service window can use
session messages. Messages outside that window require Meta-approved templates.
The implemented 24-hour/2-hour reminder scheduler is disabled by empty template
pairs until these gates pass; it is transactional appointment messaging, not a
campaign engine.

Before enabling reminders, re-engagement, receipt delivery, or asynchronous
support updates:

1. Record purpose-specific user opt-in.
2. Obtain template approval for English, Hindi, and Marathi.
3. Store approved names and locales as deployment configuration.
4. Test opt-out, throttling, template rejection, and failed delivery.
5. Track user blocks and Meta quality ratings.

Do not send campaigns from the outbox until a reviewed campaign policy,
frequency cap, suppression list, and consent record exist.

## Pre-deployment gate

- CI compile, high-confidence Ruff checks, tests, lock/SBOM consistency, and
  weekly dependency audit pass.
- CI PostgreSQL Alembic upgrade/check/downgrade/re-upgrade and Gunicorn
  configuration validation pass.
- Release commit is immutable and reviewed.
- Staging uses the exact dependency resolution and Python line.
- Managed backup policy is enabled and an isolated restore rehearsal is
  complete for the new platform; no old-bot database import is required.
- For a SQLite-to-PostgreSQL release, the untouched restore artifact,
  explicitly selected working-copy upgrade, frozen-source preflight/import JSON,
  empty-target evidence, reconciliation, and rollback rehearsal are approved.
- PostgreSQL connection pool budget fits the provider connection limit.
- All required secrets are present and no secret appears in Git history.
- Meta and Razorpay webhook secrets match their dashboards.
- Previous webhook-secret variables are empty unless a documented rotation is
  actively inside its retry/rollback window.
- Amazon SES identity/domain and internal recipients are approved; DKIM/SPF/DMARC
  passes; the account/region has production access; and a least-privilege
  `ses:SendEmail` runtime identity and monitored configuration set are active.
- Fee, capacity, timezone, cutoff, refund/cancellation, and support values are
  approved by the business owner.
- Privacy notice, terms, and AI consent are published and reviewed.
- Maintenance mode is off for the final smoke test.
- Maintenance dry-run categories and operational risks are approved.
- Payment-reconciliation run and every open review item have an owner.
- Reminder template pairs are either all empty, or each populated pair has
  Meta approval, matching language/purpose, documented opt-in, and staging
  evidence.
- Fulfilment/support queues are staffed and availability blackouts/overrides
  match real capacity.
- Rollback owner, on-call owner, and go/no-go decision maker are named.

## Staging acceptance

At minimum:

1. `/health/live` returns 200.
2. `/health/ready` returns 200 and reports PostgreSQL.
3. Meta verification succeeds and invalid verification fails.
4. Invalid WhatsApp and Razorpay signatures are rejected.
5. English, Hindi, and Marathi home/self-service flows render correctly.
6. Booking review does not create a payment link until confirmed.
7. Slot/day capacity holds under concurrent attempts.
8. A Razorpay test payment confirms the intended booking only after the current
   Payment Link and Payment agree on exact ownership, stored amount, a single
   captured payment, and zero refund state.
9. Re-delivering the same payment event creates no duplicate side effects.
10. Make the current-resource lookup fail and verify `503`, no entitlement, and
    safe retry. Supply mismatched/refunded current evidence and verify `202`,
    durable review, and no entitlement.
11. Record each terminal manual payment-review disposition and verify a delayed
    event cannot reopen or override it.
12. A forced notification-provider failure leaves a retryable outbox job.
13. Cron delivery completes the recovered job, including when the 32-task web
    fast path is saturated.
14. A missed exact provider capture is recovered once by
    `python -m jobs.reconcile_payments --limit 100`; ambiguous evidence remains
    unpaid and enters the review queue.
15. Create, assign, and resolve a support ticket and fulfilment item; verify
    audit entries and invalid transitions. Reject direct paid cancellation;
    verify the reviewed refund transition retains payment evidence and clears
    paid user state only when no other `PAID` booking remains.
16. Apply/deactivate a blackout and capacity override; verify live availability.
17. Run maintenance dry-run and `--fail-on-risk`; verify no protected evidence
    is selected for deletion.
18. With templates empty, verify reminder scheduling is a no-op. If enabling
    approved staging templates, verify deduplicated 24-hour/2-hour delivery and
    suppression after reschedule/refund-review/template removal.
19. Support and feedback records are visible only to authorised operators.
20. Logs contain request/event references but no raw phone, question, or legal
    intake content.
21. Per-user/global limits reject menu, support, media, and paid-flow requests
    before branch work and emit no more than one limit notice per user/window.
22. After a committed user-flow transition, inject a known-safe WhatsApp
    connection/config/transient failure. Require `delivery_queued`, one
    deduplicated conversation-delivery job, ignored Meta replay, successful
    outbox delivery, and terminal payload scrubbing.
23. Inject an ambiguous WhatsApp read/protocol failure. Require
    `delivery_not_retried`, a terminal inbound event, and no automatic send job.
24. Against production-like PostgreSQL with two sessions, rehearse the
    webhook/operator race on the same `OPEN` payment review. Operator-first
    `REFUND_INITIATED`/`REFUNDED` must prevent paid entitlement. Webhook-first,
    paused after provider validation and booking/review locking, must serialize
    the operator action after payment commit so the refund workflow revokes
    entitlement. Require no deadlock or lost terminal disposition.

## Release and rollback

Deployment:

1. Deploy staging from the release commit.
2. Complete acceptance and record evidence.
3. Provision the separate empty production database, enable its managed backup
   policy, and verify Alembic head; do not copy staging or old-bot records.
4. Deploy the web service from the approved commit; require successful Alembic
   pre-deploy and current schema readiness.
5. Deploy outbox, reconciliation, reminders, and maintenance from the same
   commit.
6. Check readiness, logs, queue age, operational risks, database connections,
   and webhook delivery.
7. Run a controlled smoke flow and bounded payment reconciliation.
8. Monitor the heightened-observation window.

Rollback the application when error rate, webhook processing, or booking
correctness breaches the agreed threshold. A code rollback is safe only when
the database schema remains backward compatible. For a schema/data incident,
follow the separately rehearsed database recovery plan; never improvise a
destructive restore over the only production copy.

## Monitoring and alerting

Alert on:

- readiness failure or repeated process restart;
- WhatsApp/Razorpay webhook 5xx rate and signature-failure spikes;
- payment received without confirmed booking;
- amount/currency mismatch;
- database errors, pool exhaustion, and connection saturation;
- oldest pending outbox age and any dead outbox job;
- reconciliation command errors, open/stale payment-review items, and recovered
  captures;
- overdue/missing-SLA fulfilment and support items;
- maintenance transaction failure or `alert_required`;
- reminder scheduler failure, due-window backlog, template rejection, or
  ambiguous delivery;
- active inbound claims older than the configured lease;
- Amazon SES/WhatsApp delivery failures, bounces, and complaints;
- AI provider rate limit, latency, or sustained fallback;
- unexpected booking-capacity rejection rate; and
- admin authentication failures.

Recommended dashboard measures:

- inbound messages and active users (privacy-minimised);
- booking funnel and conversion by language/category;
- pending, paid, completed, expired, and cancelled bookings;
- payment confirmation latency;
- external provider success/latency;
- support backlog age;
- fulfilment backlog/status/SLA;
- payment reconciliation status/age;
- active inbound claims and maintenance category counts;
- reminder scheduled/skipped/deduplicated/send outcomes by non-sensitive
  template purpose/language;
- feedback distribution; and
- outbox queue status.

Never use raw phone numbers, user questions, legal descriptions, tokens, full
webhook bodies, or database URLs as log labels.

## Incident runbooks

### Messages arrive but replies fail

1. Check Meta webhook delivery and application 5xx logs.
2. Verify token validity, phone ID, API version, and Meta account status.
3. Test a non-sensitive message from the staging number.
4. Check rate/quality limits and outbound error categories.
5. Keep retries bounded; do not replay an unbounded webhook export.

### Payment succeeded but booking is not confirmed

1. Stop automated manual edits.
2. Confirm the payment, amount, currency, payment-link ID, and capture state in
   Razorpay.
3. Locate the corresponding booking and webhook event by non-sensitive IDs.
4. Inspect `/admin/payment-reconciliations` and determine whether the event is
   pending, failed, duplicate, absent, or already under review.
5. Run one bounded `python -m jobs.reconcile_payments --limit 100` lookup.
6. Retry the signed provider delivery where supported.
7. Correct only through the audited operator procedure; never override
   ambiguous provider evidence.
8. Notify the user through an approved support path.

Never mark a booking paid from a screenshot or user-supplied payment text.

### Outbox backlog

1. Check cron run history and database connectivity.
2. Identify the oldest pending/dead job and error type without logging payload.
3. Restore Amazon SES/Meta configuration or provider availability.
4. Trigger one manual bounded run.
5. Verify idempotent completion before increasing drain capacity.

### Fulfilment/support SLA alert

1. Inspect the maintenance risk report and protected admin queues.
2. Assign an accountable operator/advocate without exposing sensitive text in
   chat or logs.
3. Record valid state transitions and required notes through the admin API.
4. If real capacity is unavailable, apply an audited blackout/capacity override
   and follow the approved reschedule/refund policy.
5. Confirm the audit entry and user communication through an approved channel.

### Database incident

1. Enable maintenance mode if writes may be unsafe.
2. Preserve logs and take a snapshot before repair.
3. Confirm scope with read-only queries.
4. Fail over or restore using the provider's rehearsed procedure.
5. Reconcile payments and bookings before reopening.

### AI provider incident

Set `AI_PROVIDER=local` and redeploy/restart if necessary. Preserve booking and
human support paths. Do not weaken privacy or safety controls to restore AI
availability.

## Maintenance mode

`render.yaml` explicitly sets `MAINTENANCE_MODE=false` on the web service. Since
automatic deploys are off, changing the value requires a controlled Dashboard
environment edit and a manual web redeploy. Record the operator/change ID and
verify the resulting user response.

Enable:

```text
MAINTENANCE_MODE=true
```

`MAINTENANCE_ADMIN_BYPASS` is optional and contains a sensitive WhatsApp
identifier. Use it only for a controlled smoke test, keep it out of logs, and
remove it afterward. It is deliberately absent from the Blueprint and must
remain a manually controlled temporary value.

Disable and verify:

```text
MAINTENANCE_MODE=false
```

Redeploy the web service again and verify an ordinary signed user message
reaches the normal flow. Maintenance mode gates ordinary WhatsApp text/
interactive handling only; it is not a database write freeze. For a cutover or
database-integrity incident, separately stop every applicable web/cron writer
and provider intake as the incident/cutover procedure requires.

## Backups, retention, and secret rotation

- Use managed PostgreSQL automated backups and point-in-time recovery where
  available.
- Perform scheduled restore drills into an isolated environment.
- Encrypt backup exports and restrict them by role and expiry.
- Define retention for users, conversations, bookings, webhook events,
  analytics, feedback, support, and logs.
- Review the bounded maintenance dry-run before enabling deletion. Current
  automation covers only stale pending-booking expiry and approved terminal
  webhook/inbound, analytics, and completed-outbox categories.
- Keep user deletion/anonymisation, legal holds, support/fulfilment/payment
  evidence, and backup-retention decisions in separately approved procedures.
- Rotate Meta, Razorpay, AWS/SES, database, admin, and AI secrets on a schedule
  and after any suspected exposure.
- For Meta app-secret and Razorpay webhook-secret rotation, follow the
  current/`_PREVIOUS` overlap procedure above; clear the previous value after
  the bounded retry/rollback window.
- After rotating any web value inherited by one or more crons, sync the
  Blueprint, redeploy every affected service, and verify the corresponding
  staged operation.
- After rotating `AI_SAFETY_IDENTIFIER_SECRET`, expect provider safety
  identifiers to change; document the privacy/abuse-monitoring impact.

## Document Studio RC8 staging UAT

The Blueprint deliberately keeps `DOCUMENT_STUDIO_ENABLED=false`. To exercise
RC8 on the existing staging service, set all of the following and redeploy:

```text
ENV=staging
DOCUMENT_STUDIO_ENABLED=true
DOCUMENT_STUDIO_UAT_ONLY=true
DOCUMENT_STUDIO_CONSENT_VERSION=document-studio-uat-2026-08
DOCUMENT_STUDIO_PRODUCT_ALLOWLIST=residential_agreement_mh_uat
DOCUMENT_STUDIO_TESTER_WA_IDS=<comma-separated test numbers with country code>
DOCUMENT_STUDIO_DRAFT_TTL_DAYS=7
RAZORPAY_MODE=test
```

Use synthetic data only. Verify `/health/ready` reports `ok=true` with schema
`20260819_01`. The UAT flow must not generate a legal document, payment,
booking, signature, file upload, S3 object or download. The protected
`GET /admin/document-orders` endpoint is metadata-only.

After testing, set `DOCUMENT_STUDIO_ENABLED=false`, redeploy, and verify the
original three-button home. Production readiness deliberately fails if this
UAT flag is enabled on a production-labelled service.

## Known operational limitations

- The Alembic baseline/current head and fail-closed cross-engine import utility are present,
  but real live-data backup/restore, working-copy upgrade, import/reconciliation,
  and rollback results remain external release evidence. Revision
  `20260729_01` registers the baseline, `20260818_01` adds case-brief and
  manual-handover operations, and `20260819_01` adds the staging-only Document
  Studio UAT ledger. Do not rewrite applied revision files.
- Per-user/global limits cover early menu, support, media, and paid-flow
  branches and deduplicate notices, but their state and some other abuse
  controls remain process-local.
- Maintenance deliberately covers only a narrow approved retention scope; it
  is not a legal-hold, privacy-request, or universal deletion system.
- Payment reconciliation is scheduled, but it is a bounded safety net rather
  than settlement/refund accounting and still requires staffed review.
- Admin mutations are audited and the browser console adds signed sessions,
  CSRF protection and login throttling, but access still uses a shared password
  rather than individually verified application credentials/RBAC/MFA.
- The app tracks fulfilment, verified advocate records, consented briefs,
  audited contact reveal, and manual handover events, but independent advocate
  eligibility/conflict review, consultation quality, and refund execution
  remain operational/policy gates.
- Provider health is not included in `/health/ready`.
- The outbox runner is bounded polling, not a high-throughput queue.
- Third-party AI PII filtering cannot be guaranteed.
- Meta template approval remains a future automation task; the current launch
  uses recorded manual assignment/confirmation contact and sends no campaigns.

These limitations do not justify skipping the controls above; they define the
scope for the next hardening increment.

## Authoritative platform references

- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Render Python version selection](https://render.com/docs/python-version)
- [Render health checks](https://render.com/docs/health-checks)
- [Render cron jobs](https://render.com/docs/cronjobs)
- [Python 3.11.15 security release and lifecycle](https://www.python.org/downloads/release/python-31115/)
