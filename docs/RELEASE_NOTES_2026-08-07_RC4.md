# NyaySetu RC4 Release Notes

Release date: 2026-08-07  
Content version: `legal-content-2026-08-r5`

## Purpose

RC4 is a content and user-safety refinement prepared while AWS account
activation is pending. It does not change the production infrastructure,
payment flow, database model, or external provider configuration.

## User-facing improvements

- Added dedicated Rent or Tenancy guidance in English, conversational
  Hindi/Hinglish, and Marathi.
- Added dedicated Housing Society Issue guidance in all three languages.
- Added dedicated Inheritance or Will guidance in all three languages.
- Expanded deterministic free-text routing for common rent, society, will,
  inheritance, succession, Hindi, and Marathi phrases.
- Added an explicit privacy warning to every legal guide instructing users not
  to send OTPs, PINs, CVVs, passwords, complete identity numbers, or full bank
  details in chat.
- Increased the two-level Legal Guides tree to 61 issue choices across nine
  legal areas while remaining within WhatsApp list limits.

## Safety and governance

- No statutory deadline, outcome prediction, filing method, or personalised
  legal advice was added.
- `LEGAL_CONTENT_VERSION` was advanced to `legal-content-2026-08-r5`.
- `LEGAL_CONTENT_REVIEWED_VERSION` and `LEGAL_CONTENT_REVIEWED_ON` must remain
  unset until a qualified reviewer approves this exact revision.
- The legal-review checklist now explicitly covers the new issue overlays and
  universal privacy wording.

## Validation completed locally

- Full pytest suite: 282 passed.
- Combined `app` and `services` coverage: 64.38%, above the enforced 60% gate.
- Ruff static analysis: passed.
- Locked dependency consistency (`pip check`): passed.
- Deterministic SBOM verification: passed.
- Project-source compilation and production configuration parsing: passed.
- Online `pip-audit` of `requirements.lock`: no known vulnerabilities found.
- Every configured keyword alias routes to its intended guide without a
  collision.
- All English, Hindi/Hinglish, and Marathi guides contain the privacy warning.
- Every guide remains within WhatsApp's 4,096-character text limit.
- Every issue list remains within WhatsApp's 10-row limit, with unique IDs and
  titles no longer than 24 characters.

The local suite ran on the closest official Windows runtime, CPython 3.11.9.
The existing GitHub Actions workflow remains the final authority for the exact
CPython 3.11.15/Linux Gunicorn check, PostgreSQL migration/rollback rehearsal,
full pytest/Ruff run, dependency lock, SBOM, and vulnerability gates after RC4
is uploaded.

## Deployment status

RC4 is not authorised for production deployment yet. Production remains
blocked until AWS account activation and SES setup complete, the managed
PostgreSQL and Render gates pass, provider smoke tests succeed, and a qualified
reviewer signs off `legal-content-2026-08-r5`.
