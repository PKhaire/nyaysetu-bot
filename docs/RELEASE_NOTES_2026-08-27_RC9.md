# NyaySetu RC9 — Controlled Document Studio Release

Date: 27 August 2026

Status: **implemented and automated-testable; production publication remains
blocked by external release evidence**.

## Outcome

RC9 replaces the RC8 tester-only answer-capture harness with a globally
addressable, fail-closed Document Studio workflow. When
`DOCUMENT_STUDIO_ENABLED=true`, every WhatsApp user sees the same Document
Studio entry; there is no phone-number allowlist, sampling cohort or hidden
test-user path.

The first catalogue product is an English Self-Service Draft for a narrowly
supported Maharashtra residential 11-month leave-and-licence arrangement:
one adult individual licensor, one adult individual licensee, both acting for
themselves, and one completed residential premises. Unsupported, disputed,
unusual or uncertain facts route to an advocate before preview or payment.

## Implemented

- Stable catalogue, eligibility rules and a deterministic 43-question
  questionnaire with bounded validation and resume/edit/reconfirm behavior.
- Immutable answer revisions and content hashes. Preview, payment and final
  artifacts bind to one exact customer-confirmed revision.
- Deterministic English rendering with a visibly watermarked preview and final
  PDF/DOCX parity/hash evidence.
- Exact Razorpay Payment Link and current Payment-resource verification;
  duplicate, mismatched, uncaptured or refunded evidence cannot grant release.
- Private S3-compatible artifact storage with non-public object keys,
  owner-authorized short-lived downloads and access-decision audit records.
- Append-only advocate approval/revocation history. The latest exact
  authenticated decision controls release and any hash/version mismatch fails
  closed.
- Seven-day unpaid/unattached draft expiry and 30-day final-artifact
  availability/deletion support in bounded maintenance.
- Global India-business-day capacity reservations. New drafts reserve one of
  10 configurable daily slots, confirmation consumes it, and an unconsumed
  ineligible, cancelled or retention-expired draft releases it. PostgreSQL
  transaction advisory locks prevent concurrent over-allocation.
- The maintenance cron inherits the same scoped Document Studio object-store
  identity as the web service, so expiry removes both database references and
  private S3 objects instead of leaving orphaned files.
- Protected Document Studio admin metadata and template-release operations
  that do not expose answer JSON, draft text, storage credentials or presigned
  URLs.
- Alembic revision `20260827_01` for payment, release, artifact and access-audit
  data, plus `20260903_01` for capacity evidence, building on `20260819_01`.

## Privacy and product boundaries

- No Aadhaar, PAN, bank credential, signature image, identity-document or
  evidence upload is requested or accepted.
- The output is labelled **Self-Service Draft**. It does not contain an
  advocate identity, signature, stamp, letterhead, certification or claim of
  matter-specific review.
- NyaySetu does not verify identity, title, authority, property facts or party
  capacity. Stamp duty calculation, execution and registration remain outside
  this workflow.
- Object URLs are never public or permanent and are not themselves treated as
  authorization.

## Configuration

Required for controlled staging:

```text
ENV=staging
DOCUMENT_STUDIO_ENABLED=true
DOCUMENT_STUDIO_CONSENT_VERSION=document-studio-self-service-2026-08
DOCUMENT_STUDIO_PRODUCT_ALLOWLIST=mh_residential_leave_licence_11m_self_service
DOCUMENT_STUDIO_DRAFT_TTL_DAYS=7
DOCUMENT_STUDIO_DAILY_CAPACITY=10
DOCUMENT_STUDIO_FINAL_TTL_DAYS=30
DOCUMENT_STUDIO_DOWNLOAD_TTL_SECONDS=600
DOCUMENT_STUDIO_PRICE_INR=<approved positive test amount>
DOCUMENT_STUDIO_S3_BUCKET=<private staging bucket>
DOCUMENT_STUDIO_S3_REGION=ap-south-1
DOCUMENT_STUDIO_S3_ACCESS_KEY_ID=<scoped credential>
DOCUMENT_STUDIO_S3_SECRET_ACCESS_KEY=<scoped credential>
RAZORPAY_MODE=test
```

The Blueprint keeps the switch off, price zero and storage unset by default so
that an incomplete environment cannot collect payment or release a document.

## Mandatory gates still open

The product must not be published to production until all are recorded:

1. A licensed Maharashtra advocate authenticates an `APPROVED` decision for
   the exact questionnaire, candidate template, renderer, aggregate hash,
   golden PDF hash and golden DOCX hash in the review-pack contract. The
   currently blank form is not approval.
2. The deployed hashes exactly equal the active approval and the review date
   has not expired or been revoked.
3. The private staging/production buckets, least-privilege credentials,
   encryption, Block Public Access, lifecycle and deletion evidence pass.
4. Razorpay staging tests prove exact price/payment/refund behavior, then the
   separately approved live price and credentials are configured.
5. PostgreSQL upgrade/rollback rehearsal, cross-user authorization, link
   expiry, renderer parity, interrupted resume, retention and operational
   monitoring tests pass, including concurrent requests for the final daily
   capacity slot and India-date rollover.

## Validation target

- Static analysis: `ruff check --no-cache .`
- Full tests: `pytest -q -p no:cacheprovider`
- Migration: upgrade through `20260903_01`, `alembic current`, `alembic check`,
  compatible downgrade/re-upgrade in isolated PostgreSQL
- Readiness: PostgreSQL, complete configuration and schema
  `20260903_01`

RC9 being present in the repository is not itself authorization to enable the
production switch.

## Local validation evidence

Recorded on 3 September 2026 against Python 3.11:

- `319 passed` with total coverage `66.57%` (required gate: 60%).
- Ruff static analysis passed with no findings.
- Python source compilation passed with an external bytecode cache.
- Dependency consistency and the committed SBOM check passed.
- Alembic reports exactly one head: `20260903_01`.
- The catalogue contains 43 questionnaire items and none exceeds WhatsApp's
  three-option interactive limit.
- No production credential pattern was found in application/configuration
  sources; secret-like values found by the broad scan are synthetic test and
  CI fixtures.

The local Windows host cannot execute Gunicorn's Unix-only configuration
loader (`fcntl`). The required GitHub Actions Linux Gunicorn check therefore
remains the authoritative pre-publication result.
