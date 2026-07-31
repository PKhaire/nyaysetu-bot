# Security, Risk, and Compliance Review

## Scope

This is a code-level review of the current repository. It is not a penetration
test, legal opinion, provider certification, or evidence that the production
environment is correctly configured.

## Implemented security controls

### Inbound requests

- Meta `X-Hub-Signature-256` is verified over raw bytes by default.
- Signature bypass is limited to an explicit non-production setting.
- Razorpay HMAC is verified over raw bytes before JSON parsing.
- Webhook verification/admin tokens use constant-time comparisons.
- A configurable request-size limit returns `413`.
- Request IDs, `nosniff`, and no-referrer response headers are applied.
- Invalid JSON and malformed provider structures are rejected safely.

### Payment integrity

- Only `payment_link.paid` with a final captured-payment/paid-link snapshot is
  considered.
- Before entitlement, the application independently reads the authenticated
  current Payment Link and Payment resources. It requires exact link/payment
  identity, booking reference/ID/token notes, stored INR amount, one full
  capture, `captured=true`, and zero/no refund state.
- Unique payment IDs and durable provider-event IDs prevent replay.
- Booking, user, webhook-event, and outbox mutations commit together.
- Provider lookup failure returns `503` without entitlement. Invalid current
  state and payment conflicts enter durable review and return `202`; terminal
  manual review statuses remain authoritative over delayed delivery.
- Webhook, scheduled reconciliation, and admin refund/review paths use a common
  booking-to-review lock order; refund then locks fulfilment/user state and
  recomputes cross-booking entitlement before commit.
- Unmatched/mismatched captured evidence is retained in a reconciliation queue;
  it never falsely pays a booking. Exact independent Payment Link plus current
  Payment-resource checks can recover a captured, non-refunded missed payment.
- User messages or screenshots cannot mark a booking paid.

### Message and delivery reliability

- Meta message IDs are unique in the lease-aware
  `inbound_message_events` inbox.
- An ordinary handler/database failure records `FAILED`; a failed/expired lease
  can be reclaimed for provider retry after a process crash.
- Outbox jobs persist external side effects and use bounded retry/backoff.
- A known-safe post-mutation text/button/list delivery failure marks the inbound
  claim `DONE` and queues one deduplicated send, preventing Meta replay from
  repeating business state. Ambiguous transport outcomes are not auto-resent.
- Completed/dead conversational delivery jobs scrub recipient and reply content
  from their retained payload.
- Step-level markers prevent a completed composite action from repeating.
- Provider result objects must explicitly report success.
- Reminder jobs are deduplicated and recheck the live approved-template,
  payment, fulfilment, schedule, and stale-window policy before sending.

### Secrets and access

- Secrets and operational contacts are environment configured.
- Meta app and Razorpay webhook signatures accept an optional previous secret
  for a bounded, zero-downtime rotation overlap.
- Production readiness rejects weak current WhatsApp tokens/app secrets,
  Razorpay credentials, admin/AI secrets, missing/invalid SES region,
  from-address or AWS access credentials, or a nonempty weak previous
  Meta/Razorpay signing secret.
- Booking email recipients default to empty; no recipient is hard coded.
- Email uses the boto3 SES v2 HTTPS client with bounded timeouts, immediate SDK
  retries disabled, at most 50 deduplicated BCC destinations, and durable
  outbox-controlled retries. Logs and alerts exclude recipients, bodies,
  credentials, and provider response bodies.
- Admin routes require a bearer or admin token and disable response caching.
- Admin metrics are aggregate. Sensitive support/fulfilment/reconciliation
  queues require token authentication; mutations additionally require an
  operator ID and append before/after audit records.
- Readiness and database logs do not reveal database credentials.
- The exact production lock has a deterministic CycloneDX SBOM checked by CI.
  It is an offline inventory, not a vulnerability result; the scheduled weekly
  `pip-audit` remains the time-sensitive dependency-advisory gate.

