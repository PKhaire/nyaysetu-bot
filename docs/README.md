# NyaySetu Documentation

This pack describes the current repository after its reliability, payment,
security, and user-experience modernization. It distinguishes code that exists
from external rollout work and future product ideas.

## Read in this order

1. [RC7 release notes](RELEASE_NOTES_2026-08-18_RC7.md) — structured case
   brief, consent, protected contact reveal, advocate registry, and manual
   handover operations.
2. [RC6 release notes](RELEASE_NOTES_2026-08-12_RC6.md) — website advocate
   intake routing.
3. [RC4 release notes](RELEASE_NOTES_2026-08-07_RC4.md) — legal-guide,
   routing, privacy, validation, and release-gate changes.
4. [RC3 release notes](RELEASE_NOTES_2026-07-31_RC3.md) — infrastructure,
   SES, verification evidence, and mandatory external gates inherited by RC4.
5. [Master product, technology, launch and growth blueprint](NYAYSETU_MASTER_BLUEPRINT.md)
   — consolidated status, decisions, user experience, architecture, privacy,
   launch, operations, budget, roadmap and marketing strategy.
6. [Functional specification](functional-specification.md) — implemented
   user and operations behavior.
7. [Technical architecture](technical-architecture.md) — runtime, data flow,
   idempotency, database, outbox, and AI design.
8. [API and integrations](api-integrations.md) — routes and provider contracts.
9. [Data model and governance](data-model.md) — current entities, sensitivity,
   lifecycle, and migration gates.
10. [Security, risk, and compliance](security-risk-compliance.md) — controls,
   limitations, and launch risks.
11. [Legal content review checklist](legal-content-review-checklist.md) —
   version-specific reviewer scope and sign-off gate.
12. [Testing and QA plan](testing-qa-plan.md) — automated coverage and required
   staging/migration evidence.
13. [Deployment and operations](deployment-operations.md) — environment,
   cutover, monitoring, runbooks, and rollback.
14. [Client and user perspective](client-user-perspective.md) — user promise,
   journey, trust, and acceptance.
15. [Business perspective](business-perspective.md) — value, operating model,
   metrics, and responsible growth.
16. [Roadmap and backlog](roadmap-backlog.md) — completed foundation, launch
    gates, and future milestones.
17. [Local AI demo](local-ai-demo.md) — optional demonstration of the built-in
    local knowledge path; it is not the production architecture specification.

## Current product

NyaySetu is a Flask/WhatsApp legal-information and consultation-booking
assistant with:

- English, Hinglish, and Marathi navigation.
- Consent-gated free AI with deterministic safety checks and local fallback.
- Persistent home, legal guides, status, preparation, support, privacy, and
  feedback.
- IST-aware, capacity-filtered booking and review before payment.
- Consent-based structured case briefs with no identity/evidence file upload.
- Razorpay stored-price verification through a signed, idempotent webhook.
- PostgreSQL-capable persistence, a lease-aware inbound inbox, and a durable
  external-delivery outbox.
- Versioned Alembic schema releases and bounded maintenance.
- Optional Meta-template-gated 24-hour/2-hour reminders, inert by default.
- Session/token-protected, audited support, fulfilment, case-brief review,
  verified advocate assignment, contact reveal/manual handover,
  reconciliation, outbox, availability, and metrics operations.

Operators can assign an active advocate or named fulfiller and manage the
fulfilment lifecycle, but the product does not automatically select an
advocate, connect a live call/chat, execute a Razorpay refund, provide an
emergency response, or guarantee legal advice/outcome.

## Runtime routes

| Route | Purpose |
|---|---|
| `GET /` | Service metadata |
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Database/configuration readiness |
| `GET /webhook` | Meta verification |
| `POST /webhook` | Inbound WhatsApp messages |
| `POST /payment/webhook` | Razorpay paid-link events |
| `GET /admin/metrics` | Token-protected aggregate metrics |
| `GET/PATCH /admin/support[...]` | Support queue and audited updates |
| `GET/PATCH /admin/fulfillments[...]` | Paid-consultation operations |
| `POST /admin/fulfillments/<id>/contact-reveal` | Audited client contact reveal |
| `POST /admin/fulfillments/<id>/contact-events` | Manual handover outcome |
| `GET/POST /admin/advocates[...]` | Verified advocate registry and protected contact reveal |
| `GET/PATCH /admin/payment-reconciliations[...]` | Payment review operations |
| `GET/POST/DELETE /admin/availability[...]` | Capacity and blackout operations |
| `GET/POST /admin/outbox[...]` | Queue inspection and retry |
| `GET /admin/audit` | Operator mutation audit |

