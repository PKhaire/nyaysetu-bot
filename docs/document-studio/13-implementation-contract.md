# Implementation Contract

This specification turns approved decisions into deep module interfaces. It is
not evidence that the production feature is implemented.

## Deep modules

### `DocumentCatalogue`

Lists active products, resolves an immutable Template Version and opens a
product-bound order. It hides publication states, eligibility metadata, clause
manifests, prices and hash checks. Only `ACTIVE` versions are customer-visible.

### `DocumentOrderWorkflow`

Commands: start, answer, resume, confirm, preview, request payment, apply
verified payment, release final and authorize download. It owns state and
idempotency, hiding revisions, hashes, entitlements, expiry and audit. Flask
and WhatsApp translate I/O; they do not implement transitions.

```text
STARTED -> ELIGIBILITY -> DRAFTING -> CONFIRMED -> PREVIEW_READY
        -> PAYMENT_PENDING -> PAID -> FINAL_GENERATING -> FINAL_AVAILABLE
        -> EXPIRED

Pre-payment -> ABANDONED or ROUTED_OUT
Ambiguous provider/render/storage -> NEEDS_ATTENTION
```

Payment never relies only on a client callback; it uses signed idempotent
webhook evidence and provider-current-state verification.

### `DeterministicDocumentRenderer`

Accepts a validated Confirmed Snapshot, Template Version and artifact kind;
returns bytes and a manifest of hashes, MIME, size and renderer version. It
hides template loading, clause selection, escaping, PDF/DOCX generation and
parity. It has no network or generative-AI access.

### `DocumentArtifactVault`

Stores immutable artifacts, authorizes bounded download, deletes, verifies
absence and reconciles inventory. It hides S3 keys, presigning, encryption and
lifecycle. PostgreSQL stores metadata, never bytes or URLs.

## Provider seams

| Port | Production adapter | Test evidence |
| --- | --- | --- |
| `PaymentEvidencePort` | Existing Razorpay | Fake for paid/delayed/duplicate/mismatch/timeout |
| `ObjectStorePort` | Private S3 Mumbai | In-memory fake plus isolated-bucket suite |
| `MessageDeliveryPort` | WhatsApp/outbox | Recording fake plus Meta staging smoke test |
| `ClockPort` | UTC, IST presentation | Fixed date/expiry boundaries |

Domain objects never depend on boto3, Razorpay JSON or WhatsApp payloads.

## Universal menu

When a product is active, use a WhatsApp list in this order:

1. Ask Legal Question
2. Book Consultation
3. Document Studio
4. More Options

On list failure use numbered text and accept `1`-`4` plus stable commands.
There is no tester-ID, customer allowlist or percentage flag. No unapproved
product may be listed.

## Template package

Each immutable package contains metadata; eligibility/questionnaire schema;
exact clauses and ordered hashes; disclosures/summary/next steps;
styles/fonts/renderer compatibility; synthetic golden inputs/outputs; and
advocate approval/effective/next-review evidence. Startup/publication validates
all hashes and fails closed.

## Invariants

- Random references and database authorization before every object action.
- Private S3, public-access block, TLS, encryption, no ACLs, S3-only credential.
- 5-15 minute download URL, never stored/logged.
- Bounded input/render/page/artifact size and escaped facts.
- Templates execute no code/network; temporary files always removed.
- Audit contains IDs/reasons/hashes, not content.
- One active version per product/language/jurisdiction; activation/suspension is
  authenticated and audited.
- One global daily capacity for all eligible users. Starting a new order
  reserves atomically, confirmation consumes, and an unconsumed ineligible,
  cancelled or retention-expired draft releases the slot. Payment failure does
  not release already-consumed drafting capacity.

## Migration and evidence

Use additive Alembic revisions; do not treat RC8 UAT tables as the final model
without review. Preserve existing consultations/payments/WhatsApp. Required
evidence covers state/idempotency, all eligibility routes, golden PDF/DOCX
parity, preview/final manifest binding, payment failures/replay, cross-user and
expired access, S3 policy/checksum/orphan handling, 7-/30-day deletion,
universal menu fallback and PostgreSQL migration rehearsal.
