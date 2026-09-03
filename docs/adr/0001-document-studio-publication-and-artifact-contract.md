# ADR 0001: Document Studio publication and artifact contract

**Status:** Accepted

## Context

RC8 used a staging-only synthetic product and named-test-user controls. RC9
needs a safe legal-content gate without creating different customer
experiences or leaving a tester flag in the released product. The commercial
flow must prevent a paid output from differing silently from the preview the
customer accepted.

## Decision

1. Production availability is controlled by the lifecycle of an immutable
   Template Version: `DRAFT -> LEGAL_REVIEW -> APPROVED -> ACTIVE`, with
   `SUSPENDED` and `RETIRED` operating states.
2. An `ACTIVE` version is shown to every user who meets its eligibility rules.
   Production has no named-user, tester or percentage rollout allowlist.
3. Staging may contain unpublished synthetic products and Razorpay test-mode
   orders. Staging controls cannot publish a template in production.
4. A free watermarked preview precedes payment. Verified payment unlocks final
   PDF and DOCX generated from the exact same Confirmed Snapshot, Template
   Version and renderer version.
5. Final Artifacts remain available for 30 days and are then deleted. Only a
   Minimal Audit Record and separately required finance evidence remain.
6. The first product is a Self-Service Draft. Advocate review, signature,
   execution, registration and government-fee payment are separate services or
   customer actions.

## Consequences

- Legal approval is per exact content hash, not per repository deployment.
- Emergency suspension is global and auditable; already-paid exceptions need
  an explicit complete-or-refund operating decision.
- Rendering and entitlement tests must prove preview/final snapshot parity.
- Synthetic UAT occurs in staging before the version is activated globally.
- A future advocate-review product needs a new ADR or amendment because it
  changes responsibility, workflow, price and retention.
