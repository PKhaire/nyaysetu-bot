# Testing and QA Plan

## Current automated suite

The repository contains automated tests across booking, webhook/flow,
delivery, transport, and AI-safety modules:

| File | Implemented coverage |
|---|---|
| `tests/test_booking_service.py` | IST slot mapping, booking horizon, daily/slot capacity, provider rollback, stored amount/link expiry, payment idempotency, pending expiry |
| `tests/test_app_flows.py` | Meta signature rejection, persistent home, structured case-brief capture/edit/consent/booking link, durable inbound leases/batch draining, bounded/pruned early-rate-limit state, capped outbox fast-path saturation, safe post-mutation reply deferral, replay suppression, ambiguous-delivery no-send, and terminal payload scrubbing |
| `tests/test_app_webhooks.py` | Razorpay signature-before-parse, live dual-resource entitlement validation, terminal manual-disposition authority, stored-price/reconciliation evidence, replay, retryable failures, health/schema/strong-configuration readiness |
| `tests/test_delivery_services.py` | Structured WhatsApp failures, step-level outbox retry, receipt cleanup/private temp files, PII-safe Amazon SES failure logging |
| `tests/test_ai_safety.py` | PII scrubbing, pseudonymous identifiers, urgent/harmful guardrails, provider short-circuiting, OpenAI privacy/request contract |
| `tests/test_ai_provider_compatibility.py` | Thread-safe bounded/TTL response cache, provider/model contracts, one-attempt fallback, and compatibility errors |
| `tests/test_whatsapp_service.py` | Payload limits, structured configuration failures, safe logs/provider errors, bounded retry behavior, stored-price payment confirmation |
| `tests/test_admin_operations.py` | Operator identity/audit, masked queue data, purpose-bound contact reveal, structured brief review, verified advocate registration/assignment, manual handover evidence, fulfilment, reviewed refund evidence/access effects, reconciliation, outbox, and availability mutations |
| `tests/test_payment_reconciliation.py` | Dual-resource exact/non-refunded capture recovery, ambiguity/concurrency preservation, idempotency, and provider failures |
| `tests/test_consultation_reminders.py` | Empty-config no-op, language/template gating, due windows, deduplication, suppression, delivery ambiguity, and CLI safety |
| `tests/test_maintenance.py` | Protected booking evidence, unattached case-brief expiry, bounded cleanup/dry-run, risk report, and exit semantics |
| `tests/test_migrations.py` | Fresh baseline plus regression coverage for the inactive legacy schema/backfill contingency |
| `tests/test_sqlite_postgres_cutover.py` | Regression coverage for the inactive SQLite-import contingency: full-table plan, preflight non-mutation, bounded copy, rollback, schema/source/empty-target checks, credential isolation, and CLI fail-closed behavior |
| `tests/test_deployment_config.py` | One-worker/query-safe Gunicorn and Render process contract |
| `tests/test_dependency_lock.py` | Exact direct/runtime lock alignment, five-service lock installation, and deterministic CycloneDX SBOM parity |

`tests/conftest.py` provides an isolated in-memory SQLite database and test
provider configuration. Provider network calls are mocked.

Run:

```text
python -m pip install -r requirements-dev.txt
python -m compileall -q app.py admin.py category_labels.py config.py db.py demo_local_ai.py gunicorn.conf.py location_service.py models.py subcategory_labels.py translations.py utils.py migrations services jobs tests utils
python -m ruff check .
python -m pytest -q
python -m pip check
python -m jobs.generate_sbom --check
python -m pip_audit --progress-spinner off -r requirements.lock
```

These checks verify code behavior, not live provider dashboards, PostgreSQL
concurrency, legal content, or operational readiness. The SBOM check is an
offline lock-inventory consistency check, not a vulnerability result;
`pip-audit` remains the time-sensitive advisory check.

## Test layers

### Unit/service tests

High-risk deterministic targets:

- Name, district, category/subcategory, date, and slot validation.
- Structured brief field bounds, versioned consent, edit/cancel behavior, no-file
  policy, booking attachment, and unattached retention.
