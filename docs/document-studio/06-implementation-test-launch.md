# Implementation, Testing and Launch

## Delivery strategy

Document Studio is built and proven without enabling public sales. Staging may
use synthetic-only UAT controls. Production publication is bound to an
immutable, advocate-approved Template Version and is universal for all
eligible users; it has no named-user, cohort or percentage rollout gate.

## Phase 0: design and legal discovery

Deliverables:

- Approved design baseline in this package.
- One selected self-service pilot product. The advocate-review add-on remains
  a separately designed future product, not a first-release dependency.
- Advocate workshop notes converted into the catalogue standard.
- Customer wording, classification, price, revisions and refund decision.
- Retention/legal-hold decision and data-flow/privacy update.
- S3 account/bucket/IAM runbook reviewed but not yet provisioned.

Exit gate: no unresolved contradiction about what is being sold, who reviews
it, what the output means, or how long NyaySetu retains it.

## Phase 1: local domain foundation

- Add migrations and SQLAlchemy models for products, versions, orders, answer
  revisions, reviews, artifacts, access and audit events.
- Implement state transition and authorization services.
- Implement schema validation with synthetic examples.
- Keep the disabled staging/UAT gate while replacing the synthetic harness;
  do not carry named-user gating into production.
- Add the catalogue-driven four-row home list, Document Studio landing-list
  contract and safe keyword routing. Prove the current three-button home is
  unchanged while no production Template Version is active.
- Add admin aggregate/queue views without document contents in list endpoints.

Exit gate: migration/model parity, unit tests and transition/property tests
pass on SQLite test compatibility and disposable PostgreSQL.

RC9 implementation status: phases 1-4 are represented in code and automated
tests. Revision `20260827_01` extends the initial ledger with exact payment,
append-only release decisions, private artifact metadata and access audits;
revision `20260903_01` adds global daily-capacity reservations.
External S3 provisioning, authenticated exact-template approval and full
staging evidence remain release gates and must not be inferred from code
presence.

## Phase 2: deterministic rendering

- Generate deterministic minimal OOXML directly, avoiding an unnecessary
  runtime dependency, and keep lock/SBOM consistent.
- Build canonical render model and one pilot template package.
- Generate watermarked PDF and final PDF/DOCX locally.
- Bundle reviewed fonts and license notices.
- Add golden manifest/text/layout tests using synthetic people and addresses.
- Enforce render time, size, page and input limits.

Exit gate: advocates review generated synthetic boundary examples, not only the
source template.

## Phase 3: storage and download security

- Provision a private non-production S3 bucket in `ap-south-1`.
- Create a new least-privilege S3-only runtime credential.
- Configure public-access block, encryption, TLS and lifecycle.
- Implement storage adapter and metadata consistency handling.
- Implement ownership/role checks and 5-15 minute presigned GET URLs.
- Execute synthetic put/head/get/delete, expiry and cross-user denial tests.

Exit gate: no public object/ACL, no PII object key, deletion/recovery evidence
and AWS budget alerts are recorded.

## Phase 4: payment and document operations

- Create document-specific Razorpay order/link references and price snapshots.
- Reuse the existing exact provider-evidence and idempotency principles.
- Add paid self-service release, exception and refund-review operations. Do not
  add advocate review, signature or issuance to this first product.
- Add manual WhatsApp/contact delivery workflow.
- Add exception queues for payment, render, review and delivery failure.

Exit gate: delayed/duplicate/mismatched payments grant no wrong entitlement;
changed answers/templates invalidate approval; manual operations are auditable.

## Phase 5: staging/UAT

- Deploy only to isolated staging with synthetic data and Razorpay test mode.
- Exercise the globally visible product in isolated staging with synthetic
  facts only; the release gate remains unpublished until exact approval.
- Run full user, advocate and operator journeys.
- Exercise backup/recovery, lifecycle, credential rotation and template
  suspension.
- Perform English accessibility, mobile and support rehearsals. Hindi/Marathi
  questionnaire and legal text require separately reviewed later versions.
- Reconcile storage inventory with metadata and verify no files enter logs.

Exit gate: signed acceptance evidence for product, legal content, privacy,
security, payment, operations and rollback.

