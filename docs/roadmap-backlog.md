# Roadmap and Backlog

## Status key

- **Implemented**: present in the current repository; still requires
  environment verification.
- **Launch gate**: must be completed before production cutover.
- **Future**: product or scale work not currently implemented.

## Implemented foundation

### Reliability and payments

- Environment-selected PostgreSQL/SQLite database configuration.
- Correct IST afternoon/evening slot mapping and configurable cutoff/horizon.
- Daily and per-slot capacity with transaction locking.
- Booking review before payment-link creation.
- Stored booking amount used for Razorpay verification.
- Raw-body HMAC verification, provider-event idempotency, and retryable payment
  failures.
- Independent current Payment Link/Payment entitlement validation, including
  exact ownership, one capture, zero refund state, and terminal manual-review
  authority.
- Atomic booking/user/webhook/outbox mutation.
- Durable WhatsApp, email, support, and optional receipt jobs.
- Deduplicated safe conversation-reply recovery without state-machine replay,
  ambiguous-delivery suppression, and terminal payload scrubbing.
- Private temporary receipt files with cleanup.
- Lease-aware durable inbound claims, crash recovery, and batch-drain behavior.
- Exact-evidence payment-link reconciliation with a human-review queue.
- Paid-booking fulfilment/SLA records and deduplicated follow-up jobs.
- Audited paid rescheduling and reviewed refund-outcome recording that preserves
  payment evidence; provider refund execution remains external.

### User experience

- Persistent home and self-service menus.
- Appointment status and payment-link recovery.
- Consultation preparation checklists.
- Built-in legal guides.
- AI privacy consent and local provider fallback.
- Support-ticket intake and protected support queue.
- Post-consultation feedback.
- District ambiguity selection.
- Today booking when a valid slot remains.
- English, Hinglish, and Marathi core flows.
- Template-gated, deduplicated 24-hour/2-hour reminder scheduling and safe
  outbox revalidation; empty pairs keep it disabled.

### Security and operations

- Token-protected metrics and audited support, fulfilment, payment-review,
  outbox, availability, and audit APIs.
- Liveness/readiness endpoints and request/security headers.
- PII-minimised logs and analytics.
- Typed environment settings and empty defaults for support/email contacts.
- Exact runtime dependency pins, deterministic lock-derived SBOM, CI
  tests/static checks/weekly vulnerability audit, and Dependabot.
- Alembic production baseline, pre-deploy migration, and expected-revision
  readiness.
- Conservative bounded retention plus fulfilment/support/payment risk reporting.
- Render definitions for exactly one threaded Gunicorn worker plus outbox,
  payment-reconciliation, reminder, and maintenance crons.

These items are “implemented,” not automatically “deployed” or “operational.”

## P0 launch gates

### Managed PostgreSQL migration

- Inventory the live SQLite/schema state.
- During a maintenance window, create and restore-test an untouched artifact
  through SQLite's Online Backup API or CLI `.backup`; never raw-copy an active
  WAL database.
- Validate the included Alembic baseline/backfill against the real legacy
  schema; keep production `AUTO_CREATE_SCHEMA=false`.
- Rehearse the included `python -m jobs.migrate_sqlite_to_postgres` utility
  from a frozen, current-head source into an empty, current-head PostgreSQL
  target. Supply the target only through `NYAYSETU_CUTOVER_TARGET_URL`, require
  a successful preflight before the exact confirmation phrase, and clear the
  variable immediately afterward.
- Validate row counts, IDs, timestamps, sequences, indexes, constraints, and
  enum/status values after the atomic import.
- Reconcile every pending/paid/completed booking against Razorpay.
- Prove web and all four crons share the intended database with least-privilege
  settings, then execute rollback rehearsal.

### Payment and delivery staging

- Run signed Meta and Razorpay test-mode end-to-end cases.
- Test duplicate, delayed, batched, unmatched, amount-mismatch, provider-down,
  and database-failure scenarios.
- Activate and monitor outbox, reconciliation, reminder, and maintenance crons.
- Verify SendGrid sender and explicitly approved recipients.
- Decide whether automatic receipts should remain off or be enabled.
- Staff alerts and the protected review queue for the five-minute
  reconciliation command.
- Keep reminder pairs empty until Meta approval/opt-in/localized suppression
  tests pass; rehearse maintenance dry-run/risk exits before mutation.

### Fulfilment and policy

- Define who provides the paid consultation, through which channel, and within
  what SLA.
- Approve price, capacity, no-show, reschedule, cancellation, refund,
  chargeback, receipt/tax, and grievance rules.
