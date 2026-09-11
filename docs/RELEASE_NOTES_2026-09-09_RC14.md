# NyaySetu RC14 - End-User Intake UX Candidate

**Date:** 9 September 2026  
**Database schema:** unchanged at `20260908_01`  
**Document questionnaire:** `mh-ll-questionnaire-2026-09-v3`  
**Status:** implemented locally; not approved, deployed or production-ready

## Why this candidate exists

Synthetic test users reported fatigue from consecutive WhatsApp questions.
RC14 keeps the RC13 legal, payment, privacy and release safeguards while
reducing the number of required interactions and making progress visible.

## Included

- Renames the customer-facing product from **Document Studio** to **Draft
  Studio** across WhatsApp, payment descriptions, delivery messages and current
  operator/product documentation. Existing `DOCUMENT_STUDIO_*` configuration,
  routes, database identifiers, object keys and the former chat keyword remain
  compatible; immutable generated-artifact metadata is retained so approved
  hashes are not changed by branding alone.
- Organises Draft Studio into five visible sections: Eligibility, Parties,
  Property & addresses, Dates & money, and Optional details.
- Reduces the shortest supported path from 22 to 19 answers by allowing one
  `Skip optional details` response to bypass all optional property-reference,
  included-area, additional-occupant and inventory questions.
- Adds `Save & Exit` throughout question entry, with `Continue Draft` resuming
  the exact saved question.
- Shows a concise section-completed message without requiring another reply.
- Replaces destructive full-form editing with a five-section correction
  picker; unrelated section answers remain saved.
- Uses a list for three-choice questions so the WhatsApp three-button limit
  does not remove the Save & Exit action.
- Tells users that the shortest document path takes about 5-7 minutes.
- Tells consultation users that booking normally takes about 3 minutes and
  that detailed advocate preparation is optional after payment.
- Keeps exactly one questionnaire schema for every user. No feature flag,
  tester cohort or dual-schema customer route is introduced.

## Release consequences

The question metadata, order and optional-navigation contract changed, so the
RC13 aggregate cannot authorize RC14. A licensed Maharashtra advocate must
review and approve the exact RC14 questionnaire, review copy, manifest and
golden artifacts. Native-speaker review and fresh WhatsApp staging UAT remain
mandatory.

## Local candidate identity

| Evidence | SHA-256 / version |
| --- | --- |
| Template version | `mh-ll-en-2026-08-candidate-1` |
| Questionnaire schema | `mh-ll-questionnaire-2026-09-v3` |
| Template hash | `091bcff220c08374396e5d87c362c7c3ebe79cccbac2a0781568e60ee6d24194` |
| Schema hash | `edd95798ee85f898a9de782599a3fd53ee15abdb3bf354a130cf1787f5a63021` |
| Aggregate hash | `80b69faf49a2815c3e0b9d96a1d3bc354c53e4c3250a809b08dfff582b562f34` |
| Golden PDF hash | `f37f573125c7d407a05814922c6a7091c4fe1a80e40502f42d6042c848029c42` |
| Golden DOCX hash | `6a2cfd9a59d19a3ebe8212bab116d5e63281b479f2b7c936c76fb5e4cb3a134d` |

Local validation passes: 374 tests with 69.06% total coverage, plus compile,
Ruff, SBOM and diff-integrity checks. The Git commit SHA and CI URL remain
pending until the candidate is reviewed and uploaded.
Template hashes use canonical LF line endings so Windows and Linux resolve the
same package identity.
