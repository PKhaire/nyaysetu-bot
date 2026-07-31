# Functional Specification

## Product purpose

NyaySetu is a WhatsApp-first legal-information and consultation-booking
assistant for users in India. It helps a user understand a common legal topic,
prepare a matter summary, choose a consultation slot, pay through Razorpay, and
track the resulting appointment.

The AI and built-in guides provide general legal information, not
representation, an advocate assignment, an emergency response, or a guarantee
of outcome.

## Implemented user capabilities

- English, Hinglish, and Marathi onboarding and navigation.
- Persistent home menu without destroying an in-progress booking.
- Versioned-consent-gated free legal-information AI, limited to five questions.
- A two-level local legal-guide tree covering nine areas and their
  category-specific issues.
- English, conversational Hindi/Hinglish, and Marathi guided questions,
  immediate actions, document checklists, urgency cues, disclaimers, and
  content-review metadata.
- Helpful/not-helpful guide feedback with guide, support, and consultation
  handoffs.
- Name, district/state, category, and subcategory intake.
- District ambiguity resolution through a WhatsApp list.
- IST-aware, capacity-filtered consultation dates and five daily time slots.
- Transparent service/fee introduction and full review before payment-link
  creation.
- Razorpay payment waiting, appointment status, payment help, and signed
  webhook confirmation.
- Time-bound paid AI access through the end of the booked slot.
- Appointment preparation checklist tailored to the legal category.
- Privacy notice and configurable support contacts.
- Persisted support tickets with optional durable email notification.
- Persisted post-consultation rating and optional comment.
- Manual receipt resend; optional automatic PDF receipt delivery.
- Optional deduplicated 24-hour/2-hour consultation reminders, disabled until
  exact Meta-approved language/template pairs are configured.

## Main navigation

Immediately after language selection, the bot offers Ask AI or Book a
consultation. The persistent home menu, available through `home`, `menu`, or
`help`, presents:

- Ask AI.
- Book a consultation.
- More options.

More options contains appointment status, consultation preparation, legal
guides, support, privacy/data information, and language change. Legal Guides
first asks for a legal area and then the closest category-specific issue. A
guide never predicts an outcome or supplies an unreviewed deadline. It ends
with a helpful/not-helpful control and a direct consultation option.

Sending a home/menu/help greeting after onboarding redisplays navigation
without clearing the current flow. A pending payment remains protected: the
bot shows payment/status/support options instead of silently starting a second
booking.

## AI flow

1. The user selects Ask AI.
2. The bot explains the AI/privacy boundary and asks for consent.
3. Declining returns to home without enabling AI.
4. Accepting enables the appropriate free or paid context.
5. Deterministic urgent-risk and harmful-request checks run before any model.
6. The router uses the configured Claude/OpenAI/local order and falls back to
   the same versioned multilingual content used by Legal Guides.
7. Free access stops after five questions and offers booking.
8. Paid access is available only through the booked consultation slot end.

Common high-risk identifiers are scrubbed before external providers, but users
must still be told not to send unnecessary sensitive data. The feedback flow
opens only after an operator records the linked fulfilment as `COMPLETED`; the
passage of the booked window alone does not prove delivery.

## Booking flow

### Scope and fee

The bot first explains that the flow books a paid consultation and displays the
configured fee. The user may continue or return home. No booking or payment link
exists at this point.

### User details

For a new profile the bot collects:

1. A person name, rejecting numbers, disallowed symbols, and common company
   suffixes.
2. District text.
3. A confirmed district/state match; ambiguous results are selectable.
4. Legal category.
5. Category-specific subcategory.

For a returning profile, the bot displays saved details and allows the user to
confirm or restart detail collection.

### Availability

The date list covers up to seven selectable days inside the configured booking
horizon. Today appears only when at least one slot is beyond the configured
cutoff and capacity remains.

The implemented slot labels are:

- 10:00 AM–11:00 AM
- 12:00 PM–1:00 PM
- 3:00 PM–4:00 PM
- 6:00 PM–7:00 PM
- 8:00 PM–9:00 PM

Paid bookings and non-expired pending bookings consume per-day and per-slot
capacity. Capacity is rechecked under a database lock when payment-link
creation begins.

### Review and payment