## Test matrix

### Functional

- Every valid questionnaire branch and required/optional field.
- Back/edit/resume, normalization and repeated-party boundaries.
- Ineligible, urgent, conflicting and unknown-answer paths.
- Preview watermark/classification and exact confirmed fact summary.
- Template suspension, stale-preview invalidation and paid-release recovery.
- PDF/DOCX parity, page headers, numbering, defined terms and fonts.
- Delivery, re-download, expiry and deleted-document behavior.

### Payment

- Valid test payment, duplicate webhook, delayed webhook and replay.
- Wrong amount/currency/reference/payment/link.
- Provider lookup timeout/current-state mismatch.
- Payment succeeds while template is suspended.
- Rendering/review fails after payment.
- Refund-review handoff and entitlement behavior.

### Authorization and storage

- Customer A cannot access Customer B order/artifact.
- Unassigned advocate cannot access an order.
- Operator list remains masked; access purpose is required and audited.
- Fabricated object key or artifact ID is rejected.
- Presigned URL expires and is absent from logs/database.
- Public bucket/ACL checks fail the release when misconfigured.
- Missing/orphan/corrupt/checksum-mismatched object handling.
- Lifecycle removes current/noncurrent versions according to policy.

### Reliability

- Render restart during generation/upload/state change.
- S3 timeout, throttling, partial upload and ambiguous response.
- PostgreSQL transaction rollback and concurrent transition attempts.
- Idempotent render/payment/review/delivery requests.
- Bounded retry and dead-letter/operator recovery.

### Legal/content

- Advocate-approved synthetic golden scenario for every clause branch.
- Exclusions never produce an ordinary document.
- Version, classification and execution limitations are visible.
- No signature/advocate approval appears on a non-approved artifact.
- Old paid order remains bound to its recorded version.

### Privacy

- Data minimization per field.
- Consent and terms version evidence.
- No answers/document contents in analytics, logs or notification subjects.
- Deletion, legal hold and customer request procedures.
- Temporary file removal on success and every failure path.

## Production launch gates

- [ ] Pilot product content hash has per-version advocate approval.
- [ ] Privacy/security/retention and cross-region processing are approved.
- [ ] S3 production bucket and IAM are isolated from staging and SES.
- [ ] AWS budget alert and operational owner are active.
- [ ] Razorpay live/ReKYC and product pricing are approved.
- [ ] Production migration is rehearsed and rollback-compatible.
- [ ] CI, dependency audit, migration check and synthetic UAT pass.
- [ ] The exact approved version is activated globally with a global daily
  capacity limit and emergency suspension control.
- [ ] Advocate staffing, SLA and manual fallback are confirmed.
- [ ] Support can suspend sales and resolve paid exceptions.
- [ ] Monitoring covers payment, render, review, delivery and overdue deletion.
- [ ] No known exposed credentials remain active.

## Rollout

1. Deploy disabled code and migrations.
2. Verify readiness and unchanged consultation/payment behavior.
3. Complete synthetic staging UAT in Razorpay test mode without publishing the
   candidate version.
4. Verify deployed questionnaire/clause/golden-output hashes equal the
   advocate-approved candidate.
5. Activate that exact version globally for all eligible users with a bounded
   daily capacity; do not use tester or customer flags.
6. Review operational evidence during the observation window.
7. Increase capacity only after payment, content, delivery, support and deletion
   evidence are clean.

## Rollback

Disable new product sales first. Do not delete paid orders or artifacts. Keep
the compatible additive schema, preserve audit/payment truth, finish or refund
review already-paid work manually, and revoke new download authorization if
artifact integrity is in doubt. Code rollback does not imply destructive schema
or object deletion.

## Acceptance evidence package

- Approved commit and dependency/SBOM results.
- Alembic head/current/check output.
- Product/template content hashes and advocate approvals.
- Synthetic golden PDF/DOCX examples.
- S3 configuration screenshots/export without credentials.
- Cross-user authorization, presigned expiry and deletion proof.
- Razorpay test-event matrix and exception outcomes.
- Staging UAT report and open-risk register.
- Go/no-go sign-off with operational owners and rollback decision.