- Timezone boundary at midnight IST and every configured cutoff.
- Per-slot/day capacity with paid, pending, expired, cancelled, and completed
  bookings.
- Thread-safe pruning/hard caps for process-local rate limits,
  maintenance-notice dedupe, AI cache, and the optional outbox fast path.
- Payment-link TTL, amount, metadata, orphan cancellation, and rollback.
- Conditional payment update under duplicate and conflicting payment IDs.
- Exact current Payment Link/Payment ownership, single capture, current
  capture/refund state, and terminal manual-disposition preservation.
- WhatsApp payload length/row/button validation and response classification.
- AI PII scrub, urgent/harmful patterns, provider order, consent, quota, and
  local fallback.
- Analytics redaction and property-size limit.
- Outbox backoff, lease recovery, terminal dead state, step markers, safe
  conversational reply retry, and terminal payload scrubbing.
- Durable inbound claim/reclaim/completion and expired terminal cleanup.
- Fulfilment transition/SLA, reconciliation strictness, and availability rules.
- Reminder due/catch-up windows, exact language-template gating, dedupe keys,
  current-state revalidation, and safe no-send completion.
- Bounded maintenance, protected evidence, risk-exit behavior, support/feedback
  validation, and localization-key completeness.

### Flask route tests

Every public route should cover valid, invalid, duplicate, and dependency-fault
cases.

For `POST /webhook`:

- Missing, malformed, and wrong signatures.
- Invalid JSON, oversized body, status-only delivery, unsupported type.
- New and returning user in each language.
- Text and interactive errors in every state.
- Ambiguous district selection.
- Home/menu without state loss.
- AI accept/decline and five-question boundary.
- Booking scope, detail verification, availability, review/change/cancel/pay.
- Pending-link recovery, support, privacy, guide, receipt, and feedback.
- Duplicate message, concurrent first message, multi-entry batch, and failure
  claim release.
- Per-user and global limits apply before menu, support, media, and paid-session
  branches; repeated limited requests produce at most one notice per window.
- A safe no-request/connection/transient-HTTP delivery failure after state
  mutation commits one deduplicated conversation-delivery job and marks the
  inbound event `DONE`; replay cannot repeat the transition.
- An ambiguous read/protocol delivery failure is terminal without resend; both
  completed and dead conversational jobs scrub recipient/body payloads.

For `POST /payment/webhook`:

- Signature verification occurs before parsing.
- Current/previous/wrong/missing secret, mode, event, timestamp, structure,
  state, currency, amount, and identifiers.
- Current configured price differs from the booking's stored amount.
- Unknown captured payment persists review evidence and returns retryable
  failure; amount/currency mismatch persists review evidence and returns `202`
  without paying the booking.
- Current Payment Link and Payment lookups require exact link/reference/notes,
  stored amount, single captured payment/ID, `captured=true`, and zero/no
  refund state.
- Provider lookup failure returns `503` without entitlement; invalid/refunded
  current state persists review evidence and returns `202`.
- Every terminal manual disposition short-circuits delayed matched and
  unmatched events, remains unchanged, and creates no entitlement/outbox work.
- PostgreSQL two-session races use the common booking-to-review lock order:
  operator-first terminal disposition prevents entitlement; webhook-first
  commit is followed by serialized refund revocation without deadlock/loss.
- Same payment replay is safe.
- Same payment on another booking creates a durable `202` review conflict.
- Concurrent event claims do not duplicate outbox jobs.
- Database failure at each transaction boundary returns `503`.
- User missing still preserves paid booking and configured outbox work.

For admin and health:

- Liveness does not require providers.
- Readiness fails for database/schema/configuration problems, weak current
  WhatsApp/Razorpay/admin/AI credentials, missing/invalid SES region,
  from-address or AWS access credentials, non-HTTPS policy URLs, invalid
  contacts, a nonempty weak previous rotation secret, or a future/malformed
  legal-review date.
