# Business Perspective

## Opportunity

People seeking legal help often do not know the right category, what evidence
to prepare, what a consultation will cost, or how to find a next step they can
trust. A WhatsApp-first journey reduces installation and account friction while
giving the service a structured intake record before a consultation.

NyaySetu's useful differentiation is not “more chat time.” It is a clearer,
safer journey from legal uncertainty to an informed next action.

## Current value proposition

For the user:

- Start in a familiar channel and choose English, Hinglish, or Marathi.
- Get limited general legal information before deciding to pay.
- See the consultation scope, fee, availability, and full summary before a
  payment link is created.
- Track the latest booking, reach support, and prepare documents.
- Receive confirmation only after verified provider payment.

For operations:

- Capture consistent name, location, category, subcategory, date, and slot.
- Prevent duplicate message/payment processing.
- Enforce configurable slot capacity.
- Persist support, feedback, analytics, webhook, and delivery records.
- Retry payment-success and email side effects through an outbox.
- View aggregate metrics and recent support tickets through protected APIs.

## Implemented commercial model

The code implements one configurable fixed-fee consultation product. The
default is INR 499, but production price must be explicitly approved and set.
Razorpay creates a full-payment link; partial payment is disabled. Revenue is
recorded only when a signed captured-payment event and independent current
Payment Link/Payment reads agree on booking ownership, stored amount, one
captured payment, and no refund.

Paid users receive time-bound AI access through the booked slot end. That is an
information feature, not proof that an advocate has been assigned or that a
human consultation has been delivered.

Possible subscriptions, document services, advocate marketplaces, or
enterprise licensing are future business models and are not in the current
code.

## Funnel

```text
WhatsApp entry
  -> language and home
  -> AI information or booking scope
  -> verified intake details
  -> capacity-filtered date/slot
  -> review and explicit pay action
  -> pending booking and Razorpay link
  -> verified payment
  -> notification and paid window
  -> feedback
```

The code records privacy-minimised events such as user creation, menu/guide
views, booking review, payment-link creation, payment confirmation,
consultation completion, support, and feedback. These support funnel analysis
after data-quality validation.

## Metrics available now

The protected metrics API provides:

- Total and recent users.
- Booking totals and status distribution.
- Recent category distribution.
- Recorded paid booking value.
- Open support-ticket count.
- Feedback count and average rating.
- Recent analytics-event count.

Recommended business reporting:

- Onboarding-to-AI and onboarding-to-booking rates.
- Booking review-to-link and link-to-paid conversion.
- Capacity rejection and payment-link expiry rate.
- Payment confirmation latency.
- Outbox retry/dead-job rate and notification latency.
- Support backlog age and resolution time.
- Consultation completion and feedback rate.
- Repeat use by consented, privacy-safe cohorts.

The current metrics endpoint does not calculate these full funnels or support
SLAs automatically.

## Trust and retention strategy

Healthy engagement comes from successful tasks and useful return paths:

- Persistent home navigation.
- Appointment status and payment recovery.
- Category-specific consultation preparation.
- Local legal guides.
- Transparent AI consent and privacy information.
- Reachable support and post-consultation feedback.

Do not optimize for conversation length, forced loops, repeated notifications,
or urgency pressure. In a legal product those patterns can reduce trust,
increase support cost, and create consumer-protection risk.

## Operating model required

Code alone does not deliver a consultation. The business must define:

- Who fulfils each paid appointment and through which channel.
- Coverage hours, capacity ownership, advocate eligibility, and conflict checks.
- Contact SLA after payment and no-show handling.
- Reschedule, cancellation, refund, and dispute rules.
- Support ownership, escalation, and ticket-resolution procedure.
- Receipt/tax wording and record-retention obligations.
- Legal-content ownership, approval cadence, and correction procedure.
- Privacy contacts, data-subject requests, and incident response.

The repository now creates a fulfilment/SLA item after payment and provides an
audited operator assignment/status workflow. It can record a reviewed
`REFUNDED` outcome, cancel service entitlement while preserving payment
evidence, and keep a terminal payment-review disposition authoritative. It
does not execute the provider refund. These remain launch gates because code
cannot supply qualified staffing, conflict review, the consultation channel,
external refund execution, or an approved refund process.

## Production readiness

Implemented foundation:

- Managed-database-capable persistence.
- Capacity-safe booking and stored-price payment verification.
- Signed webhooks and durable retry records.
- Durable inbound processing, payment reconciliation, and fulfilment/SLA
  queues.
- Configurable email recipients; no hard-coded operational mailbox.
- Self-service support/privacy/status/preparation/feedback.
- Audited operator support, fulfilment, reconciliation, availability, outbox,
  and metrics APIs.
- Alembic releases and bounded maintenance/risk reporting.

Prerequisites before a production cutover:

- For the approved fresh first release, initialise a new managed PostgreSQL
  database at the expected Alembic revision, enable backups, and complete a
  restore test. Do not import old-bot users, bookings, or payments.
- Run and monitor outbox, reconciliation, reminder, and maintenance schedules;
  alert on queue age/dead jobs/provider errors/operational risk.
- Staff reconciliation/risk queues and keep reminder templates empty until
  opt-in and Meta approval are evidenced.
- Validate live Meta/Razorpay/Amazon SES configuration in staging, including
  email authentication and bounce/complaint/delivery monitoring.
- Staff consultation fulfilment and support with measurable SLAs.
- Publish approved privacy, terms, refund/cancellation, and AI notices.
- Rehearse payment mismatch, provider outage, data incident, and rollback
  procedures.

## Growth backlog

High-value next capabilities:

1. Automatic advocate matching, eligibility/conflict evidence, and user
   notification on top of existing operator fulfilment tracking.
2. User reschedule/cancellation plus controlled provider refund workflow.
3. Activate the implemented appointment reminders with approved templates,
   opt-in, localized QA, suppression, and frequency caps.
4. Individual operator RBAC/MFA and settlement/refund/chargeback reconciliation.
5. Source-backed legal content with counsel review.
6. Privacy export/deletion/legal holds beyond current bounded retention and
   versioned consent.
7. Cohort and funnel reporting with privacy thresholds.
8. CRM integration only after purpose and access controls are agreed.

Campaign messaging, subscriptions, referral incentives, and marketplace
features should follow—not precede—reliable fulfilment, support, and compliance.