### Privacy minimisation

- Application logs use masked or keyed/pseudonymous identifiers and avoid
  message bodies, recipients, webhook bodies, and outbox payloads.
- Analytics properties are bounded and redact sensitive key names.
- Razorpay webhook bodies are represented by a hash rather than stored raw.
- AI prompts receive best-effort PII scrubbing and a non-reversible safety ID.
- Receipts use random private temporary files and are deleted after delivery
  attempts.
- Support/privacy contact defaults are empty to avoid publishing unverified
  information.

## Important limitations

### Production data start

The approved release is a fresh first release. It will use a new empty managed
PostgreSQL database and will not import old-bot users, bookings, or payment
records. The repository's legacy SQLite cutover utility therefore remains a
contingency rather than an active launch step. Repository presence still does
not prove that the new database is correctly revisioned, access-controlled,
backed up, restorable, shared by every runtime process, or monitored. Those
fresh-database checks remain launch gates.

### Rate limiting

Per-user and global throttles run before menu, support, media, and paid-session
branches and deduplicate limit notices per user/window. User ordering locks,
those counters, AI throttles, caches, and circuit breakers are in process
memory. They reset on restart and are not shared across workers/instances. The
supplied Gunicorn configuration enforces exactly one web worker; this avoids
split state but does not provide distributed abuse protection.

### Retention and data rights

Bounded maintenance deletes only approved terminal webhook/inbound events,
analytics, and completed outbox jobs and expires stale pending bookings. It
preserves financial, fulfilment, reconciliation, support, user, feedback,
failed, nonterminal, and legacy evidence and reports operational risk.
There is still no data-subject export/correction/deletion, anonymisation,
legal-hold, or backup-deletion workflow.

### AI privacy and legal quality

Pattern-based PII scrubbing can miss identifiers and context. The application
records versioned AI/payment consent, but revocation, data-subject rights, and
policy-governance workflows remain incomplete. External AI processing still
requires a defined purpose, vendor terms/DPA review, retention choices, and
user notice.

AI outputs and static guides can be incomplete, outdated, or wrong. Safety
rules cover selected urgent/harmful patterns but cannot detect every risk.
Prompts and content require Indian legal counsel and native-language review.

### Operational authorization

The admin token is a shared secret, not individual authentication, RBAC, or
MFA. Mutations require a declared operator ID and create an application audit
trail, but an operator can still assert another valid-looking ID. Admin queues
include sensitive user/payment matter data. Place them behind TLS, platform
identity/MFA and access controls, rotate the token, and avoid broad sharing.

### Consultation fulfilment and consumer risk

The application creates a fulfilment/SLA item for paid bookings and supports
audited advocate/named assignment, status/no-show/refund-review/refunded
transitions, and capacity-checked operator rescheduling. A recorded refund
cancels service entitlement but preserves payment evidence. It does not verify advocate
credentials/conflicts, connect the consultation channel, execute Razorpay
refunds, or import settlements/chargebacks. The business must not market those
capabilities until the operating process and policy exist.

## Risk register

