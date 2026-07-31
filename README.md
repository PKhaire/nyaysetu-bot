# NyaySetu WhatsApp Legal Information and Booking Bot

NyaySetu is a WhatsApp-first legal information, intake, and paid consultation
booking service for users in India. It supports English, Hindi, and Marathi,
guides users through a transparent appointment flow, confirms Razorpay
payments, and provides self-service appointment and preparation information.

The product is designed for useful, consent-based engagement. AI responses are
general legal information, not legal advice, and the bot must not use
manipulative retention patterns or imply a lawyer-client relationship.

## What the service includes

- Multilingual WhatsApp onboarding and a persistent home menu.
- Consent-gated AI information with deterministic safety checks and local
  fallback content.
- Guided legal category, district, date, and capacity-aware slot selection.
- A review step before creating a Razorpay payment link.
- Signed and idempotent Meta and Razorpay webhook processing. Payment
  entitlement additionally requires exact, current Razorpay Payment Link and
  Payment-resource evidence with no refund.
- Appointment status, preparation checklists, legal guides, privacy, support,
  receipt, and post-consultation feedback flows.
- Deduplicated 24-hour/2-hour appointment reminders that remain disabled until
  exact Meta-approved per-language templates are configured.
- Managed-database support, readiness/liveness probes, privacy-minimised
  analytics, and durable inbound-inbox/outbox processing, including safe
  deduplicated reply retry without replaying committed user-flow state.
- Audited operator queues for support, paid-consultation fulfilment, payment
  reconciliation, outbox recovery, and booking availability controls.
- Alembic-managed schema releases and bounded retention/operational-risk
  maintenance.

## Architecture

```text
WhatsApp user
    |
Meta Cloud API --> Flask webhook --> SQLAlchemy --> PostgreSQL
                         |                 |
                         |                 +--> durable inbound inbox
                         |                 +--> durable outbox --> cron drain
                         |                 +--> fulfilment/reconciliation
                         |
                         +--> local/OpenAI/Claude information provider
                         +--> Razorpay payment links and signed webhook
                         +--> SendGrid notifications
```

SQLite is a development fallback. A managed PostgreSQL database is a production
requirement because booking capacity, webhook idempotency, feedback, support,
analytics, and outbox jobs all require durable shared state.

## Local setup

Prerequisite: Python 3.11.

PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m flask --app app run
```

macOS/Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python -m flask --app app run
```

Flask loads `.env` in local CLI mode through `python-dotenv`. Edit the copied
file before testing real integrations. Gunicorn and Render use platform
environment variables; they must not rely on a deployed `.env` file.

Local SQLite tables are created on startup. To replay unsigned webhook fixtures
locally, set `ALLOW_INSECURE_WEBHOOKS=true` and keep `ENV` different from
`production`. Never use that opt-out in a shared or production environment.

Useful commands:

```powershell
python -m compileall -q app.py admin.py category_labels.py config.py db.py demo_local_ai.py gunicorn.conf.py location_service.py models.py subcategory_labels.py translations.py utils.py migrations services jobs tests utils
python -m ruff check .
python -m pytest -q
python -m pytest -q --cov=app --cov=services --cov-fail-under=60
python -m alembic -c alembic.ini upgrade head
python -m jobs.process_outbox
python -m jobs.maintenance --dry-run --batch-size 500 --fail-on-risk
python -m jobs.reconcile_payments --limit 100
python -m jobs.consultation_reminders --dry-run --batch-size 100
python -m jobs.generate_sbom --check
python -m pip_audit --progress-spinner off -r requirements.lock
```

## Configuration

Start from [.env.example](.env.example). The following settings are launch
critical:

