# Client and User Perspective

## User promise

NyaySetu should help a person understand the next lawful step, book a clearly
described consultation, and recover from payment or navigation problems
without needing technical knowledge.

It must not imply that an AI answer is legal representation, that a lawyer has
been assigned when none has, or that payment guarantees a particular legal
outcome.

## Primary users

### First-time legal help seeker

Needs plain language, category guidance, price transparency, and confidence
about what happens after payment.

### Low digital-confidence user

Benefits from WhatsApp buttons/lists, persistent home navigation, clear retry
prompts, saved profile details, and support.

### Urgent or distressed user

Needs a deterministic safety message and an appropriate local emergency/human
route. The chat cannot dispatch help and must not invent a hotline or delay the
user with a long intake.

### Returning or paid user

Needs appointment status, the current payment link where applicable,
preparation guidance, paid-session access, receipt recovery, and support
without being forced to restart.

## Implemented journey

1. The user messages the WhatsApp number.
2. The bot creates a case ID and offers English, Hinglish, or Marathi.
3. The initial choice offers Ask AI or Book consultation; the persistent home
   also offers More options.
4. AI explains the privacy boundary and asks for consent.
5. Booking explains the paid scope and fee before collecting or reusing
   profile details.
6. The user confirms district/state, category, and subcategory.
7. Available IST dates and slots reflect cutoff and capacity.
8. A final review shows the person, matter, location, date, time, and amount.
9. Pay now creates one pending booking and Razorpay link.
10. The waiting view offers link recovery, status, and payment help.
11. Only a verified Razorpay webhook plus exact current Payment Link/Payment
    evidence confirms the appointment.
12. The user receives a durable WhatsApp success message; configured operations
    recipients receive email.
13. The user can view preparation guidance and use paid AI until the slot ends.
14. The first interaction after the slot ends marks completion and triggers a
    private rating and optional comment.

## What the user can self-serve

- Redisplay home without losing booking progress.
- Check the latest appointment and pending payment link.
- Change language.
- Read built-in legal guides.
- Get a category-relevant preparation checklist.
- Read a short privacy notice and configured policy link.
- Submit a support ticket.
- Change date/time or cancel during the pre-payment review.
- Request a receipt again after a completed payment.

The user cannot currently reschedule or cancel a paid booking, request a refund
through the bot, select an advocate, or update a support ticket.

## Trust requirements

### Before payment

The user should see:

- What service is being booked.
- The exact fee.
- Their saved details.
- Appointment date and time.
- A way to change or cancel before payment.
- How to get payment support.

The implemented review provides these details before creating a link.

### After payment

Confirmation must be based on provider evidence, not a typed claim or
screenshot. The signed event is independently checked against the current
Payment Link and Payment, including ownership, stored amount, one full capture,
and no refund. A provider lookup failure must grant no entitlement, while
evidence that cannot be matched enters an operations reconciliation process.
An operator's terminal review decision cannot be undone by a delayed event.

The business still needs to publish:

- How and when the human consultation occurs.
- Reschedule, cancellation, no-show, and refund rules.
- Support response targets.
- Tax/receipt wording.

### AI and privacy

The current flow asks for AI consent and offers a privacy menu. High-risk
identifiers are scrubbed on a best-effort basis before third-party AI calls.
The product should continue to tell users not to share OTPs, passwords,
unnecessary IDs, or unrelated private documents.

AI and booking/payment grants are stored with policy versions. Consent
revocation/governance and automated export/deletion are not implemented.

## Language experience

Navigation and core flow copy exist in English, Hinglish, and Marathi. Built-in
legal guide source content is primarily English; non-English users receive a
language note. Before launch, native reviewers should test terminology,
truncation, tone, and safety across all three experiences.

## Remaining friction

- There is no in-product explanation of the actual call/chat channel for the
  human consultation.
- Operators can record advocate/named fulfilment assignment, but there is no
  automatic matching or user-facing assigned-professional/channel message.
- Paid changes are not user-self-service. Operators can capacity-check a paid
  reschedule and record a reviewed refund outcome, but provider refund execution
  and user-facing change notifications are not implemented.
- Support tickets have no user-visible SLA or status-update flow.
- Automatic receipts are disabled by default.
- Consultation reminders remain inactive while Meta-approved language/template
  pairs are empty.
- Five fixed daily slots may not reflect real staffing.
- Static local legal guides are not source-cited or personalized by
  jurisdiction.
- In-memory throttles may feel inconsistent after restart or horizontal scale.

## Client demo script

Use test credentials and isolated data:

1. Start with a new WhatsApp ID and select each language once.
2. Open and close AI consent; verify no AI is enabled on decline.
3. Ask a harmless legal question and a deterministic harmful/urgent test.
4. Open More options and inspect status, preparation, guide, privacy, and
   support.
5. Start booking and confirm the scope/fee appears first.
6. Enter an ambiguous district and choose a result.
7. Select category/subcategory, date, and slot.
8. Verify slot selection shows review but creates no provider link.
9. Change time, return to review, and select Pay now.
10. Complete one signed Razorpay test payment.
11. Verify one paid booking, one WhatsApp success job, configured email job, and
    no duplicate side effects on replay.
12. Use protected operations to assign/complete fulfilment and verify its audit
    trail.
13. Submit feedback only after completed fulfilment.

Never demonstrate production payment credentials or real user legal messages.

## Client acceptance checklist

- Fee and service wording are approved.
- Booking capacity matches staffing.
- Human fulfilment channel and SLA are documented.
- Payment, expiry, duplicate, refund, and support scenarios are approved.
- Native speakers approve all three language flows.
- Privacy, terms, AI consent, retention, and deletion policies are published.
- Meta/Razorpay/SendGrid test evidence is available.
- Fresh managed PostgreSQL setup/restore and payment reconciliation are
  rehearsed; no old-bot user or booking records are imported.
- Support staff can access tickets securely and know how to resolve them.
- Metrics measure successful outcomes rather than conversation length alone.

## Future user-experience priorities

1. Show the operator-recorded fulfilment channel and assigned professional
   after confirmation.
2. Add controlled reschedule/cancel/refund requests with audit history.
3. Activate the implemented 24-hour/2-hour reminder pipeline only after
   explicit opt-in, Meta template approval, localized QA, and suppression/
   frequency rules.
4. Give users support-ticket status and expected response time.
5. Add privacy export/deletion, consent revocation, and policy-governance
   controls around the versioned consent records.
6. Provide counsel-reviewed, source-backed multilingual legal guides.
7. Test accessibility with low-literacy and assistive-technology users.