| Severity | Risk | Current mitigation | Required action |
|---|---|---|---|
| Critical launch gate | Fresh production PostgreSQL is not yet proven, backed up, or restore-tested | Alembic baseline, expected-revision readiness and idempotent payment model | Provision an empty managed database, verify revision/access, enable backups, restore-test, reconcile staging payments and rehearse rollback |
| Critical launch gate | Paid appointment may lack staffed human fulfilment/refund path | Fulfilment/SLA queue, assignment/status audit, support | Define staffing, eligibility/conflicts, channel, cancellation/refund and payment-incident procedures |
| High | Provider or worker failure delays confirmation | Retryable webhook, durable inbox/outbox, five-minute exact-evidence reconciler | Monitor cron/provider errors and staff every open/recovered review plus 5xx/queue/dead/risk states |
| High | Sensitive legal/payment/support data is retained too long | Minimized storage and bounded terminal-artifact cleanup | Approve remaining deletion/anonymisation, backup, and legal-hold policy |
| High | Third-party AI receives sensitive or misleading context | Consent, PII scrub, safety checks, local fallback | Privacy/DPA/legal review and multilingual red-team evaluation |
| High | Shared admin token is compromised | Constant-time token check and no-cache | Platform access controls, rotation, audit trail, eventual RBAC/MFA |
| Medium | In-memory limits can be bypassed at scale | Single-worker deployment | Add distributed throttling/WAF before horizontal growth |
| Medium | Static legal guides become stale | Disclaimer and local fallback | Counsel-owned sources, review dates, correction workflow |
| Medium | Proactive WhatsApp messages breach consent/template rules | Transactional reminder pipeline is inert with empty pairs and revalidates live eligibility | Before populating a pair, obtain opt-in/template approval and test localization, frequency, suppression, and quality |
| Medium | Migration/cleanup policy drifts from code or legal approval | Alembic pre-deploy/CI and bounded scheduled maintenance | Freeze historical revisions, review dry-runs/TTL policy, and test restore/legal holds |
| Low | Readiness misses provider outage | Database/config health only | Add external synthetic monitoring without putting providers in readiness |

## Compliance and governance checklist

Before production, document and obtain appropriate review for:

- Privacy notice, lawful purpose, data minimisation, access, retention, and
  data-subject rights.
- AI notice/consent, provider data handling, safety limitations, and human
  escalation.
- Terms of service, scope of legal information, advocate relationship, and
  outcome disclaimers.
- Price, receipt/tax wording, payment expiry, reschedule, cancellation, refund,
  dispute, chargeback, and grievance handling.
- Advocate credentials, conflicts, supervision, recordkeeping, and professional
  obligations.
- Meta opt-in, template, quality, and business-messaging requirements.
- Razorpay and Amazon SES account/security requirements, including region-local
  identity/domain verification, DKIM/SPF/DMARC, sandbox exit, least-privilege
  `ses:SendEmail`, and monitored bounce/complaint/delivery events.
- Incident response, breach notification, evidence preservation, and secret
  rotation.
- Backup encryption, restore access, database roles, and production change
  approval.

Applicable Indian law and professional rules must be assessed by qualified
counsel for the real business entity, data flows, users, and service model.

## Security verification required

- Test invalid/missing signatures and oversized bodies.
- Replay identical and competing WhatsApp/Razorpay events.
- Inject database failure after a captured payment and prove exact-evidence
  reconciliation recovers once while ambiguity remains unpaid.
- Rehearse the same-review webhook/operator race with two PostgreSQL sessions;
  prove operator-first suppression, webhook-first refund revocation, no
  deadlock, and no lost terminal disposition.
- Prove an amount mismatch cannot mark a booking paid.
- Prove a failed notification remains retryable without duplicating a
  successful prior step.
- Verify receipt cleanup and absence of PII in provider-error logs.
- Review dependencies through the pinned dependency audit.
- Perform SAST, secret scanning, authenticated admin tests, and an external
  webhook/API penetration test.
- Restore a production-like backup and reconcile sampled Razorpay payments.
- Test operator-ID enforcement/audit, allowed fulfilment transitions,
  availability overrides, and maintenance protected-category preservation.

## Future controls

- Freeze each historical Alembic revision and extend retention only under
  approved legal-hold/privacy policy.
- Privacy request, consent revocation, and deletion/anonymisation workflows.
- Per-operator RBAC/MFA backed identity and tamper-resistant audit retention.
- WAF/distributed rate limiting and abuse alerting.
- Formal payment settlement/refund reconciliation.
- Source-backed legal content with provenance and review dates.
- Broader proactive messaging/campaign governance beyond the narrowly
  template-gated consultation reminders.