Operational entry points are:

```text
python -m jobs.process_outbox
python -m jobs.reconcile_payments --limit 100
python -m jobs.consultation_reminders
python -m jobs.maintenance --batch-size 500 --fail-on-risk
```

The Blueprint schedules all four commands. Reminder scheduling remains inert
while exact Meta-approved template name/language pairs are empty.

## Source of truth

- Live behavior: Python code and tests.
- Configuration: `config.py` and `.env.example`.
- Runtime/deployment shape: `render.yaml`, `Procfile`, and
  `.python-version`.
- Production dependency graph: `requirements.lock`; human-reviewed direct
  intent remains in `requirements.txt`.
- Offline release inventory: deterministic CycloneDX `sbom.cdx.json`, generated
  from the production lock by `jobs/generate_sbom.py`. It is not a vulnerability
  scan; CI's weekly `pip-audit` is the time-sensitive vulnerability gate.
- Automated checks: `tests/`, `.github/workflows/ci.yml`, and
  `.github/dependabot.yml`.
- Operating procedure: `deployment-operations.md`.

When prose conflicts with executable code, investigate and update both rather
than treating this document as an override.

## Implemented versus deployed

Implemented in the repository:

- Environment-driven PostgreSQL/SQLite database engine.
- Booking capacity, correct IST slot mapping, and payment-link lifecycle.
- Signed, retryable, idempotent Meta and Razorpay webhook handling.
- Atomic payment/outbox transaction and retryable external delivery.
- Durable lease-based inbound-message claims recoverable after a process crash.
- Safe temporary receipts, configurable email recipients, AI consent/PII
  controls, versioned consent, support, feedback, and audited operator APIs.
- Payment-link reconciliation that automatically recovers only exact provider
  evidence and queues ambiguity for human review.
- Alembic baseline, bounded retention/risk maintenance, deployment-contract
  tests, and CI migration/static/dependency checks.
- A fail-closed one-shot frozen-SQLite-to-empty-PostgreSQL cutover utility;
  using it on live data still requires the runbook's backup, restore, rehearsal,
  reconciliation, approval, and rollback evidence.

Still required before production cutover:

- For the approved fresh first release, create an empty managed PostgreSQL
  database, apply and verify the Alembic revision, enable backups, and
  restore-test it. No legacy users or database records will be imported. The
  SQLite cutover utility and runbook remain available only if that decision
  changes.
- Deploy the one-worker web service plus outbox, reconciliation, reminder, and
  maintenance crons with correctly scoped shared settings.
- Pass signed Meta/Razorpay/Amazon SES staging, duplicate/failure, and PostgreSQL
  concurrency tests.
- Staff consultation fulfilment/support and approve price, capacity, refund,
  cancellation, privacy, AI, retention, and incident policies.
- Activate monitoring for webhook failures, unmatched payments, readiness,
  queue age, and dead jobs.

Future work includes automated advocate matching/user notification, controlled
Razorpay refund execution, per-operator RBAC/MFA, privacy export/deletion and
legal holds, source-backed legal content, broader user-status workflows, and
distributed throttling. The implemented reminder pipeline must remain disabled
until Meta template, opt-in, localization, and messaging-policy gates pass.

## Terminology

- **User**: the WhatsApp participant stored in `users`.
- **Booking**: the appointment/payment record stored in `bookings`.
- **Pending**: a booking whose payment has not been confirmed and whose link
  may still consume capacity.
- **Paid**: a signed provider event confirmed the stored amount.
- **Completed booking**: the paid booking/fulfilment lifecycle has been closed;
  verify the linked fulfilment audit rather than inferring delivery from time.
- **Inbound inbox**: `inbound_message_events`, used for lease-aware WhatsApp
  deduplication and crash recovery.
- **Webhook inbox**: `webhook_events`, used for provider event idempotency and
  minimal audit metadata.
- **Outbox**: `outbox_jobs`, used to retry committed external side effects.
- **Reconciliation item**: privacy-minimised provider/payment evidence that
  requires automatic exact-match recovery or an audited operator disposition.
- **Local AI**: deterministic/local legal-information content; not a substitute
  for counsel.

## Documentation maintenance

Update the relevant pages whenever a route, model, state, environment variable,
provider contract, rollout gate, or operating policy changes. Keep completed,
prerequisite, and future claims separate so stakeholders do not mistake code
presence for production readiness.
