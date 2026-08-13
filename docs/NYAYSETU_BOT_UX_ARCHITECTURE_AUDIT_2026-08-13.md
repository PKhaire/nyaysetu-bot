# NyaySetu Bot UX and Architecture Audit

Date: 13 August 2026  
Audit baseline: public `PKhaire/nyaysetu-bot` `main` at commit `ed5f2de`  
Hardening release: RC7

## Executive decision

NyaySetu does **not** need a risky full rewrite before the controlled launch.
Its current architecture already has the important production foundations:
durable inbound-message deduplication, a database-backed conversation state,
PostgreSQL migrations, signed webhook validation, payment verification, an
outbox for asynchronous delivery, legal-content routing, multilingual content,
and health/readiness checks.

A focused conversation redesign **was required and has been implemented**.
The audit found user-visible dead ends and one WhatsApp list that could exceed
Meta's provider limit. RC7 fixes those problems while preserving the existing
payment, booking, legal-content, and database contracts.

## User journey reviewed

1. First contact and language selection
2. Legal-question consent and free guidance
3. Persistent Home and More Options navigation
4. Legal-guide category, issue, answer, and helpfulness feedback
5. Ask an Advocate website hand-off and support-ticket creation
6. Booking scope, name, location, category, subcategory, date, and time
7. Booking review, terms acceptance, Razorpay payment, and payment help
8. Appointment status and consultation-preparation checklist
9. Paid-session behaviour, receipt access, and post-consultation feedback
10. Restart, stale-button, invalid-input, and unsupported-media recovery

## Findings and RC7 changes

### 1. Silent response at the primary choice — fixed

At `ASK_AI_OR_BOOK`, only the two exact WhatsApp button identifiers were
accepted. A user typing “book consultation” or typing a legal question could
receive no response.

RC7 accepts a typed booking request, safely routes other typed questions to the
AI-consent step, and redisplays the choice after an invalid or stale button.

### 2. Property menu could exceed the WhatsApp row limit — fixed

The Property category already contained ten subcategories. The previous helper
then appended “General Legal Query”, creating eleven rows although WhatsApp
allows only ten. This could prevent the list from being delivered.

RC7 uses the existing “Not Sure” choice as the general route and guarantees
that every subcategory menu contains at most ten rows.

### 3. Invalid website advocate intake could disappear — fixed

A prepared Ask an Advocate message was safely stored only when it exactly
matched the approved contract. That strict validation is correct, but an edited
or stale prepared message was silently ignored.

RC7 keeps strict validation and does not store malformed legal intake. It now
explains the problem and returns the user to a safe navigation path.

### 4. Stale date and time selections created dead ends — fixed

Some invalid date/slot actions displayed an error without redisplaying the
available choices. RC7 always restores the relevant picker and safely returns
to date selection when the temporary date is missing.

### 5. Generic unknown input had no visible recovery — fixed

The final webhook fallback acknowledged the provider but sent nothing to the
user. RC7 sends a concise recovery explanation and the Home menu. Delivery and
read-status callbacks remain silently acknowledged because they are not user
messages.

### 6. Language consistency — improved

The list action button was always “Select” and feedback rating titles were
always English. RC7 supplies English, Hindi/Hinglish, and Marathi list actions
and rating labels through the central translation system.

### 7. Restart required an unnecessary extra message — fixed

Restart previously told the user to type “Hi” again. RC7 confirms the reset and
immediately presents Home. Paid and payment-pending safeguards remain intact.

### 8. Corrupt paid-booking data could fail silently — fixed

If a paid booking lacked a valid date or slot window, the bot logged the issue
but gave no user response. RC7 provides a safe support-oriented explanation,
does not create a new payment, and returns Home.

## Architecture recommendation

### Launch architecture

Keep the current single-worker Flask deployment for the controlled launch. It
matches the present process-local rate limits and user locks and avoids a large
last-minute behavioural rewrite.

### Refactor after launch, based on measured growth

When traffic requires more than one web worker or multiple Render instances:

- move user locks, throttling, and short-lived deduplication to Redis or another
  shared coordination service;
- extract the large webhook state machine into a conversation orchestrator
  with one handler per state;
- run the durable outbox and scheduled maintenance as independently monitored
  workers;
- add funnel dashboards for language selection, guide completion, booking
  review, payment completion, support response time, and user abandonment;
- version the website-to-WhatsApp advocate-intake contract so website and bot
  releases can be upgraded independently.

These are scale and maintainability improvements, not blockers for the current
controlled launch.

## Verification performed

- Full automated suite: **289 passed**
- Focused UX, WhatsApp transport, and translation suite: **34 passed**
- Ruff static analysis: passed
- Python compilation: passed
- Tests cover malformed advocate intake, typed primary choices, visible
  fallback recovery, list row limits, and localized list action titles.

## Release boundaries

RC7 contains no database migration and does not change Razorpay signatures,
payment amounts, webhook URLs, booking records, or advocate-review content.
It changes conversation routing and presentation only.

## Controlled-launch checklist

- Deploy RC7 while the service is in application maintenance mode.
- Confirm migrations complete and `/health/live` and `/health/ready` return 200.
- Test English, Hindi/Hinglish, and Marathi journeys on real WhatsApp.
- Test one structured Ask an Advocate request and verify its ticket/notification.
- Complete one Razorpay **test-mode** booking and verify webhook idempotency.
- Confirm restart, stale date, stale slot, unknown text, Support, and Menu.
- Keep public payments disabled until Razorpay ReKYC and the live-payment launch
  decision are complete.
- Keep unverified-recipient email expectations disabled while SES remains in
  sandbox, or approve and configure the selected production email provider.
- Record the deployed Git commit and retain the previous known-good Render
  deployment for rollback.

## Final verdict

The bot is ready for the next controlled testing cycle after RC7 is uploaded
and deployed. A full UI or backend rewrite is not recommended before that test
cycle. Public production launch remains a separate go/no-go decision based on
provider readiness, real-device smoke tests, and business/legal sign-off.
