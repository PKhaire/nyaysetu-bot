# NyaySetu First Production Launch Checklist - Bot + Document Studio

Prepared: 3 September 2026  
Release candidate: RC9  
Decision rule: NyaySetu Bot and Document Studio launch together. There is no
base-bot-only production path in this checklist. Any unchecked mandatory gate
keeps the release at **NO-GO**.

## Current verdict

**NO-GO for production.** The deployed service is healthy staging, but the
complete RC9 source is still local and Document Studio has unresolved legal,
infrastructure, operational, security, and end-to-end evidence gates.

Verified baseline:

- [x] Public API is reachable and the current staging readiness response is OK.
- [x] Current deployed schema is `20260819_01`.
- [x] Local RC9 validation passed: 319 tests, 66.57% coverage, Ruff, compile,
  dependency check, SBOM generation, and the 60% coverage gate.
- [x] Local RC9 has a single Alembic head: `20260903_01`.
- [x] Document Studio is globally available when enabled, not a test-user or
  cohort feature.
- [ ] All mandatory gates below are complete and supported by saved evidence.

## A. Freeze and publish the exact RC9 release

- [ ] Review the local diff and confirm every intended RC9 file.
- [ ] Confirm no credentials, access tokens, personal test data, generated
  documents, `.env` file, or private advocate material is in the upload set.
- [x] Implement and test the global daily Document Studio capacity
  control before freezing RC9. It must be atomic across all users and must not
  behave as a percentage rollout or test-user flag.
- [x] Rerun the full automated suite after the capacity change.
- [ ] Assign the release a final immutable version/tag and record its Git SHA.
- [ ] Upload/merge that exact source to GitHub `main`.
- [ ] Confirm GitHub CI is green for tests, migration validation, static checks,
  and dependency vulnerability audit.

Evidence: Git SHA, reviewed manifest, CI URL, test report, and SBOM.

## B. Separate staging from production

- [ ] Keep the current staging service/database available for UAT.
- [ ] Create or verify a separate production Render service/environment group.
- [ ] Create a separate production PostgreSQL database; do not promote UAT
  records as real customer data.
- [ ] Use independent production secrets, Razorpay keys, S3 storage, and webhook
  configuration.
- [ ] Set `ENV=production`, `FLASK_ENV=production`, and `DEBUG=false` only in
  production.
- [ ] Confirm `RESET_DB=false` and destructive reset behavior is disabled.
- [ ] Run Alembic and confirm schema `20260903_01` is applied.
- [ ] Confirm `/health/live` and `/health/ready` return HTTP 200.

Evidence: sanitized environment inventory, service IDs, migration log, and
health responses. Never store secret values in evidence.

## C. Document Studio legal and product approval

- [ ] Obtain authenticated advocate review of the exact RC9 template version,
  clauses, eligibility rules, exclusions, questionnaire, preview, final output,
  disclaimer, and consent language.
- [ ] Record advocate identity, enrolment verification, review date, exact
  version/hash, decision, limitations, and required edits.
- [ ] Resolve every requested legal change and obtain exact-version approval. A
  general or verbal green signal is not enough.
- [ ] Approve the initial document catalogue and price for each document.
- [ ] Confirm unsupported matters fail closed and route to appropriate help
  without generating a purchasable final draft.
- [ ] Confirm the product does not promise validity, registration, notarisation,
  court acceptance, representation, or a guaranteed outcome.
- [ ] Do not display an advocate signature unless that identified advocate has
  actually reviewed and signed that exact output.

Evidence: advocate decision record and approved template hashes.

## D. Document Studio capacity and availability

- [x] Add a documented environment setting for the global daily drafting limit.
- [x] Reserve capacity atomically in PostgreSQL so concurrent requests cannot
  exceed the limit.
- [x] Define when a reservation is consumed, released, expired, or retained
  after payment failure.
- [x] Give every eligible user the same availability rules; do not use test-user,
  allow-list, percentage, or hidden cohort checks.
- [x] Show a friendly capacity-reached message and do not take payment.
- [x] Expose capacity use/exhaustion to admin metrics.
- [x] Test India-timezone rollover and PostgreSQL advisory-lock invocation.
- [ ] Prove concurrent final-slot allocation against staging PostgreSQL.

Evidence: tests, staging concurrency result, configuration, and metrics view.

## E. Private document storage and downloads

