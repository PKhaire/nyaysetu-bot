# NyaySetu RC18 - Private Cheque-Notice Legal Package

**Date:** 11 September 2026  
**Database schema:** `20260911_01`  
**Release status:** local candidate; private and not customer-visible

## Outcome

RC18 implements Phase D for one narrowly scoped advocate-issued cheque-bounce
notice. The package is registered in the runtime catalogue but deliberately
excluded from the global product allowlist, WhatsApp intake and customer
payment path. No tester flag or user cohort controls availability.

## Product boundary

- One individual named payee acting personally.
- One living adult individual drawer acting personally.
- One cheque and one presentation/return event.
- Personal-loan fact pattern only.
- Exact bank return reason `FUNDS INSUFFICIENT` only.
- Part-payment, settlement, prior notice, existing proceedings, uncertain
  facts and every other category/reason route out before standard drafting or
  payment.
- Software records and validates facts but never decides legal eligibility,
  service, limitation, liability or outcome.

## Implementation

- Adds one immutable 18-response schema with bounded validation, explicit
  consent, double amount confirmation, executable supported/boundary/decline
  scenarios and mandatory clean evidence states.
- Adds an exact clause catalogue and candidate notice template based on the
  reviewed source register.
- Adds deterministic `FACTUAL_SUMMARY_PDF` and `NOTICE_REVIEW_PDF` package
  artifacts. The second is an unsigned internal review candidate, not an
  issued notice; the per-order advocate workflow remains the only issuance
  path.
- Allows both review artifact kinds through the private artifact-vault identity
  contract. This closes the staging failure where correct review PDFs were
  rendered but rejected before S3 upload.
- Extends the release ledger with a canonical classification-specific artifact
  hash map. Existing residential PDF/DOCX approval rows remain supported.
- Rejects the legacy PDF/DOCX approval payload for the cheque package, so the
  wrong evidence format cannot create an apparently valid decision record.
- Adds a system-only intake evaluation that verifies the exact package
  snapshot, current package approval, active immutable answer revision and
  clean mandatory evidence before advocate triage.
- Keeps `ADVOCATE_QUOTE` products free of a fixed catalogue price. Payment can
  arise only from an advocate-accepted, customer-confirmed immutable quote.

## Frozen local package identity

- Product: `in_ni138_single_cheque_individual_advocate_issued`
- Template version: `in-ni138-single-cheque-en-2026-09-candidate-1`
- Template hash: `a843b17c148ada97291c1eb39b943b4965546bf34bc137c2e39a3eaeeb2360a0`
- Schema hash: `7ff717628a53f886a3889fb9fb39ff1de2b7ef2bc860638b0ce2fd623902b872`
- Aggregate hash: `c22541d506ee10bb3a7c293b8ace8e439590bb1b5b471a29b169e9b312e81726`
- Factual-summary PDF hash: `b6f74ed92a59dc9224fcc63f042bffd2ecd2b90549fb2e16e4ed9483077f73d5`
- Notice-review PDF hash: `0f91329053f15c015d11fae8ad7e75b83bde552cfca081ece5d27f63376af96b`

These values identify this local source package. After deployment, compute the
manifest again in the staging runtime and authenticate that exact package;
never copy an earlier product approval.

## Verification evidence

- Phase D focused tests: 21 passed.
- Complete regression: 443 passed.
- Coverage gate: 71.63%, above the required 60%.
- Ruff, Python compilation, dependency consistency, deterministic SBOM,
  Alembic single-head and diff-integrity checks pass.
- Local live advisory audit reports no known vulnerabilities in the pinned
  runtime dependency set.
- Gunicorn configuration cannot execute on Windows because Gunicorn requires
  POSIX `fcntl`; GitHub CI on Linux remains the authoritative check.

## Still blocked

RC18 does not activate the product. Phase E still requires GitHub CI, staging
migration, exact runtime package approval, a production malware scanner,
scoped advocate/customer interfaces, cross-user and expiry security tests,
quote/tax/refund/SLA policy, signing and dispatch procedures, provider UAT,
translations and a recorded global launch decision.
