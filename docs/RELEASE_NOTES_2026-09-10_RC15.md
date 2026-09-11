# NyaySetu RC15 - Multi-Product Draft Studio Foundation

**Date:** 10 September 2026  
**Database schema:** unchanged at `20260908_01`  
**Document questionnaire:** unchanged at `mh-ll-questionnaire-2026-09-v3`  
**Status:** implemented and validated locally; not uploaded, deployed or
production-approved

## Why this candidate exists

Draft Studio needs to support additional independently governed products
without allowing one product's questions, template, approval or payment to be
used for another. RC15 establishes that seam before any second product is
registered.

## Included

- Adds a private product-definition registry with a small catalogue interface.
- Keeps the Maharashtra residential Leave & Licence product as the sole
  registered and globally visible product.
- Carries the explicit WhatsApp product selection into order creation.
- Resolves preview, payment, final rendering and release checks from the
  immutable `DocumentOrder.product_code`.
- Makes unknown products and mismatched order/package snapshots fail closed.
- Lets the admin release route select an explicit registered product and
  rejects unknown codes.
- Makes template path and renderer version part of the resolved product, while
  preserving the exact existing rendered artifacts.
- Adds characterization tests for registry visibility, immutable identity,
  unknown-product blocking and payment product mismatch.
- Adds the discovery-only product, questionnaire, source, advocate-review and
  implementation documents for a future single-cheque section 138 notice.

## Advocate-review status

The product owner reported that an advocate reviewed and approved the
discovery package for the proposed cheque-notice product. This is treated as
`APPROVED_FOR_TEMPLATE_DRAFTING` only. It does not approve any exact legal
template, questionnaire hash, price, customer offer, payment, signature,
issuance or dispatch. Those require a later authenticated, package-specific
release record and completed operational dependencies.

## Safety boundary

- No cheque-notice product is registered or customer-visible.
- No legal notice text, evidence upload, advocate-issued workflow or signing
  mechanism is implemented.
- No environment variable, database migration, dependency or hosting service
  is added.
- No feature flag, tester phone, sampled cohort or alternate customer schema
  is introduced.
- The existing agreement remains available to all users only through its
  existing global enablement and allowlist controls.

## Preserved product identity

| Evidence | SHA-256 / version |
| --- | --- |
| Template version | `mh-ll-en-2026-08-candidate-1` |
| Questionnaire schema | `mh-ll-questionnaire-2026-09-v3` |
| Template hash | `091bcff220c08374396e5d87c362c7c3ebe79cccbac2a0781568e60ee6d24194` |
| Schema hash | `edd95798ee85f898a9de782599a3fd53ee15abdb3bf354a130cf1787f5a63021` |
| Aggregate hash | `80b69faf49a2815c3e0b9d96a1d3bc354c53e4c3250a809b08dfff582b562f34` |
| Golden PDF hash | `f37f573125c7d407a05814922c6a7091c4fe1a80e40502f42d6042c848029c42` |
| Golden DOCX hash | `bc41414a90d312fa2ab6a3db50fa0b74849b86c41d34deb65749c6a603d5fcbc` |

## Local validation

Template hashes use canonical LF line endings so Windows and Linux resolve the
same package identity.
DOCX entries use deterministic stored ZIP members so their artifact hash is
also stable across operating-system compression backends.

- Full regression with the CI coverage gate: `380 passed`, `69.12%` coverage.
- Focused product/admin/payment/application regression: `147 passed`.
- Ruff, compile, dependency consistency, SBOM and diff-integrity checks pass.
- Gunicorn's Unix-only configuration import cannot run on Windows because it
  requires `fcntl`; the unchanged Linux check remains mandatory in GitHub CI
  and Render.
- Git commit SHA and CI evidence remain pending until the candidate is
  uploaded.
