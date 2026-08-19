# Implementation, Testing and Launch

## Delivery strategy

Document Studio is delivered behind a feature flag and product allowlist. Each
phase has a reviewable result and does not require enabling public sales.

## Phase 0: design and legal discovery

Deliverables:

- Approved design baseline in this package.
- One selected pilot product and one reviewed-path product.
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
- Add a disabled `DOCUMENT_STUDIO_ENABLED=false` configuration gate.
- Add the feature-gated four-row home list, Document Studio landing-list
  contract and safe keyword routing. Prove the current three-button home is
  unchanged while the feature flag/product allowlist is disabled.
- Add admin aggregate/queue views without document contents in list endpoints.

Exit gate: migration/model parity, unit tests and transition/property tests
pass on SQLite test compatibility and disposable PostgreSQL.

RC8 implementation status: the safe subset is complete. Revision
`20260819_01` creates resumable UAT orders, immutable answer revisions and
privacy-minimised audit events. The feature-gated four-row home list and one
synthetic questionnaire are implemented. Product/version/review/artifact
models, rendering and storage remain later phases and must not be inferred
from the UAT tables.

## Phase 2: deterministic rendering

- Add pinned `python-docx` and update lock/SBOM.
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

## Phase 4: payment and advocate operations

- Create document-specific Razorpay order/link references and price snapshots.
- Reuse the existing exact provider-evidence and idempotency principles.
- Add document review assignment, revision, approve/reject and issuance audit.
- Add manual WhatsApp/contact delivery workflow.
- Add exception queues for payment, render, review and delivery failure.

Exit gate: delayed/duplicate/mismatched payments grant no wrong entitlement;
changed answers/templates invalidate approval; manual operations are auditable.

## Phase 5: staging/UAT

- Deploy only to isolated staging with synthetic data and Razorpay test mode.
- Activate one product for an internal allowlist.
- Run full user, advocate and operator journeys.
- Exercise backup/recovery, lifecycle, credential rotation and template
  suspension.
- Perform accessibility, mobile, Hindi/Marathi UI and support rehearsals.
- Reconcile storage inventory with metadata and verify no files enter logs.

Exit gate: signed acceptance evidence for product, legal content, privacy,
security, payment, operations and rollback.

## Test matrix

### Functional

- Every valid questionnaire branch and required/optional field.
- Back/edit/resume, normalization and repeated-party boundaries.
- Ineligible, urgent, conflicting and unknown-answer paths.
- Preview watermark/classification and exact confirmed fact summary.
- Review approve/revise/reject and stale-approval invalidation.
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
- [ ] Product is initially allowlisted with a daily order/capacity limit.
- [ ] Advocate staffing, SLA and manual fallback are confirmed.
- [ ] Support can suspend sales and resolve paid exceptions.
- [ ] Monitoring covers payment, render, review, delivery and overdue deletion.
- [ ] No known exposed credentials remain active.

## Rollout

1. Deploy disabled code and migrations.
2. Verify readiness and unchanged consultation/payment behavior.
3. Enable for named internal UAT identities in Razorpay test mode.
4. Enable one product for a small controlled production cohort.
5. Review every order manually during the observation window.
6. Increase capacity only after payment, content, delivery, support and deletion
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
