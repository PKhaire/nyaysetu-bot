# NyaySetu 2026-07-31 RC3 Release Notes

## Purpose

RC3 supersedes RC2 as the next deployment candidate. It retains the
multilingual legal-guide, safety, payment, fulfilment, PostgreSQL, operational,
and fresh-release foundations while replacing the previous SendGrid integration
with usage-priced Amazon SES and correcting the Render worker override that
blocked startup.

This remains a release candidate. Passing local tests does not prove that AWS,
Meta, Razorpay, PostgreSQL, legal review, or operational staffing is ready.

## User and operations changes

- Booking, support, payment-review, and scheduled operational email now uses
  the Amazon SES v2 HTTPS API through the official AWS Python SDK.
- Email recipient lists are deduplicated and delivered as BCC destinations so
  recipients do not see one another.
- Payment-review alerts use a dedicated recipient list instead of exposing
  financial-review metadata to ordinary booking or support mailboxes.
- Operational alert emails no longer copy names, phone numbers, support
  narratives, legal categories, districts, or payment-provider identifiers.
  Staff must use the authenticated operations interface for those details.
- Every SES message carries only non-PII event type and record-ID tags for
  delivery monitoring and operator deduplication.
- SES's 50-recipient message limit is enforced before a provider call.
- The daily appointment report now contains booking IDs and time slots rather
  than names, legal categories, or districts.

## Reliability, security, and deployment changes

- The existing durable database outbox remains responsible for delayed email
  retries. The SDK is limited to one request per attempt to reduce duplicate
  delivery after an ambiguous timeout.
- SES does not offer a `SendEmail` idempotency token. Email therefore has an
  explicit at-least-once delivery contract: a timeout followed by an outbox
  retry can produce a duplicate, which operators identify using the stable
  event type and record ID.
- SES clients are created lazily, shared safely by the single-process threaded
  service, and use bounded 5-second connect and 15-second read timeouts.
- Provider errors are logged without credentials, recipients, subject lines,
  bodies, or case narratives.
- Staging and production readiness now require bounded AWS credential strength,
  an SES region, verified sender address syntax, valid recipients, and no more
  than 50 unique operational recipients.
- `render.yaml` carries the SES configuration from the web service to the
  outbox worker and explicitly pins `WEB_CONCURRENCY=1` plus
  `GUNICORN_CMD_ARGS=--workers 1`.
- The Blueprint now targets the existing `nyaysetu-bot-backend` Render service
  and records its `api.nyaysetu.in` custom domain, avoiding an accidental
  second backend during Blueprint adoption.
- Added exact-pinned `boto3` and transitive dependencies, refreshed the
  deterministic SBOM, and bumped its application version to
  `2026.07.31-rc3`.

## Candidate verification

- Complete local suite: `274 passed`.
- Overall test coverage: `64.38%`, above the enforced 60% floor.
- Focused SES/readiness/deployment/delivery/dependency checks: passed.
- Ruff, Python compilation, dependency consistency, and deterministic SBOM
  checks: passed.
- Dependency vulnerability audit: no known vulnerabilities reported.
- The dependency lock was also resolved for the production Python 3.11/Linux
  target.

GitHub Actions must repeat the exact-commit checks on Python 3.11.15. No live
SES message was sent during local verification because production credentials
must never be present in the source or release archive.

## Mandatory external gates

1. Verify the `nyaysetu.in` domain or exact sender identity in the selected SES
   Region and enable Easy DKIM.
2. Publish and validate SPF, DKIM, and DMARC records.
3. Request SES production access in that same Region; a sandbox account is not
   a production mail service.
4. Create a least-privilege IAM principal restricted to `ses:SendEmail` and
   the approved sender identity. Store credentials only as Render secrets.
5. Create an SES configuration set with delivery, bounce, complaint, reject,
   and delay monitoring.
6. Upload the exact RC3 candidate, confirm every GitHub Actions job is green,
   and create an isolated staging deployment.
7. Pass SES mailbox-simulator plus approved-recipient tests, including provider
   rejection, timeout, outbox retry, duplicate recognition, bounce, and
   complaint handling.
8. Complete the remaining PostgreSQL, Meta, Razorpay, legal/language, privacy,
   support, fulfilment, rollback, and production approval gates.

Until all required gates pass, RC3 is ready for GitHub and staging—not for
uncontrolled public production traffic.
