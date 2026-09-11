# NyaySetu RC13 - Simplified Intake Candidate

**Date:** 9 September 2026  
**Database schema:** unchanged at `20260908_01`  
**Document questionnaire:** `mh-ll-questionnaire-2026-09-v2`  
**Status:** implemented locally; not approved, deployed or production-ready

## Included

- Replaces the unlaunched 43-question Document Studio prototype with exactly
  one globally active conditional schema.
- Reduces the typical no-optionals Document Studio path to 22 answers.
- Groups equivalent eligibility confirmations while preserving fail-closed
  route-out behaviour.
- Removes unused furnishing input and repeated fixed-term acknowledgements.
- Adds explicit yes/no branches for property reference, included areas, other
  occupants and inventory.
- Replaces fragmented premises address inputs with PIN assistance, one complete
  customer-entered address and exact confirmation.
- Packages 1,666 Maharashtra PIN references from IndiaPost source revision
  `9903190eb2073826f869f0c384bb83a34a21ebd5`; its content hash and provenance
  are bound into the Document Studio schema hash.
- Shortens pre-payment consultation intake to issue summary and urgency, plus a
  deadline or safety note only when relevant.
- Offers a post-payment `Prepare for advocate` flow for stage, chronology,
  desired help/questions, document types and optional opposing party.
- Keeps every paid appointment valid when advocate preparation is incomplete,
  and exposes `INCOMPLETE`/`COMPLETE` in the admin appointment detail.
- Moves long Document Studio facts to an ordinary WhatsApp text message so the
  interactive confirmation body stays within provider limits.
- Removes the unused legacy four-field Document Studio UAT service and its
  separate test-only schema.
- Supersedes an incompatible active synthetic V1 draft with an audited empty
  V2 draft instead of interpreting old answers under the new schema.

## Release gates reset by this change

The questionnaire schema, confirmed snapshot, golden artifacts and aggregate
hash differ from the previously approved package. The prior approval must not
authorize this candidate. Before any deployment that permits payment:

1. Reconcile/cancel test payment links and clean synthetic V1 drafts/artifacts
   through the controlled maintenance procedure.
2. Generate the new release manifest and golden PDF/DOCX.
3. Have the licensed Maharashtra advocate review the grouped eligibility text,
   exact questionnaire/review copy and new golden files.
4. Record an authenticated approval for the exact new aggregate and golden
   hashes with a future review date.
5. Run full automated regression, then fresh WhatsApp/Razorpay/S3/admin UAT on
   this replacement only.

No production deployment or environment change is part of this candidate.

## Local candidate identity

Generated after the 369-test local regression pass:

| Evidence | SHA-256 / version |
| --- | --- |
| Template version | `mh-ll-en-2026-08-candidate-1` |
| Questionnaire schema | `mh-ll-questionnaire-2026-09-v2` |
| Template hash | `091bcff220c08374396e5d87c362c7c3ebe79cccbac2a0781568e60ee6d24194` |
| Schema hash | `e7517ee9de42dd2f962f77848e9b48ef7a6b7e5b018cb249c7a08203959b75d4` |
| Aggregate hash | `5815ecc1b3de5425ff84dedde8b3479740cf12b0de501662d5cad6633d6af72c` |
| Golden PDF hash | `f37f573125c7d407a05814922c6a7091c4fe1a80e40502f42d6042c848029c42` |
| Golden DOCX hash | `bc41414a90d312fa2ab6a3db50fa0b74849b86c41d34deb65749c6a603d5fcbc` |

Regenerate and compare these values after any change to the questionnaire,
postal reference, template, renderer or golden answers. The Git commit SHA and
CI URL are intentionally pending until the candidate is uploaded.
Template hashes use canonical LF line endings so Windows and Linux resolve the
same package identity.
DOCX entries use deterministic stored ZIP members so their artifact hash is
also stable across operating-system compression backends.
