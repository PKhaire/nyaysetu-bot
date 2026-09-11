# NyaySetu First Production Launch Checklist - Bot + Draft Studio

Updated: 9 September 2026

Release candidate: RC14 (integrated checklist filename retained for continuity)

Decision rule: NyaySetu Bot and Draft Studio launch together. There is no
base-bot-only production path in this checklist. Any unchecked mandatory gate
keeps the release at **NO-GO**.

## Current verdict

**NO-GO for production.** The simplified RC14 intake candidate is implemented
locally, but its changed Draft Studio aggregate is not yet advocate-approved
or deployed. Production isolation/live-provider configuration, translations,
real-user/advocate UAT, restore proof, final regression, staffing/policy
evidence, and a recorded GO decision remain mandatory.

Verified baseline:

- [x] Public API is reachable and the current staging readiness response is OK.
- [x] Current deployed staging schema is `20260903_01` and readiness is green.
- [x] RC11 email-disabled/manual-operations behavior, outbox health, payment
  reconciliation, maintenance risk-zero report, and Draft Studio final
  PDF/DOCX flow have staging evidence.
- [x] Local RC14 final validation passes with a single Alembic head
  `20260908_01`, updated SBOM, and the configured coverage gate.
- [ ] RC17 Phase C has a single local Alembic head `20260910_01`; complete
  regression, CI, staging migration and synthetic evidence are still required.
- [x] Draft Studio is globally available when enabled, not a test-user or
  cohort feature.
- [ ] All mandatory gates below are complete and supported by saved evidence.
- [x] RC14 full automated regression and static checks pass locally: 374 tests
  and the 60% coverage gate pass; total measured coverage is 69.06%.
- [ ] RC14 replacement aggregate and golden artifacts receive a new exact-hash
  advocate approval; the earlier approval must not be reused.

## A. Freeze and publish the exact RC14 release

- [ ] Review the local diff and confirm every intended RC10-RC12 file.
- [ ] Confirm no credentials, access tokens, personal test data, generated
  documents, `.env` file, or private advocate material is in the upload set.
- [x] Implement and test the global daily Draft Studio capacity
  control before freezing RC9. It must be atomic across all users and must not
  behave as a percentage rollout or test-user flag.
- [x] Rerun the full automated suite after the capacity change.
- [x] Rerun the full automated suite after named-admin MFA, audit-identity
  hardening.
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
- [ ] Run Alembic and confirm schema `20260910_01` is applied.
- [ ] Confirm `/health/live` and `/health/ready` return HTTP 200.

Evidence: sanitized environment inventory, service IDs, migration log, and
health responses. Never store secret values in evidence.

## C. Draft Studio legal and product approval

- [ ] Confirm the test-only earlier schema and synthetic artifacts/payment
  attempts have been reconciled and removed through controlled procedures.
- [ ] Verify the packaged Maharashtra PIN reference source revision, content
  hash, manual fallback and customer-confirmation wording.
- [ ] Obtain authenticated advocate review of the exact RC14 aggregate,
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
- [x] Implement the Phase C advocate-issued workflow foundation with synthetic
  matters only: linked advocate MFA, assignment/conflict/acceptance, immutable
  quote, exact payment, scanned private evidence, per-order issue approval,
  PDF-only delivery, dispatch proof, legal hold and audited failure paths.
- [ ] Complete Phase D's exact cheque-notice schema, clauses, template,
  validators, supported/boundary/decline golden artifacts and authenticated
  package approval. Discovery-pack approval alone is insufficient.
- [ ] Select and validate the production malware/file scanner and approve the
  evidence type/size, access, retention, incident and legal-hold procedures.
- [ ] Build and security-test the dedicated scoped advocate interface; never
  grant an advocate the general operations console or let an operator make a
  legal decision.
- [ ] Approve quote scope, expiry, tax/receipt/refund wording, advocate SLA,
  signing method and dispatch procedure before enabling payment.

Evidence: advocate decision record and approved template hashes.

## D. Draft Studio capacity and availability

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
- [ ] For advocate-issued evidence, prove clean-scan enforcement, assignment
  revocation, superseded-revision denial, active legal-hold preservation and
  post-hold deletion with synthetic files before accepting real evidence.

Evidence: sanitized storage/IAM settings, access tests, lifecycle rule, and
cleanup result.

## F. Draft generation, preview, and entitlement

- [x] Confirm in local automated tests that there is exactly one questionnaire
  schema for all users and the typical no-optionals path reaches review after
  19 answers across five visible sections.
- [x] Test locally the grouped eligibility route-outs, conditional navigation,
  known and unknown PINs, address confirmation, and complete-address
  rendering. Repeat these as human staging UAT before release.
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

- [x] Implement bounded Draft Studio reconciliation using current Payment
  Link and Payment evidence, exact recovery, mismatch quarantine, and exact
  full-refund confirmation.
- [ ] Complete Razorpay ReKYC and confirm settlements are unrestricted.
- [ ] Keep staging on newly rotated `rzp_test_*` credentials.
- [ ] Test successful, failed, cancelled, delayed, duplicated, and tampered test
  payments for consultations and Draft Studio.
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