- [ ] Provision a private production S3 bucket in the selected AWS region.
- [ ] Block public access at account and bucket level.
- [ ] Enable encryption at rest, HTTPS-only access, and versioning if approved.
- [ ] Create least-privilege IAM access for only the production bucket/prefix.
- [ ] Configure lifecycle deletion to match approved retention.
- [ ] Configure access auditing without recording document text.
- [ ] Use separate staging storage and credentials.
- [ ] Confirm final PDF/DOCX objects cannot be listed or read anonymously.
- [ ] Require owner authorization and short-lived signed download URLs; test URL
  expiry and cross-user denial.
- [ ] Test upload/download failure, orphan cleanup, expiry, and deletion requests.

Evidence: sanitized storage/IAM settings, access tests, lifecycle rule, and
cleanup result.

## F. Draft generation, preview, and entitlement

- [ ] Verify every supported questionnaire path in English, Hindi, and Marathi.
- [ ] Verify validation for required fields, invalid dates/amounts, excessive
  length, malicious input, and contradictory answers.
- [ ] Verify save, resume, cancel, expiry, and restart behavior.
- [ ] Generate from the approved versioned source deterministically.
- [ ] Confirm preview is watermarked/incomplete and no final download is exposed
  before verified payment.
- [ ] Show document name, exact price, material inputs, consent, disclaimer, and
  revision limits before payment.
- [ ] Verify PDF/DOCX Unicode rendering and absence of unresolved placeholders or
  internal metadata.
- [ ] Bind artifacts to the correct user, draft, payment, currency, price, and
  approved template hash.
- [ ] Verify duplicate webhooks cannot duplicate entitlements or outputs.
- [ ] Verify unpaid, failed, refunded, disputed, expired, and tampered payments
  cannot unlock a final document.

Evidence: multilingual matrix, redacted samples, access and idempotency results.

## G. Razorpay and financial operations

- [ ] Complete Razorpay ReKYC and confirm settlements are unrestricted.
- [ ] Keep staging on newly rotated `rzp_test_*` credentials.
- [ ] Test successful, failed, cancelled, delayed, duplicated, and tampered test
  payments for consultations and Document Studio.
- [ ] Create a live-mode webhook for the exact production endpoint with its own
  strong secret and required events.
- [ ] Keep live keys only in production secret storage.
- [ ] Set `RAZORPAY_MODE=live` only during approved production cutover.
- [ ] Run one controlled low-value live transaction and verify signature,
  database state, entitlement, reconciliation, and bank settlement.
- [ ] Document refund, duplicate payment, chargeback, failed generation, and
  support procedures.

Evidence: redacted payment IDs, webhook result, reconciliation, and settlement.

## H. WhatsApp and transactional communication

- [ ] Confirm production WhatsApp number, phone ID, token, app secret, verify
  token, webhook, and subscriptions are active.
- [ ] Rotate/invalidate every token or secret exposed in chat, screenshots, logs,
  or test notes.
- [ ] Verify `Hi`, home menu, Ask Legal Question, Book Consultation, Document
  Studio, and More Options in English, Hindi, and Marathi.
- [ ] Keep menus within WhatsApp limits and show Document Studio to every user
  when the integrated launch is enabled.
- [ ] Verify signature rejection, replay protection, retries, and idempotency.
- [ ] Decide production email delivery: obtain SES production access, integrate
  another provider, or formally disable email-dependent behavior and update
  readiness/operations.
- [ ] Document the V1 manual client/advocate notification procedure, SLA,
  fallback channel, and contact evidence.
- [ ] Do not message outside Meta's allowed window without an approved template.

Evidence: real-number UAT IDs, security/retry results, provider decision, and
manual notification runbook.

## I. Website, policies, consent, and privacy

- [ ] Describe consultation booking and Document Studio accurately, including
  their limitations.
- [ ] Publish advocate-reviewed Terms, Privacy, Refund, Cancellation, disclaimer,
  document-retention, and grievance information without unnecessary personal or
  home-address disclosure.
- [ ] Describe when email, phone, questionnaire data, payment IDs, document data,
  and operational audit data are collected.
- [ ] Explain preview/final output, payment timing, revision limits, downloads,
  expiry, deletion, refunds, and advocate involvement.
- [ ] Set environment policy/version values to the exact published versions.
- [ ] Test all links, mobile layouts, accessibility basics, contact routes, and
  HTTPS redirects.
- [ ] Confirm versioned consent capture and proof retention.

Evidence: approved URLs, versions, test report, and consent record.

## J. Admin security and operations