- Staff support and document incident/escalation procedures.
- Publish privacy, terms, AI, and retention notices with valid contact details.
- Review legal content and all languages with qualified/native reviewers.

### Monitoring and security

- Alert on webhook 5xx, payment mismatch/unmatched events, queue age, dead jobs,
  readiness failure, and database saturation.
- Add platform access control around admin routes and rotate secrets.
- Complete secret scan, dependency review, penetration test, and backup
  security review.
- Define retention/deletion schedules and incident response.

## P1 product and operations

### Advocate fulfilment

- Extend the implemented fulfilment entity/status audit with provider-channel
  evidence and notifications.
- Validate qualifications, availability, category/district fit, and conflicts.
- Notify the advocate and user through approved channels.
- Record acceptance/contact evidence and reassignment beyond current
  assignment/confirmation/completion/no-show states.

### Reschedule, cancellation, and refund

- Let users request changes without creating duplicate payments.
- Enforce cutoff and policy rules.
- Integrate controlled Razorpay refund execution with idempotency and approval
  on top of the implemented operator review/outcome record.
- Notify all parties and preserve an audit history.

### Operator workflows

- Add individually authenticated RBAC/MFA rather than a shared token.
- Extend implemented support assignment/status/SLA updates with comments and
  independently authenticated actor identity.
- Search bookings using non-sensitive references.
- Extend implemented payment/refund dispositions and outbox review to provider
  settlement, refund-execution, and chargeback state.
- Make the implemented application audit trail tamper-resistant and integrate
  it with platform identity/audit retention.

### Privacy lifecycle

- Extend implemented versioned AI/payment consent to privacy/marketing,
  revocation, and policy-governance workflows.
- Add user export, correction, deletion/anonymisation, and legal-hold handling.
- Extend bounded cleanup beyond terminal inbox/webhook/analytics/completed
  outbox categories only after legal-hold and policy approval.
- Verify backups follow the same retention and deletion decisions.

### Reminder activation and governance

- Populate the implemented appointment-reminder template pairs only after
  opt-in and Meta approval.
- Include frequency caps, quiet hours, suppression, and opt-out.
- Never use the operational outbox as an unreviewed marketing campaign engine.

## P2 quality and growth

### Legal knowledge quality

- Replace static answers with a counsel-owned source repository.
- Add source dates, jurisdiction, citations, review status, and correction
  workflow.
- Evaluate retrieval and model output in all supported languages.
- Route uncertainty and high-stakes matters to humans.

### Analytics

- Define a privacy-safe event dictionary and funnel queries.
- Report conversion, expiry, capacity, fulfilment, support SLA, and feedback.
- Apply minimum cohort sizes and role-based access.
- Optimize for successful resolution and trust, not conversation duration.

### Scalability

- Introduce distributed rate limiting/WAF controls.
- Move from bounded polling to a queue when measured volume requires it.
- Add PostgreSQL concurrency/load tests before increasing web workers.
- Add synthetic provider monitoring and tested graceful degradation.

### Integrations

- CRM integration after purpose/access/retention approval.
- Settlement/accounting export with reconciliation controls.
- Secure document intake only after malware scanning, encryption, and
  retention design.

## Suggested milestones

### Milestone 1: Controlled staging

Complete PostgreSQL rehearsal, automated tests, signed provider scenarios,
outbox monitoring, and policy review.

### Milestone 2: Limited production pilot

Launch to a capped cohort with staffed human fulfilment/support, monitored
five-minute bounded payment reconciliation, and rollback readiness.

### Milestone 3: Operational maturity

Operationalize the implemented fulfilment/support/reconciliation/maintenance
foundation, then add provider refund execution, individual RBAC/MFA, legal
holds/privacy rights, and tamper-resistant audit retention.

### Milestone 4: Evidence-led growth

Activate the approved reminder pipeline, source-backed multilingual content,
quality evaluation, and outcome-focused analytics before broader acquisition.

## Definition of done for production launch

- Managed PostgreSQL is restored, migrated, reconciled, and monitored.
- All automated, PostgreSQL-concurrency, and external staging tests pass.
- Meta, Razorpay, SendGrid, web, outbox, reconciliation, reminder, and
  maintenance configuration is independently reviewed.
- Payment and notification failures are alertable and recoverable.
- Human fulfilment and support owners meet documented SLAs.
- Privacy, AI, legal-content, refund, retention, and incident policies are
  approved.
- Secrets, admin access, backup/restore, and rollback are tested.

Features in later milestones are not required to start a tightly controlled
pilot, but payment fulfilment, reconciliation, privacy, and support gates are.