- Missing admin configuration hides routes.
- Invalid/valid bearer and header tokens.
- Support pagination limits and no-cache headers.
- Metrics contain no phone, name, message, or provider short URL.
- Mutations require operator ID and create correct before/after audit records.
- Support/fulfilment/reconciliation transitions reject invalid/no-note actions.
- Direct `UNASSIGNED` to `CANCELLED` is rejected. The reviewed
  `REFUND_REVIEW` to `REFUNDED` path cancels the booking while preserving
  processed payment evidence and clears paid user state only without another
  `PAID` booking.
- Blackouts/capacity overrides affect live availability and deactivate safely.
- Queue/list responses keep client and advocate contacts masked; reveal requires
  a stable operator ID plus purpose and creates an audit event.
- Advocate registration/assignment rejects inactive or unverified records, and
  manual client/advocate contact outcomes are append-only and scoped to the
  correct fulfilment.

### PostgreSQL integration tests

SQLite tests do not prove production locking. Against disposable PostgreSQL:

- Run the real schema/migration baseline.
- Run `python -m alembic -c alembic.ini upgrade head`, `current`, and `check`
  against a fresh database.
- Submit concurrent requests for the final available slot.
- Deliver the same payment event through competing database sessions.
- Claim the same outbox job from competing runners.
- Interrupt a running job and verify lease recovery.
- Verify enum, unique constraint, transaction isolation, pool, and timestamp
  behavior.
- Load test signed WhatsApp batches and payment webhooks.

Representative legacy-schema upgrades and the SQLite importer remain regression
coverage for an inactive contingency; they are not staging or production launch
gates. In disposable CI infrastructure, keep testing the legacy upgrade plus
the one-shot preflight and exact-confirmation import from a frozen, current-head
SQLite backup into an empty current-head PostgreSQL target. Verify all table
counts, preserved IDs/timestamps/foreign keys, reset integer sequences, target
locks, and atomic rollback after an injected mid-copy failure. Also prove that
stale/incomplete schemas, source sidecars or changes, non-empty targets, and
target URLs on the process command line are rejected.

Production still enforces one Gunicorn web worker. Multi-worker tests are
preconditions for a future topology change, not permission to override
`gunicorn.conf.py`.

### Staging end-to-end tests

Use isolated Meta, Razorpay test-mode, Amazon SES, and PostgreSQL resources:

Before user-flow acceptance, provision a new empty staging PostgreSQL database,
apply the current Alembic revision, run `current` and `check`, and verify
readiness. Populate it only with synthetic/test data. Do not restore a legacy
SQLite database or run `jobs.migrate_sqlite_to_postgres` in the current staging
or production rollout.

1. Complete each primary user journey in all languages.
2. Create one test link only after review.
3. Pay the exact amount and verify one paid booking only after current Payment
   Link and Payment resources pass the full ownership/capture/refund contract.
4. Verify one WhatsApp success and configured email.
5. Redeliver the provider event and verify no duplicate side effect.
6. Fail WhatsApp/Amazon SES, run the outbox cron, and verify recovery without
   an immediate SDK retry.
7. Expire a pending link and verify capacity becomes available.
8. Exercise support and feedback and inspect only through authorized access.
9. Verify receipt delivery and file cleanup when explicitly enabled.
10. Exercise fulfilment assignment/status, reviewed refund recording,
    reconciliation disposition, and availability blackout/override; verify
    audit events, payment-evidence preservation, and delayed-event terminal
    disposition authority.
11. Run exact-evidence payment reconciliation once and verify ambiguity is not
    auto-paid.
12. Run maintenance dry-run and risk exit; verify protected evidence survives.
13. With templates empty, verify reminder cron no-op; with approved staging
    pairs, verify 24-hour/2-hour dedupe and suppression after appointment/
    fulfilment/template changes.
14. Confirm provider dashboards and application records reconcile.
15. Inject safe and ambiguous post-mutation WhatsApp reply failures; verify
    state is not replayed, only safe delivery is queued, and terminal payloads
    are scrubbed.
16. Saturate the bounded web outbox fast path; verify the request safely skips
    the optional kick and the one-minute cron drains the durable jobs.
17. With two PostgreSQL sessions, pause webhook processing after current
    provider validation and booking/review locking while resolving the same
    `OPEN` review. Verify both operator-first and webhook-first orderings,
    entitlement/revocation, no deadlock, and no lost disposition.

