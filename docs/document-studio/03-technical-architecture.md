# Technical Architecture

## Context and constraints

Document Studio extends the existing single-worker Flask, PostgreSQL, Razorpay,
WhatsApp, outbox and admin architecture. V1 must remain compatible with the
one-process correctness constraint and current Render Singapore deployment.
It does not require a new web service or database at pilot volume.

Generated files are object-storage data. PostgreSQL stores workflow truth and
artifact metadata, not PDF/DOCX byte arrays. Amazon S3 in `ap-south-1` is the
approved initial provider. Questionnaire and operational data continue to be
processed by the existing Singapore application/database; this cross-region
fact must be documented rather than described as India-only storage.

## Component view

```text
WhatsApp/user
    |
    v
Flask Document Studio routes/state machine
    |              |                 |
    |              |                 +--> Razorpay payment links/current evidence
    |              +--> deterministic template/render service
    |                                   |--> PDF (ReportLab)
    |                                   +--> DOCX (python-docx)
    v
PostgreSQL ------------------------------> private S3 ap-south-1
orders/answers/templates/reviews             preview/final artifacts
payments/artifact metadata/audit             lifecycle deletion
    |
    +--> admin/advocate review queue
    +--> existing outbox/manual WhatsApp delivery
```

## Proposed modules

| Module | Responsibility |
| --- | --- |
| `services/document_catalog_service.py` | Resolve active product/template, eligibility and price snapshot |
| `services/document_intake_service.py` | Validate typed answers, revisions and customer confirmation |
| `services/document_render_service.py` | Build canonical render model; generate bounded PDF/DOCX |
| `services/document_storage_service.py` | Private S3 put/head/delete and short-lived presigned download |
| `services/document_review_service.py` | Assignment, revision, approval and issuance transitions |
| `services/document_delivery_service.py` | Authorized delivery record and outbox/manual handoff |
| `jobs/document_retention.py` | Bounded expiration verification and metadata terminalization |
| `templates/document_studio/` | UI templates only; legal templates live in a governed package/location |

Legal templates must not be editable from an unaudited admin text box. A later
template-management UI requires separate roles, review and publishing controls.

## Logical data model

### `document_products`

Stable commercial identity: product code, display metadata, supported language,
jurisdiction/scope, review mode, active status, current published version,
price configuration and retention class.

### `document_template_versions`

Immutable version: product, semantic version, source package reference,
questionnaire schema, clause manifest, renderer version, content hash, legal
owner/reviewer, approval/effective/next-review dates and lifecycle status.

### `document_orders`

Customer workflow: public random reference, user, product/template version,
state, output classification, price/currency snapshot, terms/consent versions,
payment references, active answer revision, timestamps and exception code.

### `document_answer_revisions`

Immutable confirmed answer snapshots: order, revision, encrypted/sensitive
structured payload or normalized relational representation, schema version,
customer confirmation timestamp and SHA-256 hash. The implementation choice
must support field-level deletion/redaction and avoid indexing sensitive text.

### `document_reviews`

Assignment and decision: order, advocate, answer/template/artifact hashes,
decision, structured reason codes, bounded note, timestamps and supersession.

### `document_artifacts`

Metadata only: order, kind (`PREVIEW_PDF`, `REVIEW_PDF`, `FINAL_PDF`,
`FINAL_DOCX`, `SIGNED_PDF`), immutable revision, provider/bucket/object key,
size, MIME type, SHA-256, encryption mode, created/expiry/deleted timestamps and
generation status. No presigned URL is stored.

### `document_access_events`

Who requested access, artifact, purpose, decision, timestamp, request ID and
coarse client/security context. Do not store the generated signed URL.

### `document_audit_events`

Append-only business events for state transitions, template publication,
assignment, approval, exception handling and retention. Payloads contain stable
IDs and reason codes, not rendered clauses or full answers.

## Object naming

Object keys contain no name, phone, address, email or document title:

```text
production/orders/<random-order-uuid>/<artifact-uuid>/v0001.pdf
production/orders/<random-order-uuid>/<artifact-uuid>/v0001.docx
```

The database maps a business reference to the object key. Customer-visible
download filenames are generated safely at response time and exclude sensitive
facts.