- [ ] Protect admin routes with MFA or an equivalent identity/access layer; a
  shared password alone is insufficient for production sensitive data.
- [ ] Restrict access to named operators using least privilege.
- [ ] Rotate admin credentials and Flask secret before production.
- [ ] Verify login throttling, secure cookies, CSRF protection where applicable,
  session expiry, logout, and audit logging.
- [ ] Verify contact reveal is reason-gated, time-limited, and audited.
- [ ] Train at least two operators for reconciliation, document failures,
  consultation assignment, privacy requests, refunds, and incidents.
- [ ] Define advocate verification, activation, suspension, assignment, conflict
  check, handover, and outcome procedures.
- [ ] Keep UAT records separate from production reports.

Evidence: access review, operator/training sign-off, audit sample, and advocate
registry review.

## K. Jobs, monitoring, backup, and recovery

- [ ] Deploy web and every cron/worker from the same Git SHA.
- [ ] Verify outbox, reconciliation, reminders (if enabled), and maintenance/
  retention jobs individually.
- [ ] Confirm lease/idempotency prevents duplicate scheduled processing.
- [ ] Alert on readiness, webhook, queue, payment, generation, S3, capacity, cron,
  database, and elevated 5xx failures.
- [ ] Configure production database backups and approved retention.
- [ ] Perform and time an isolated restore drill.
- [ ] Test application rollback with the migrated schema.
- [ ] Test Meta, Razorpay, S3, email, database, and AI outages.
- [ ] Confirm logs/alerts omit secrets, full phone numbers, answers, document
  content, and signed URLs.
- [ ] Record on-call contacts, severity/escalation, customer wording, and kill
  switch.

Evidence: job/alert results, backup policy, restore/rollback reports, and incident
drill notes.

## L. Full integrated staging acceptance

- [ ] Deploy the exact candidate SHA to staging with Document Studio enabled for
  all users and a safe non-zero test price.
- [ ] Verify a new user sees all four choices: Ask Legal Question, Book
  Consultation, Document Studio, More Options.
- [ ] Complete consultation booking, test payment, webhook confirmation, case
  brief, admin assignment, manual handover, and outcome.
- [ ] Complete every eligible Document Studio path through paid PDF/DOCX download.
- [ ] Test ineligible/ambiguous matters, exhausted capacity, abandoned/expired
  drafts, invalid consent, failed/duplicate payment, generation/S3 failure,
  expired URL, cross-user access, refund, and deletion.
- [ ] Complete smoke, regression, security, privacy, mobile, multilingual,
  concurrency, recovery, and accessibility tests.
- [ ] Fix all release blockers and rerun affected and full regression tests.
- [ ] Obtain acceptance from product, operations, verified advocate,
  security/privacy, and technical release owners.

Evidence: signed test report containing case IDs, defects, retests, reviewers,
date, candidate SHA, schema version, and sanitized evidence.

## Final go/no-go record

Record **GO** only when every mandatory checkbox is complete:

- [ ] Product owner: scope, price, promise, and support readiness.
- [ ] Verified advocate: exact legal content and boundaries.
- [ ] Operations owner: staffing, manual notifications, fulfilment, refunds, and
  incidents.
- [ ] Security/privacy owner: access, secrets, retention, deletion, storage, and
  audits.
- [ ] Technical owner: SHA, CI, migration, UAT, monitoring, backup/restore,
  rollback, and provider readiness.
- [ ] Record decision, date/time, participants, approved SHA, and conditions.

## Controlled production cutover

Run only after a recorded GO decision:

1. Announce the release window and freeze unrelated changes.
2. Confirm backup, rollback target, support cover, and provider dashboards.
3. Deploy the approved SHA with maintenance mode enabled.
4. Apply/verify migration `20260903_01`.
5. Verify production configuration without printing secret values.
6. Verify `/health/live` and `/health/ready` internally.
7. Confirm private S3, jobs, alerts, admin identity, Meta webhook, and Razorpay
   live webhook.
8. Run one controlled live consultation payment smoke test.
9. Run one controlled live Document Studio payment, generation, private PDF/DOCX
   download, admin/reconciliation, and deletion/expiry smoke test.
10. Confirm both low-value payments settle/reconcile correctly.
11. Resolve test records under the approved financial/data procedure.
12. Disable maintenance mode and monitor through the launch window.
13. Record completion or activate rollback/kill switch.

A successful Render build or healthy endpoint alone is not production approval.
NyaySetu Bot and Document Studio are one release for this launch decision.
