# NyaySetu RC16 - Multi-Product Draft Studio Catalogue

**Date:** 10 September 2026  
**Database schema:** unchanged at `20260908_01`  
**Document questionnaire:** unchanged at `mh-ll-questionnaire-2026-09-v3`  
**Status:** implemented and validated locally; not uploaded or deployed

## Included

- Validates the global product allowlist against the immutable runtime
  catalogue and hides the entire customer catalogue when configuration is
  partial or inconsistent.
- Rejects duplicate, structurally incomplete or key-mismatched internal
  product definitions before any catalogue row becomes visible.
- Adds `DOCUMENT_STUDIO_PRODUCT_PRICES_INR`, an immutable comma-separated
  `product_code=whole_inr` map. The current `DOCUMENT_STUDIO_PRICE_INR` remains
  a compatibility fallback when the new setting is blank or absent.
- Requires price keys to match enabled products exactly and rejects duplicate,
  malformed, unknown, disabled, missing, zero or negative product prices.
- Returns a non-secret release result for every enabled product from
  `/health/ready`; staging and production readiness fail when any enabled
  product is unavailable or lacks an exact current advocate approval.
- Adds `/admin/document-products` and product filters for document orders,
  metrics and operator audit evidence.
- Uses catalogue-owned product metadata for WhatsApp rows and Razorpay payment
  descriptions. Product labels use translation keys, catalogue pages stay
  within the ten-row provider limit, and numbered text replies remain usable.
- Requires every existing order's template version, schema hash, template hash
  and output classification to be present and exactly match its resolved
  package before preview or payment.
- Blocks disabled products at customer selection, order creation, preview and
  payment while preserving fulfillment and authorized artifact access for an
  already captured exact payment.
- Exercises a synthetic non-legal second product only through automated-test
  injection. It is not present in the runtime catalogue.

## Preserved boundaries

- The Maharashtra residential agreement is the sole registered runtime
  product and remains globally visible to all users when enabled.
- No tester phone, cohort, percentage rollout, alternate customer schema or
  per-user feature decision exists.
- The existing product code, template/schema versions, aggregate hash and
  golden PDF/DOCX hashes are unchanged.
- The future cheque-bounce notice remains documentation-only and has no legal
  text, workflow, payment, upload, signature, issuance or customer entry.
- No database migration or new hosting dependency is required.

## Configuration transition

Existing staging remains compatible with:

```text
DOCUMENT_STUDIO_PRICE_INR=299
DOCUMENT_STUDIO_PRODUCT_PRICES_INR=
```

The preferred equivalent is:

```text
DOCUMENT_STUDIO_PRODUCT_PRICES_INR=mh_residential_leave_licence_11m_self_service=299
```

Do not configure both as independent sources of truth. When the map is
non-empty, it is authoritative.

## Local validation

- Template/package identity uses canonical LF line endings so Windows and
  Linux checkouts resolve the same hashes.
- DOCX entries use deterministic stored ZIP members so approved artifact
  hashes do not depend on the operating-system compression backend.

- Focused Phase B catalogue, workflow, admin, readiness and deployment tests:
  `110 passed`.
- Full regression with the CI coverage gate: `400 passed`, `81.68%` coverage.
- Ruff, Python compilation, dependency consistency, deterministic SBOM,
  Alembic single-head and diff-integrity checks pass locally. A fresh audit of
  `requirements.lock` reported no known published vulnerabilities.
- Linux Gunicorn configuration, PostgreSQL migration parity and the repeated
  dependency vulnerability audit remain GitHub CI gates.