## Storage contract

Runtime credentials are a new S3-only IAM principal, separate from SES. Minimum
runtime access is limited to the production bucket/prefix and required
`PutObject`, `GetObject`, `HeadObject` and controlled `DeleteObject` operations.
Bucket-policy, public-access, lifecycle and IAM administration are not granted
to the web runtime.

Baseline bucket configuration:

- Region `ap-south-1`.
- Block Public Access enabled at account and bucket level where compatible.
- Object ownership enforced; ACLs disabled.
- SSE-S3 encryption initially. SSE-KMS is a later documented decision.
- TLS-only bucket policy.
- CORS restricted to exact NyaySetu origins and required methods if direct
  browser upload is later enabled.
- Versioning decision coupled to lifecycle rules for noncurrent versions.
- Lifecycle rules for temporary/unpaid/final prefixes and incomplete multipart
  uploads.
- Cost allocation tags and AWS budget/anomaly alerts.

## Download authorization

1. Authenticated user or authorized operator asks NyaySetu for one artifact.
2. Application loads order and artifact metadata and checks ownership, state,
   expiry, deletion, output entitlement and role/purpose.
3. Application appends an access decision event.
4. On allow, it generates a GET presigned URL valid for 5-15 minutes.
5. Client downloads directly from S3. The URL is never written to logs,
   database, analytics or support notes.

Presigned URLs are bearer capabilities until expiry. A short expiry does not
revoke a copied URL immediately. High-risk revocation requires credential/policy
action or an application-proxy design; the V1 risk decision must be recorded.

## Rendering contract

- Rendering input is a canonical model produced from the confirmed revision,
  not raw request JSON.
- Templates cannot execute arbitrary Python, shell commands or network calls.
- Every clause insertion has a stable clause code and version.
- PDF and DOCX outputs display product/template version, classification and
  unique document reference in a non-misleading location.
- Temporary local files use randomized private paths and are deleted in a
  `finally` block after S3 upload.
- Maximum render time, output size, page count and repeated-group count are
  bounded.
- Fonts are bundled with license records. English/Hindi/Marathi layout is
  tested using representative synthetic content before a language is enabled.
- Artifact hashes are calculated before upload and verified from returned S3
  metadata or a subsequent `HeadObject` contract.
- Published artifact bytes are immutable. A DOCX is an editable customer copy,
  not proof that the customer has preserved or executed the released version;
  the PDF/hash remains the reference artifact for review and issuance records.

ReportLab already exists in the runtime. `python-docx` is a proposed pinned
direct dependency for editable DOCX output and must be added to the lock and
SBOM through the repository's dependency process.

## API shape

Representative endpoints; exact paths remain subject to implementation review:

```text
GET    /document-studio/products
POST   /document-studio/orders
GET    /document-studio/orders/<public_ref>
PUT    /document-studio/orders/<public_ref>/answers
POST   /document-studio/orders/<public_ref>/confirm
POST   /document-studio/orders/<public_ref>/preview
POST   /document-studio/orders/<public_ref>/payment-link
POST   /document-studio/artifacts/<artifact_ref>/download

GET    /admin/document-orders
POST   /admin/document-orders/<public_ref>/assign
POST   /admin/document-orders/<public_ref>/review
POST   /admin/document-orders/<public_ref>/issue
POST   /admin/document-products/<code>/suspend
```

Mutating routes use CSRF protection for browser sessions, idempotency keys
where replay is possible, database authorization and append-only audit events.
They never accept storage object keys or prices directly from the browser.

## Background processing

At pilot scale, bounded small renders may execute synchronously after state is
committed, with retryable work represented durably. If measured generation
time threatens web latency or reliability, add a document-generation outbox
kind processed by a bounded worker/cron. A continuously paid worker is not a V1
prerequisite.

## Observability

Metrics include counts and latency by product code, output kind, lifecycle
state and error code. Logs include request/order/artifact identifiers but no
answers, object URL, document text or storage credentials. Readiness may verify
configuration shape without writing test objects; an explicit synthetic
provider smoke test verifies put/head/get/delete before launch and periodically
under controlled operations.