After slot selection, the bot displays name, matter, location, date, slot, and
fee. The user can:

- Pay now.
- Change date/time.
- Cancel before payment.

Only Pay now creates a pending booking and Razorpay link. The link has a
configurable lifetime of at least 16 minutes. The waiting state shows status,
support, and the current link. An expired pending booking releases capacity and
returns the user to availability.

### Confirmation

User text saying that payment was made does not confirm a booking. Confirmation
starts with a valid signed Razorpay event, but the event snapshot alone is not
enough. Before entitlement, the application independently reads the current
Razorpay Payment Link and Payment resources and requires all of the following:

- The signed event and current provider state represent a captured INR payment
  and paid payment link.
- The link ID, booking reference/ID/token notes, and payment ID identify the
  stored booking exactly.
- The stored amount matches the link amount, amount paid, single full capture,
  and current Payment amount.
- The current Payment says `captured=true` and has zero/no refund state.
- Has not already completed under the same payment ID.

Successful processing changes the booking to `PAID`, clears the user's active
link, creates a fulfilment work item, and commits durable
WhatsApp/email/optional-receipt work. An unmatched captured payment is retained
for review while the endpoint requests provider retry. Provider lookup failure
also returns `503` without entitlement. Invalid current state, amount/currency
change, or a conflicting payment is retained for review and acknowledged with
`202` without paying the booking. A prior terminal operator disposition remains
authoritative over delayed delivery. The independent reconciliation command can
recover a missed capture only from the same exact authenticated-provider
evidence.

## Self-service and engagement

### Appointment status

The bot shows the latest booking ID, status, date, time, category, and amount.
For a pending booking it also resends the active link when available.

### Consultation preparation

The checklist combines a category-specific evidence/document suggestion with a
timeline, correspondence, parties, desired outcome, top questions, and advice
to retain original documents safely.

### Legal guides

Seven built-in topics are available from the local knowledge set. Each carries
a general-information disclaimer. Non-English users receive a language note
where the underlying guide remains English.

### Support

The user can submit a 5–2,000 character support message. The system stores a
ticket with an `NSH-######` display ID and, when notification recipients are
configured, queues an email. Authenticated operators can assign, prioritize,
progress, resolve, or close a ticket through the admin API. Closing requires a
resolution note; every mutation records an operator audit event.

### Feedback

At the end of a paid consultation window, the bot records a one-to-five rating
and an optional comment of up to 1,000 characters. It does not publish feedback
or use it for automated legal decisions.

### Privacy

The menu shows a short localized notice and includes `PRIVACY_POLICY_URL` when
configured. Support and privacy contact values have empty defaults so
unverified details are not published.

## Maintenance behavior

When `MAINTENANCE_MODE=true`, ordinary text and interactive messages receive a
generic maintenance response. An explicitly configured WhatsApp ID can bypass
maintenance for testing. The response does not publish a hard-coded emergency
number.

The separate maintenance command applies bounded retention and operational
risk reporting:

```text
python -m jobs.maintenance --dry-run --batch-size 500 --fail-on-risk
```

It preserves financial, fulfilment, support, user, feedback, failed, and legacy
evidence. Exit `2` with `--fail-on-risk` means the run succeeded but overdue
fulfilment/support or stale reconciliation work needs operator attention.

## Operations capabilities

Implemented:

- Liveness/readiness routes.
- Token-protected aggregate metrics.
- Token-protected, audited support, fulfilment, payment-review, outbox,
  availability, and audit operations.
- Capacity-checked paid rescheduling and an audited
  `REFUND_REVIEW`-to-`REFUNDED` recording path. The terminal refund record
  cancels the service entitlement, preserves payment evidence, and creates or
  terminalizes exact reconciliation truth; it does not execute a provider
  refund.
- Durable outbox with retry/backoff and dead-letter status.
- Durable lease-aware inbound-message inbox.
- Alembic schema releases and expected-revision readiness.
- Exact-evidence payment-link reconciliation:
  `python -m jobs.reconcile_payments --limit 100`.
- Template-gated reminder scheduling: `python -m jobs.consultation_reminders`.
- Bounded retention and operational-risk maintenance.
- Category and privacy-minimised product analytics events.
- Compatibility daily-appointment email command.

