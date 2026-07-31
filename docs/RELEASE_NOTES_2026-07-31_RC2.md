# NyaySetu 2026-07-31 RC2 Release Notes

## Purpose

This candidate supersedes the deployed/uploaded
`nyaysetu-bot-2026-07-29-rc1.zip`. It combines the existing reliability,
payment, persistence, operations and deployment foundation with the refined
multilingual legal-information experience.

It is a release candidate, not evidence of production approval. The exact
uploaded commit must pass GitHub Actions and staging verification before a
manual Render deployment.

## User-facing changes

- Two-level Legal Guides navigation across nine legal areas and 58 issue
  choices.
- English, conversational Hindi/Hinglish and Marathi deterministic guidance.
- Guided questions, immediate actions, document checklists, urgent escalation,
  location context and clear limitations.
- Issue-specific safety overlays for selected high-risk matters.
- Helpful/not-helpful feedback and consultation handoff.
- Additional multilingual free-text routing.
- Boundary-aware, most-specific FAQ matching so short aliases such as `fir`
  cannot match inside unrelated words and `legal notice` reaches the correct
  guide.
- Unicode-aware fallback across English, Hindi/Hinglish and Marathi labels.
- Ambiguous generic terms now route to `Other` / `Not Sure` rather than an
  arbitrary legal category.
- Expanded deterministic immediate-danger, self-harm and harmful-intent
  guardrails across English, Hindi/Hinglish and Marathi.
- Compatibility with seven older guide-button identifiers.
- Removal of duplicate feedback-prompt text in the guide delivery sequence.

## Product and governance changes

- Legal content version `legal-content-2026-07-r4`.
- Production readiness requires `LEGAL_CONTENT_REVIEWED_VERSION` to match
  `LEGAL_CONTENT_VERSION` plus a valid `LEGAL_CONTENT_REVIEWED_ON` date.
- Staging readiness now requires isolated PostgreSQL, the expected Alembic
  revision, strict provider/secret configuration and Razorpay test keys; live
  payment mode and unsigned webhooks are rejected.
- Added a qualified legal/native-language review checklist.
- Added the consolidated product, technology, launch, operations, budget,
  marketing and risk blueprint.
- Aligned active documentation to the approved fresh-release approach: no
  legacy user, booking or payment import.

## Release boundaries

- Generated print HTML/PDF files are local deliverables and are excluded from
  source/runtime packaging.
- No `.env`, credentials, Git metadata, caches, compiled Python, local
  databases or private keys may be included.
- AI defaults to the deterministic local provider. External generative AI is
  optional and remains subject to privacy/legal approval.
- Reminder template pairs remain empty until opt-in, Meta approval and
  localized staging tests are complete.

## Candidate verification

- Exact CI-style test/coverage command: `257 passed`, 64% overall coverage,
  above the enforced 60% regression floor.
- Ruff static analysis: passed.
- Python compilation, dependency consistency and deterministic SBOM checks:
  passed.
- Focused guide tests cover every configured alias and every visible localized
  category/subcategory label, including ambiguity and Hindi-context
  regressions.

These local results do not replace the GitHub Actions run on the uploaded
commit or the isolated provider/PostgreSQL staging evidence.

## Required gates

1. Upload this exact candidate to the repository root.
2. Confirm all GitHub Actions jobs are green.
3. Complete conversation/product review.
4. Obtain qualified legal and native-language approval.
5. Configure a fresh managed PostgreSQL staging environment.
6. Pass signed Meta, Razorpay test-mode and SendGrid staging tests.
7. Confirm support, fulfilment, refund/cancellation and incident owners.
8. Manually deploy the approved commit to Render.
9. Require `200` from `/`, `/health/live` and `/health/ready`.
10. Run a controlled WhatsApp and payment smoke test before user traffic.