| Area | Required production settings |
| --- | --- |
| Database | `DATABASE_URL` pointing to managed PostgreSQL |
| Meta | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`; optional `WHATSAPP_APP_SECRET_PREVIOUS` during rotation |
| Razorpay | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_MODE=live`; optional `RAZORPAY_WEBHOOK_SECRET_PREVIOUS` during rotation |
| Email | `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `BOOKING_NOTIFICATION_EMAILS`, `SUPPORT_NOTIFICATION_EMAILS` |
| User trust | reviewed `SUPPORT_*`, `PRIVACY_*`, policy URLs, and consent/terms versions |
| Operations | a long random `ADMIN_TOKEN` and `AI_SAFETY_IDENTIFIER_SECRET` |

AI is optional. The Render Blueprint defaults to `AI_PROVIDER=local`. To enable
a third-party provider, set `AI_PROVIDER=openai`, `claude`, or `auto`, provide
the corresponding key and reviewed model setting, and complete the privacy and
legal launch gates below. Never place credentials in Git, logs, support
tickets, or webhook fixtures.

The local provider is a deterministic, versioned knowledge engine rather than
a generative model. Its Legal Guides flow first asks for one of nine legal
areas and then a category-specific issue. English, conversational
Hindi/Hinglish, and Marathi guidance includes:

- questions that help the user organise the matter;
- immediate, non-personalised next steps;
- a document-preparation checklist;
- urgent-risk escalation language;
- state/district-based consultation-routing context;
- a legal-information disclaimer and content-review metadata;
- private helpful/not-helpful feedback and a consultation handoff.

Every content revision must change `LEGAL_CONTENT_VERSION`. Production
readiness remains false until `LEGAL_CONTENT_REVIEWED_VERSION` exactly matches
it and `LEGAL_CONTENT_REVIEWED_ON=YYYY-MM-DD` identifies the date on which a
qualified reviewer approved that revision.

`GET /health/ready` checks database connectivity and the applied Alembic
revision, rejects SQLite and automatic schema creation in staging/production,
and validates strict provider, recipient, support/privacy, HTTPS-policy and
secret configuration. Staging requires Razorpay test keys; production requires
live keys plus an exact content-review version/date pair. Current production
credentials must also meet the enforced format/strength contract: 32 or more
characters for the WhatsApp app secret/token and admin/AI secrets, 16 or more
for the WhatsApp verify token and Razorpay key/webhook secrets, an
`rzp_live_...` key ID, and an `SG.` SendGrid key. A configured previous Meta app
secret must also be at least 32 characters and a configured previous Razorpay
webhook secret at least 16; leave them empty outside a bounded rotation. It does
not prove that policy/counsel approval exists or that SendGrid, Meta, Razorpay,
or an AI provider is currently reachable; external evidence, smoke tests, and
alerts remain necessary.

## HTTP endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Minimal service information |
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Database/configuration readiness |
| `GET /webhook` | Meta webhook verification |
| `POST /webhook` | Signed WhatsApp events |
| `POST /payment/webhook` | Signed Razorpay payment events |
| `GET /admin/metrics` | Aggregate operational metrics |
| `GET/PATCH /admin/support[...]` | Support queue and audited ticket updates |
| `GET/PATCH /admin/fulfillments[...]` | Paid-consultation fulfilment queue and lifecycle |
| `GET/PATCH /admin/payment-reconciliations[...]` | Payment-review queue and dispositions |
| `GET/POST/DELETE /admin/availability[...]` | Blackouts and capacity overrides |
| `GET/POST /admin/outbox[...]` | Outbox inspection and controlled retry |
| `GET /admin/audit` | Audited operator mutation history |

Admin routes require `Authorization: Bearer <ADMIN_TOKEN>` or
`X-Admin-Token: <ADMIN_TOKEN>`. Mutations additionally require a valid
`X-Operator-ID`, and every mutation writes an audit event. Do not put admin
credentials in query strings. The shared token is not a substitute for
platform RBAC, MFA, or individual database access controls.

## Production deployment

[render.yaml](render.yaml) defines:

- one Gunicorn web service with a database-aware readiness check;
- a one-minute cron drain for the bounded durable outbox runner;
- a five-minute exact-evidence payment reconciliation cron;
- a ten-minute reminder scheduler that is inert while approved template pairs
  are empty; and
- a daily bounded maintenance/risk cron.

Every service installs the fully pinned transitive `requirements.lock` with
`--no-deps` and then runs `python -m pip check`; production does not resolve
new transitive versions during a deploy.

The committed `sbom.cdx.json` is a deterministic CycloneDX 1.5 inventory
generated offline from that lock. CI runs
`python -m jobs.generate_sbom --check` to reject drift. The SBOM does not query
a vulnerability service and is not evidence that dependencies are safe; the
weekly `pip-audit` job remains the time-sensitive vulnerability gate.

The web command loads [gunicorn.conf.py](gunicorn.conf.py): exactly one
`gthread` worker with eight threads. Its startup hook rejects a worker-count
override because user ordering, throttles, caches, and circuit breakers still
contain process-local state. Do not add web workers or instances until those
controls use shared infrastructure and PostgreSQL concurrency/load tests pass.

The Blueprint intentionally leaves `DATABASE_URL` as an operator-supplied
secret instead of declaring and immediately attaching a new database. This
prevents a Blueprint sync from silently switching a live bot to an empty
database. Validate a separate fresh PostgreSQL database in staging, then
provision a different empty production database in the same region and supply
its internal connection string to the web service. Sync the Blueprint so all
four crons inherit that exact production connection.

The outbox command processes a bounded batch and exits, which is why it is a
cron job instead of a long-running worker. Every cron inherits the same
`DATABASE_URL` and only the additional settings it needs. The outbox receives
WhatsApp/SendGrid delivery settings plus the reminder policy it must recheck at
send time; reconciliation receives Razorpay API credentials and notification
recipients; reminders receive template/catch-up policy; and maintenance receives
retention/risk policy. After rotating a shared value, sync the Blueprint,
redeploy every affected service, and verify resolved values. Keep
`AUTO_SEND_RECEIPTS=false` until receipt delivery has passed staging. Razorpay's
webhook signing secret remains web-only.

The web Blueprint explicitly sets `MAINTENANCE_MODE=false`. Enabling or
disabling the user-facing gate requires a controlled environment change and
manual web redeploy because automatic deploys are off. The optional
`MAINTENANCE_ADMIN_BYPASS` is never predeclared; add it only for a controlled
smoke test and remove it immediately afterward.

The payment reconciler runs every five minutes with web-service database and
Razorpay API credentials. It checks both Payment Link and current Payment
resources and auto-recovers only exact, captured, non-refunded evidence. Alert
on exit code `2` and review every ambiguous item through the protected queue.
The payment webhook independently performs the same current dual-resource
verification before granting entitlement; a provider lookup failure remains
retryable, while invalid current evidence enters review without paying the
booking. A final operator payment-review disposition remains authoritative over
later delivery.

The reminder scheduler runs every ten minutes but enqueues nothing until an
exact Meta-approved 24-hour or 2-hour template name/language pair is configured
for the user's language. The outbox rechecks live template and booking/
fulfilment eligibility immediately before sending. Keep every pair empty until
opt-in, template approval, localized rendering, frequency, and suppression
gates pass.

Read [the deployment and operations runbook](docs/deployment-operations.md)
before changing the production Blueprint. Do not deploy directly from an
untested working tree.

## Fresh database release gate

The repository includes Alembic revision `20260729_01`. Render runs
`python -m alembic -c alembic.ini upgrade head` before the web release, and
staging and production readiness require that exact revision. Automatic
`create_all()` is disabled by default in both environments and remains only a
local-development/test compatibility path.

This release intentionally imports no old-bot data:

1. Create isolated empty managed PostgreSQL databases for staging and
   production. Never run staging tests against the production database.
2. Set `AUTO_CREATE_SCHEMA=false` and run Alembic `upgrade head`, `current`,
   and `check` against staging.
3. Complete signed Meta, Razorpay test-mode, SendGrid, failure/retry,
   maintenance and operator-queue acceptance in staging.
4. Create or re-create an empty production database, apply the same Alembic
   revision, and verify that no synthetic staging rows exist.
5. Point the web service and all four cron jobs to that one production
   connection and require `/health/ready` to report PostgreSQL, the expected
   revision, complete configuration and the approved legal-content version.

Every future schema change must add and rehearse a reviewed Alembic revision.
The included SQLite-to-PostgreSQL utility is retained only as a fail-closed
contingency for a separately approved future legacy import; it is not part of
this fresh-release launch and must not be run against the production database
without a new migration plan and approval.

## Privacy, legal, and AI launch gates

NyaySetu handles phone numbers, names, location, legal issue descriptions,
payment references, and potentially sensitive legal facts. Before public use:

- Have Indian legal counsel approve disclaimers, scope, escalation language,
  current-law content, fees, cancellation/refund terms, and legal guides.
- Publish an accessible privacy notice covering purposes, processors,
  retention, access/deletion requests, and cross-border processing.
- Approve explicit retention periods before enabling the bounded maintenance
  deletion policy. It expires stale pending bookings and removes only eligible
  completed webhook/inbound events, analytics events, and completed outbox
  jobs. It deliberately preserves users, bookings, fulfilments, payment
  reviews, support, feedback, conversations, failed evidence, and legacy
  message claims; legal hold, data-subject deletion, and backup retention
  remain external governance work.
- Restrict database, Render, Meta, Razorpay, SendGrid, and admin access by role;
  enable MFA, audit access, rotate secrets, and test restore procedures.
- Treat PII scrubbing and model guardrails as defence-in-depth, not a guarantee.
  Do not send identity documents, evidence, privileged communications, or
  unnecessary case facts to an AI provider.
- Evaluate every enabled model in all supported languages for hallucinations,
  outdated statutes, unsafe advice, prompt injection, and emergency handling.
- Keep a clear route to human support. Never market an AI answer as advocate
  advice or a predicted legal outcome.

## WhatsApp template and messaging policy

Most interactive bot replies occur inside a user-initiated customer-service
window. Any reminder, re-engagement, receipt, or support update sent outside
that window must use a Meta-approved message template for the exact language
and purpose.

Before enabling proactive messages:

1. Obtain opt-in and record its purpose and timestamp.
2. Submit English, Hindi, and Marathi templates to Meta.
3. Map approved template names/locales in staging.
4. Test opt-out, frequency caps, delivery failures, and escalation.
5. Monitor Meta quality ratings and stop campaigns that users reject.

Do not repurpose transactional consent for promotional campaigns.

## Quality and release controls

CI in [.github/workflows/ci.yml](.github/workflows/ci.yml) compiles source,
validates the Gunicorn configuration, runs high-confidence Ruff checks and
tests with coverage, verifies the lock-derived SBOM, audits dependencies, and
rehearses Alembic upgrade/check/downgrade/re-upgrade against PostgreSQL. It also
runs weekly. Third-party checkout/setup actions are pinned by commit SHA.
Dependabot opens bounded monthly dependency updates.

This project directory is intended to be the Git repository root. If it is
committed as a subdirectory of a larger monorepo, move/merge `.github` into the
actual repository root and add appropriate path filters; GitHub will not
discover nested workflow directories.

A production release still requires:

- signed Meta and Razorpay staging fixtures;
- a complete Razorpay test-mode payment with current dual-resource validation,
  duplicate-delivery retry, invalid/refunded-state review, and terminal manual
  disposition preservation;
- WhatsApp interactive-message rendering in all three languages;
- SendGrid sender/recipient verification and outbox retry testing;
- database backup/restore evidence;
- migration-head, dry-run maintenance, and payment-reconciliation evidence;
- alerting for webhook 5xx responses, dead outbox jobs, payment mismatch,
  overdue fulfilment/support, database errors, and provider failures; and
- a documented rollback decision and responsible on-call owner.

## Further documentation

The detailed documentation index is in [docs/README.md](docs/README.md), with
functional, architecture, security, testing, data, API, and operational
references.