The compatibility `python -m jobs.daily_appointments_email` command is not
scheduled in the supplied Render definition. The Blueprint schedules outbox
processing, five-minute payment reconciliation, ten-minute template-gated
reminder scheduling, and daily maintenance/risk reporting.

## Error and retry behavior

- Invalid WhatsApp signatures are rejected before a message claim.
- Ordinary WhatsApp handler/database failure marks its durable claim `FAILED`
  and returns `503`; failed/expired leases can be reclaimed.
- After user-flow state changes, a text/button/list failure known safe to retry
  atomically marks the inbound event `DONE` and creates one deduplicated
  conversation-delivery outbox job. Meta replay cannot rerun the state change.
- Ambiguous transport delivery, where Meta may have accepted the message, is
  marked `DONE` without automatic resend. Terminal conversational outbox
  payloads retain only a minimal delivery marker.
- Multi-message Meta deliveries are drained one item at a time by deliberate
  provider retry.
- Per-user and global request limits run before menu, support, media,
  paid-session, and other user-flow branches; a limited user receives at most
  one rate-limit notice per applicable window.
- Failed Razorpay processing or current-resource lookup returns `503` and
  records a failure marker when possible; no entitlement is granted.
- Provider notification failures that are safe to resend remain in the outbox
  for bounded retry.
- A failed payment-link creation rolls back the booking and best-effort cancels
  the provider link.
- User-facing list/state errors redisplay a valid choice instead of silently
  stranding the user.

## Explicitly not implemented

- Automatic advocate selection/user notification or a live lawyer chat/call
  connection. Operators can assign an active advocate or named fulfiller.
- User self-service reschedule, post-payment cancellation, or Razorpay refund
  execution. Operators can capacity-check a paid reschedule and record a
  reviewed refund outcome; direct paid cancellation is not an allowed shortcut.
- Marketing/re-engagement campaigns. The implemented transactional
  consultation reminders remain disabled until exact Meta-approved templates,
  opt-in, localization, and suppression policy are configured.
- Full Razorpay settlement/chargeback import or refund execution.
- Automated data export/deletion/legal-hold handling. Bounded retention exists
  only for explicitly approved terminal operational categories.
- Source-cited legal retrieval or jurisdiction-specific case-law research.
- Distributed rate limiting across multiple web processes.

## Rollout acceptance criteria

The code is ready for production launch only after staging acceptance and the
production provisioning gates below are complete:

- An isolated, empty managed PostgreSQL staging database is upgraded to the
  current Alembic revision, passes `current`, `check`, and readiness, and
  contains only synthetic/test data.
- Production uses a different, empty managed PostgreSQL database. The current
  Alembic revision and backup/restore procedure are verified before traffic,
  and no staging, test, or legacy rows are present.
- No legacy SQLite users, bookings, or payments are imported or reconciled for
  this release. The SQLite-to-PostgreSQL utility is a non-current contingency
  that requires a separately approved migration plan if the launch decision
  changes.
- Meta and Razorpay signatures, duplicates, delayed events, batch delivery, and
  injected failure retries behave as specified.
- A payment confirms only its intended booking when the current Payment Link
  and Payment resources agree on exact ownership, stored amount, one captured
  payment, and zero refund state.
- Provider lookup failure grants no entitlement; current-state mismatch enters
  review; a delayed event cannot reopen a terminal manual disposition.
- Direct paid cancellation is rejected, while the reviewed refund transition
  preserves payment evidence and revokes access only when no other paid booking
  remains.
- The outbox cron drains WhatsApp/email jobs and alerts on failures/dead jobs.
- Maintenance dry-run/risk reporting and the payment-reconciliation command
  are exercised with audited operator follow-up.
- Reminder scheduling is a no-op with empty templates; any enabled 24-hour/2-hour
  pair has Meta approval, opt-in, localized rendering, deduplication, and
  reschedule/refund suppression evidence.
- Support, privacy, terms, refund/cancellation, consultation fulfilment, and
  retention policies are approved and configured.
- Every enabled AI provider has privacy/legal approval and multilingual safety
  evaluation.
- Amazon SES identity/domain, email-authentication records, production access,
  monitored configuration set, recipients, and any Meta templates are approved.

Passing unit tests alone does not satisfy these external acceptance criteria.
