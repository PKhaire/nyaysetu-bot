# Functional Specification

## Product purpose

NyaySetu is a WhatsApp-first legal-information and consultation-booking
and governed self-service document assistant for users in India. It helps a
user understand a common legal topic, prepare a matter summary, choose a
consultation slot, pay through Razorpay, track the resulting appointment, and
prepare an eligible legal draft from a reviewed deterministic template.

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
- Structured case-brief intake before slot selection: issue summary, current
  legal stage, important dates, desired outcome, urgency/safety cue,
  document-availability checklist, and optional opposing-party name.
- A separate, short WhatsApp confirmation records versioned consent before
  the brief can be attached to a paid booking. The product accepts no document
  uploads in this release.
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
- A globally visible Document Studio entry when the product-level switch is
  enabled; there is no tester phone list, cohort, or percentage sampling.
- A privacy-minimised eligibility screen and 43-question English questionnaire
  for the Maharashtra 11-month residential leave-and-licence self-service
  draft. Ineligible or out-of-scope matters are routed out before payment.
- Immutable answer revisions, an exact advocate-approved release gate,
  watermarked preview PDF, exact Razorpay payment verification, and private
  time-limited PDF/DOCX delivery.

## Main navigation

Immediately after language selection, the bot presents the persistent home
menu, also available through `home`, `menu`, or `help`:

- Ask Legal Question.
- Book a consultation.
- Document Studio, when the global product switch is enabled.
- More options.

More options contains appointment status, consultation preparation, legal
guides, support, privacy/data information, and language change. Legal Guides
first asks for a legal area and then the closest category-specific issue. A
guide never predicts an outcome or supplies an unreviewed deadline. It ends
with a helpful/not-helpful control and a direct consultation option. Every
guide warns users not to send account secrets, complete identity numbers, or
full bank details in chat.

Sending a home/menu/help greeting after onboarding redisplays navigation
without clearing the current flow. A pending payment remains protected: the
bot shows payment/status/support options instead of silently starting a second
booking.

WhatsApp permits at most three reply buttons. NyaySetu therefore renders the
four top-level choices as a list rather than hiding Document Studio behind a
tester-only route. Disabling the single product switch removes Document Studio
for everyone; enabling it makes the same catalogue visible to every user. A
separate release gate still blocks preview/payment if the exact deployed
template package lacks a current authenticated advocate approval.

## Document Studio flow

The first governed product is
`mh_residential_leave_licence_11m_self_service`: an English self-service draft
for a Maharashtra residential leave-and-licence arrangement of up to 11
months, between one adult individual licensor and one adult individual
licensee, both acting for themselves, for completed residential premises.

1. The user opens Document Studio, sees the scope, price, retention notice and
   safety boundary, and chooses to create or resume a draft. A new draft
   atomically reserves one of the globally shared India-business-day slots;
   resuming the same draft does not consume another slot. When capacity is
   full, no order or payment is created and the user is asked to try tomorrow.
2. Eligibility questions run before detailed intake. A company/firm party,
   representative/POA arrangement, multiple party, minor, non-residential or
   under-construction premises, non-Maharashtra property, disputed title,
   security/loan arrangement, or other excluded condition routes the user to
   support/consultation without creating a payment entitlement and releases an
   unconsumed slot. Explicit cancellation and retention expiry do the same.
3. The eligible user completes the bounded 43-question questionnaire. Answers
   are validated against the catalogue schema and saved as immutable numbered
   revisions; the working draft can be resumed for seven days.
4. The review message presents material terms and versioned consent. NyaySetu
   does not request Aadhaar/PAN numbers, bank credentials, identity documents,
   signatures, evidence files, or scans in this flow.
5. Confirming answers first checks the exact release package. Monetisation is
   denied unless the latest append-only decision for the deployed aggregate
   hash is `APPROVED`, unrevoked, within its review window, and matches the
   deterministic golden PDF and DOCX hashes.
   Confirmation also consumes the reservation; later payment failure does not
   erase drafting work already counted against that day's limit.
6. An approved release produces a watermarked preview PDF in private object
   storage, then creates a Razorpay link for the price snapshotted on the
   order. A user message claiming payment is never accepted as proof.
7. The signed payment event is followed by authenticated current Payment Link
   and Payment reads. Exact identity, notes, amount, INR currency, one full
   capture, payment ID, and zero-refund state must all match the order.
8. Exact payment renders immutable final PDF and DOCX artifacts. Only
   short-lived presigned download URLs are sent to the owning WhatsApp user.
   Final artifacts expire after 30 days; every permitted or denied access and
   retention deletion is audited without logging document contents.

The generated files are an automated self-service draft, not advocate-signed
work and not a substitute for registration, stamping, witnessing, legal
advice, or a title/identity check. The exact scope and questionnaire contract
are maintained under `docs/document-studio/`.

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

### Structured case brief and consent

After category/subcategory selection, the bot collects a privacy-minimised
brief. It tells the user not to send Aadhaar/PAN numbers, passwords, banking
details, or document images. The document step records only whether common
document types are available; it does not accept or store files.

The complete factual review is sent as an ordinary WhatsApp message. A second,
bounded interactive message states the assigned-registered-advocate sharing
purpose, consent version, and privacy URL. **Confirm brief** records both the
brief consent fields and the `ADVOCATE_CASE_BRIEF_SHARING` user-consent row;
**Edit brief** starts a fresh draft and **Cancel** prevents assignment. Only a
confirmed brief can be linked to the booking created for the payment link.

Immediate-safety selection displays an emergency limitation and captures a
short operational note; NyaySetu does not present itself as an emergency
service.

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

## Appointment control desk

An authenticated browser console at `/admin/appointments` presents the
SLA-ordered paid-consultation fulfilment queue. Operators can search and filter
records and review the client's consented structured case brief without opening
separate files. Ordinary queue responses expose only masked contact details.
A stable operator ID and a stated operational purpose are required to reveal a
client or advocate number; every reveal is written to the admin audit trail.

Operators register and select only active, verified advocates, assign the paid
matter, and manually contact the advocate and client. Each contact attempt is
recorded with party, channel, outcome, notes, and an optional follow-up time.
This release therefore does not depend on approval of outbound Meta WhatsApp
templates. Operators can then confirm arrangements, record a capacity-checked
reschedule, or record an allowed exception/final outcome. Completion is always
an explicit audited operator action with notes; elapsed time alone never
completes an appointment. The existing token-authenticated API remains
available for approved automation.

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
- Governed Document Studio catalogue, questionnaire, release-approval ledger,
  deterministic PDF/DOCX rendering, private object storage, exact payment
  confirmation, download audit, and retention deletion.
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
- Advocate signature/e-signing, identity/KYC verification, evidence uploads,
  registration/stamp-duty execution, multi-party/POA/company document flows,
  and documents outside the one approved RC9 catalogue item.

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
- Document Studio remains disabled until the exact RC9 hashes have a current
  authenticated licensed-Maharashtra-advocate approval, a non-zero reviewed
  price, a private S3 bucket with least-privilege credentials and lifecycle
  controls, and tested preview/payment/final-download/expiry evidence.

Passing unit tests alone does not satisfy these external acceptance criteria.
