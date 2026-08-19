# NyaySetu RC8 — Document Studio UAT Foundation

Date: 2026-08-19

## Outcome

RC8 adds a feature-gated, staging-only Document Studio test harness to the
current WhatsApp bot. It is designed for synthetic internal testing and is not
a legal-document product.

When the feature is enabled in a staging-labelled service, the home screen is
a WhatsApp list with this order:

1. Ask legal question
2. Book consultation
3. Document Studio
4. More Options

When the feature is disabled, the existing three quick-reply buttons remain
unchanged. This avoids the WhatsApp three-button limit without breaking the
current production navigation.

## Implemented in RC8

- One allowlisted synthetic product: `residential_agreement_mh_uat`.
- Guided four-answer questionnaire with input validation.
- Draft persistence, seven-day resume window, edit, cancel and recent-tests
  paths.
- Immutable user-confirmed answer revision with SHA-256 content hash.
- Privacy-minimised state-transition audit events.
- Token/session-protected admin UAT ledger that excludes answers, names and
  WhatsApp identifiers.
- Additive Alembic revision `20260819_01`.
- English, Hindi and Marathi navigation keys.
- Deployment fail-closed controls: the feature is disabled by default and a
  production-labelled service is not ready while it is enabled.

## Deliberately not implemented

RC8 does not:

- generate a legal agreement, notice, PDF or DOCX;
- accept payment or create a Razorpay booking;
- collect identity/evidence files;
- upload to S3 or create a download link;
- add an advocate signature, review or approval;
- expose a public document API.

The completion message states these limits. Use synthetic people, addresses
and disputes only.

## Staging configuration

Enable only on the existing staging service:

```text
ENV=staging
DOCUMENT_STUDIO_ENABLED=true
DOCUMENT_STUDIO_UAT_ONLY=true
DOCUMENT_STUDIO_CONSENT_VERSION=document-studio-uat-2026-08
DOCUMENT_STUDIO_PRODUCT_ALLOWLIST=residential_agreement_mh_uat
DOCUMENT_STUDIO_TESTER_WA_IDS=<comma-separated test numbers with country code>
DOCUMENT_STUDIO_DRAFT_TTL_DAYS=7
RAZORPAY_MODE=test
```

The Render Blueprint keeps `DOCUMENT_STUDIO_ENABLED=false`. Enabling it is a
manual, recorded staging UAT action. Do not enable it on a production-labelled
service. Only the WhatsApp IDs in `DOCUMENT_STUDIO_TESTER_WA_IDS` can see or
enter the UAT flow.

## Verification

- Static analysis and targeted Document Studio/migration/admin/webhook tests
  must pass.
- Run the entire CI-equivalent suite before upload.
- Apply Alembic `upgrade head` and verify `/health/ready` reports schema
  `20260819_01` and `ok=true`.
- Verify the admin ledger at `GET /admin/document-orders` contains metadata
  only.
- Verify no booking, payment link, artifact, signature or download is created.

## Next gate

RC8 authorizes navigation and questionnaire UAT only. Rendering, private S3
storage, payment, advocate review, signing and issuance remain later phases
and require their separate legal, security and operational approvals.