- [ ] Verify the shortened booking minimum, conditional deadline/safety paths,
  post-payment preparation, incomplete preparation, completion and resume.
- [ ] Confirm production WhatsApp number, phone ID, token, app secret, verify
  token, webhook, and subscriptions are active.
- [ ] Rotate/invalidate every token or secret exposed in chat, screenshots, logs,
  or test notes.
- [ ] Verify `Hi`, home menu, Ask Legal Question, Book Consultation, Document
  Studio, and More Options in English, Hindi, and Marathi.
- [ ] Keep menus within WhatsApp limits and show Draft Studio to every user
  when the integrated launch is enabled.
- [ ] Verify signature rejection, replay protection, retries, and idempotency.
- [x] Formally disable internal email for V1 with
  `EMAIL_NOTIFICATIONS_ENABLED=false`; readiness, enqueueing, outbox cleanup,
  and Render deployment no longer require SES.
- [x] Document the V1 manual client/advocate notification procedure, SLA,
  fallback channel, and contact evidence.
- [ ] Do not message outside Meta's allowed window without an approved template.

Evidence: real-number UAT IDs, security/retry results, provider decision, and
manual notification runbook.

## I. Website, policies, consent, and privacy

- [ ] Describe consultation booking and Draft Studio accurately, including
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

- [x] Implement privacy-safe Draft Studio detail, one-order reconciliation,
  audited refund-review, and idempotent final-link redelivery APIs.
- [x] Implement individual password-plus-TOTP/recovery authentication,
  persistent lockout, named `ADMIN`/`OPERATOR`/`VIEWER` authorization, session
  invalidation, and verified browser audit identity.
- [ ] Set and securely back up a unique `ADMIN_MFA_ENCRYPTION_KEY`; never reuse
  `SECRET_KEY` and never expose setup seeds/recovery codes in evidence.
- [ ] Apply RC12 and enroll at least two active named MFA identities, including
  one `ADMIN`; store each set of recovery codes separately offline.
- [ ] Confirm production readiness reports `admin_access.mode=named_mfa`,
  `active_named_operators>=2`, `active_admins>=1`, and
  `production_compatible=true`; confirm shared-password fallback is rejected.
- [ ] Review roles for least privilege and protect Render shell/provider access
  with separate MFA; a shell `--actor-id` is accountability, not authentication.
- [ ] Rotate admin credentials and Flask secret before production.
- [ ] Verify account lockout, TOTP replay denial, one-use recovery, disable/reset
  session invalidation, login throttling, secure cookies, CSRF, session expiry,
  logout, role denial, and non-spoofable audit identity.
- [ ] Verify contact reveal is reason-gated, time-limited, and audited.
- [ ] Train at least two operators for reconciliation, document failures,
  consultation assignment, privacy requests, refunds, and incidents.
- [ ] Define advocate verification, activation, suspension, assignment, conflict
  check, handover, and outcome procedures.
- [ ] Keep UAT records separate from production reports.

Evidence: access review, operator/training sign-off, audit sample, and advocate
registry review.

## K. Jobs, monitoring, backup, and recovery

- [x] Put Draft Studio final-link delivery in the durable outbox; create
  short-lived URLs only during sending and scrub the order ID after acceptance.
- [x] Keep advocate-issued durable delivery PDF-only and require the exact
  current per-order approval before each fresh link/redelivery.
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

- [ ] Deploy the exact candidate SHA to staging with Draft Studio enabled for
  all users and a safe non-zero test price.
- [ ] Verify a new user sees all four choices: Ask Legal Question, Book
  Consultation, Draft Studio, More Options.
- [ ] Complete consultation booking, test payment, webhook confirmation, case
  brief, admin assignment, manual handover, and outcome.
- [ ] Complete every eligible Draft Studio path through paid PDF/DOCX download.
- [ ] Complete every supported cheque-notice path through assignment, evidence,
  quote, test payment, advocate draft, customer fact confirmation, exact issue,
  locked-PDF download and simulated dispatch. Exercise conflict, decline,
  unsupported, quote expiry, refund, scanner failure and legal-hold paths.
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
4. Apply/verify migration `20260910_01`.
5. Verify production configuration without printing secret values.
6. Verify `/health/live` and `/health/ready` internally.
7. Confirm private S3, jobs, alerts, admin identity, Meta webhook, and Razorpay
   live webhook.
8. Run one controlled live consultation payment smoke test.
9. Run one controlled live Draft Studio payment, generation, private PDF/DOCX
   download, admin/reconciliation, and deletion/expiry smoke test.
10. Confirm both low-value payments settle/reconcile correctly.
11. Resolve test records under the approved financial/data procedure.
12. Disable maintenance mode and monitor through the launch window.
13. Record completion or activate rollback/kill switch.

A successful Render build or healthy endpoint alone is not production approval.
NyaySetu Bot and Draft Studio are one release for this launch decision.