Never run destructive, refund, or load scenarios against real user data.

## Manual product QA

- Copy fits Meta button, list, header, and body limits.
- Markdown and Unicode render correctly in each language.
- Marathi/Hinglish wording is reviewed by native speakers.
- Today and 3 PM/6 PM/8 PM slots display and validate correctly.
- No list selection silently strands the user.
- Home does not erase an in-progress booking.
- Fee and fulfilment wording match approved policy.
- Support/privacy contacts and links are valid.
- Immediate-danger messaging is clear and does not invent a local service.
- AI answers remain informational and do not expose redacted identifiers.
- User can understand whether an action is pending, paid, completed, or failed.

## Security and privacy QA

- Secret scan committed files and built artifacts.
- Confirm logs contain no request body, phone, legal/support text, payment short
  URL, email recipients, database credentials, or outbox payload.
- Verify TLS and platform access controls.
- Test token timing/format handling and rotate all staging secrets.
- Fuzz webhook envelopes and WhatsApp interactive IDs.
- Test request-size and rate-limit boundaries.
- Review generated receipt metadata/content and deletion.
- Audit dependencies and container/runtime image.
- Conduct external penetration testing before launch.

## Fresh-release database and disaster-recovery QA

- Provision an isolated empty staging PostgreSQL database; apply
  `python -m alembic -c alembic.ini upgrade head`, then verify `current`,
  `check`, and readiness.
- Confirm staging contains only synthetic/test data.
- Back up staging, restore it into a different isolated database, and measure
  recovery objectives.
- Prove the web service and all four crons use the one intended staging
  database and staging-only provider credentials.
- Reconcile only staging test transactions against Razorpay test mode.
- Provision production on a different empty PostgreSQL database, apply and
  verify the same Alembic revision, and prove backup/restore before traffic.
- Prove the web service and all four crons use the one intended production
  database with production-only provider credentials.
- Confirm production contains no staging, test, or legacy rows and that no
  legacy import or reconciliation is scheduled.

### Contingency legacy-import QA (not part of the current release)

Run these checks only if a separately reviewed plan activates a future import:

- Restore a live-like backup into an isolated database.
- Apply `python -m alembic -c alembic.ini upgrade head`, then verify
  `current` and `check`.
- Compare row counts, IDs, unique values, statuses, timestamps, and samples.
- Reconcile pending, paid, and completed bookings against Razorpay.
- Prove every service uses only the intended database/provider credentials.
- Simulate a failed import/cutover, execute rollback, restore from the final
  backup, and measure recovery objectives.

## Release gates

Code gates:

- Compile/static checks pass.
- All automated tests pass with no unexplained skip.
- Dependency audit has no unaccepted finding.
- PostgreSQL concurrency tests pass.
- The two-session webhook/operator terminal-disposition rehearsal passes on the
  production-like PostgreSQL engine.

External gates:

- Signed Meta and Razorpay staging evidence is retained.
- The Amazon SES identity/domain and recipients are approved; DKIM/SPF/DMARC,
  production access, least-privilege `ses:SendEmail`, configuration-set
  bounce/complaint/delivery monitoring, the 50-destination BCC bound, bounded
  timeouts, and PII-safe failure telemetry are verified. Every enabled reminder
  pair has matching Meta template/language approval, opt-in, localization, and
  suppression evidence.
- Fresh staging and production backup/restore evidence passes, and staging
  test-transaction reconciliation passes in Razorpay test mode.
- Outbox monitoring and incident alerts are active.
- Price, capacity, language, legal content, privacy, AI, fulfilment, support,
  refund, and retention policies are approved.

## Future test work

- Property-based testing for webhook envelopes and state transitions.
- Contract fixtures captured from current provider schemas.
- Mutation testing for payment/idempotency code.
- Accessibility and low-literacy moderated usability tests.
- Multilingual AI safety and legal-quality evaluation set.
- Scheduled restore and reconciliation drills.
- Performance baselines for PostgreSQL and the outbox.
