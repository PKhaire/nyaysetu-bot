# NyaySetu RC17 - Advocate-Issued Workflow Foundation

**Date:** 10 September 2026  
**Database schema:** `20260910_01`  
**Runtime catalogue:** unchanged; residential agreement only  
**Status:** implemented and validated locally; not uploaded, deployed or public

## Included

- Adds verified advocate authority data and one-to-one named MFA advocate
  identities without granting access to the general operations console.
- Adds assignment, conflict, matter-review, immutable quote, private evidence,
  per-order issue approval, dispatch and legal-hold records.
- Requires clean file-scan results before storing evidence or advocate PDFs;
  storage remains private and download URLs are short-lived and never durable.
- Binds payment to the exact accepted quote. Webhook and reconciliation paths
  start advocate drafting only and do not auto-generate or deliver a final.
- Delivers only the exact locked issued PDF, supports audited fresh-link
  redelivery and rejects cross-user, expired or superseded-revision access.
- Extends bounded maintenance for private evidence, active legal holds and
  overdue advocate-assignment signals.

## Deliberately excluded

- No cheque-bounce legal text, clause catalogue, runtime questionnaire,
  customer price, product registration or global allowlist entry.
- No reusable advocate signature image, editable final DOCX, automatic claim
  of legal service, real dispatch or public advocate interface.
- No production file-scanner selection or staging legal-package approval;
  these remain Phase D/E prerequisites.

## Validation

The workflow has synthetic success, conflict, decline, unsupported, quote
expiry, payment failure/mismatch/refund, evidence denial/expiry, exact issue,
revision supersession, PDF-only delivery/redelivery, dispatch, legal-hold,
maintenance and SLA tests.

- Phase C and adjacent operations regression: `151 passed`.
- Complete repository regression: `422 passed`; CI-style measured coverage is
  `71.19%`, above the configured `60%` gate.
- Ruff reports no findings; `pip check` reports no broken requirements.
- Python source compilation and deterministic SBOM verification pass.
- Alembic reports one head, `20260910_01`; fresh/legacy migration behavior is
  covered by the passing migration tests.
- `git diff --check` reports no whitespace errors.

These local checks do not prove zero defects or replace Linux CI, PostgreSQL
migration validation, dependency vulnerability audit, production scanner
selection, legal-package approval, security review or staging UAT.
Gunicorn's configuration checker depends on Unix `fcntl` and therefore remains
a Linux CI check; it cannot execute in this Windows worktree.
