# NyaySetu Master Product, Technology, Launch and Growth Blueprint

**Document status:** Working master for partner, product, legal, engineering,
operations and marketing review  
**Prepared on:** 30 July 2026  
**Current candidate:** `legal-content-2026-07-r4`  
**Release approach:** Fresh first production release; no legacy-user or
legacy-database migration  
**Launch budget under discussion:** INR 25,000  
**Next formal review:** Conversation and product review

---

## 1. Purpose of this document

This is the single consolidated reference for NyaySetu. It records:

- what NyaySetu is and is not;
- decisions already made during product and deployment discussions;
- the present state of the source code and release candidate;
- the intended user experience and operating model;
- the technical, privacy, security and legal controls;
- the work still required before staging and production;
- the product, content, AI and engineering roadmap;
- the marketing, partnership and responsible-growth strategy;
- budgets, metrics, risks, ownership and launch checklists.

This document is a management and delivery blueprint. It is not legal advice,
a penetration-test report, an infrastructure invoice, a provider approval or
proof that the release is live. Executable source code, automated tests,
provider dashboards and production evidence remain authoritative for their
respective subjects.

### 1.1 Status language used throughout

To prevent misunderstandings, every important item should use one of these
labels:

| Status | Meaning |
|---|---|
| **Built** | The capability exists in the current source repository. |
| **Locally validated** | Static or standalone checks passed in the available development environment. |
| **CI validated** | The exact commit passed the complete GitHub Actions workflow. |
| **Staging verified** | The capability passed with isolated Meta, Razorpay, SendGrid and PostgreSQL resources. |
| **Approved** | The responsible business, legal, privacy, language or security owner signed off. |
| **Live** | The exact approved version is deployed and monitored in production. |
| **Future** | The capability is proposed but not implemented. |

“Built” must never be presented to partners or users as “Live.”

---

## 2. Executive summary

NyaySetu is a WhatsApp-first platform that helps people:

1. understand the general nature of a legal problem;
2. organise basic facts and documents;
3. recognise when urgent human help may be needed;
4. book and pay for a clearly described lawyer consultation;
5. recover appointment, payment, preparation and support information.

Its strongest positioning is not “AI lawyer” or “longer conversations.” It is:

> **A clear, trustworthy next step for people who do not know where to begin
> with a legal problem.**

The product currently contains a substantial reliability, payment, privacy,
booking and operations foundation. The newest refinement adds a deterministic,
versioned legal-information system with English, conversational Hindi/Hinglish
and Marathi guidance, a two-level legal-guide menu, urgent-situation overlays,
document checklists, next actions, feedback and lawyer-booking handoff.

The correct launch strategy is a controlled fresh release:

- no migration of old bot users or old database records;
- a new managed PostgreSQL database;
- no local installation for end users;
- no mandatory paid generative-AI API;
- paid, reliable cloud infrastructure for production;
- counsel-reviewed and native-language-reviewed content;
- isolated staging before any real customer traffic;
- a capped pilot before marketing at scale.

The current `r4` release candidate is **not yet production-approved or live**.
It must be committed/uploaded, pass CI, pass conversation/product review,
receive legal/language approval, pass staging provider tests and complete a
fresh-production rehearsal.

---

## 3. Product vision, mission and principles

### 3.1 Vision

Make the first step toward lawful help understandable and accessible to people
using a familiar communication channel.

### 3.2 Mission

Provide multilingual, privacy-conscious legal information and a reliable path
to a human consultation without misleading users about AI, lawyers, outcomes,
urgency, payment or privacy.

### 3.3 Product principles

1. **Clarity before cleverness:** Plain language and buttons are more valuable
   than impressive but uncertain AI prose.
2. **Trust before engagement:** Optimise for successful next actions, not time
   spent chatting.
3. **Human review for high stakes:** Legal content, urgent guidance and
   operational policies require qualified review.
4. **Minimum necessary data:** Do not request or retain a private legal
   narrative when structured choices are enough.
5. **Payment integrity:** A user message or screenshot can never mark a
   booking paid.
6. **No silent failure:** Failed messages, payments and fulfilment tasks must
   be visible and recoverable.
7. **Multilingual equivalence:** Translated experiences should preserve
   meaning and safety, not merely translate words.
8. **Fresh-release discipline:** Start with clean infrastructure and controlled
   traffic instead of importing unknown legacy risk.
9. **Evidence-led growth:** Expand only after fulfilment, support, payment and
   user-outcome metrics are stable.
10. **No “forever ready” claim:** Production readiness must be continuously
    maintained through monitoring, review, updates and rehearsals.

---

## 4. Decisions already made

| Decision | Current position | Reason |
|---|---|---|
| First release | Fresh production release | No need to preserve outdated bot users or data. |
| End-user setup | No local installation | Users interact through WhatsApp. |
| Operator/deployment setup | Cloud configuration is required | Credentials and providers cannot operate without secure environment configuration. |
| Production database | Managed PostgreSQL | Booking capacity, payment idempotency, support, audit and durable delivery require shared state. |
| Old database backup | Not required for the fresh release | No legacy data will be migrated. |
| New database backup | Required from launch day | Fresh data still becomes operational and financial evidence. |
| Generative AI | Optional | Core FAQ/legal-guide experience works deterministically without a paid model API. |
| Local FAQ cost | No model-token/API cost | The content is code-based and versioned; hosting and review still have costs. |
| Home SSD/Wi-Fi/spare phone | Not primary production infrastructure | Useful for testing, encrypted offline export and alerts, but not reliable hosting. |
| Initial launch allocation | INR 25,000 target | Supports a careful pilot if scope and vendor choices remain controlled. |
| Immediate priority | User experience and content quality | Infrastructure spending should follow product acceptance. |
| Deployment style | Staging, then controlled pilot | Reduces payment, legal, language and fulfilment risk. |
| Marketing objective | Useful resolution and trust | Conversation length is not a success metric. |

### 4.1 Decisions still requiring partner approval

- Exact consultation price and taxes/receipt wording.
- Consultation duration, channel and service scope.
- Advocate onboarding, qualification and conflict-check process.
- Operating hours, daily capacity and holiday rules.
- Support and fulfilment response targets.
- Paid reschedule, cancellation, refund, no-show and dispute policies.
- Privacy-retention schedule and data-rights procedure.
- Whether any third-party generative AI will be enabled later.
- Marketing geography and first target customer segment.
- Final distribution of the INR 25,000 launch budget.

---

## 5. Current status as of 30 July 2026

### 5.1 Release status

| Area | Status | Evidence or remaining action |
|---|---|---|
| Reliability/payment modernization | **Built** | Present in repository and documented tests. |
| Earlier GitHub CI run | **CI validated for an earlier commit** | The screenshot showed all three jobs green; it does not cover later `r4` changes. |
| Legal knowledge `r4` | **Built and locally validated** | Compile, static diff and standalone contract checks passed. |
| `r4` full automated suite | **Not yet CI validated** | Push/upload the exact candidate and rerun GitHub Actions. |
| Legal-language content | **Not approved** | Qualified legal and native-language review required. |
| Provider integration | **Built, not staging verified for `r4`** | Run signed Meta/Razorpay/SendGrid scenarios. |
| Production infrastructure | **Not approved/live** | Create fresh managed resources and configure secrets. |
| Production deployment | **No-go today** | Product, legal, CI, staging and operating gates remain. |

### 5.2 Refined release artifact

The deployment archive must be built only after the source and documentation
are frozen. Record its filename, byte size, entry count and SHA-256 alongside
the release approval; do not embed an archive's own checksum inside that
archive. Every later source or documentation change requires a new candidate
archive and checksum.

Generated print editions of this blueprint are retained outside the runtime
archive. The Markdown source remains part of the reviewed release.

### 5.3 New user-facing content in `r4`

- Nine legal areas and 58 issue choices, including `Not Sure`.
- English, conversational Hindi/Hinglish and Marathi experiences.
- Guided questions for organising the matter.
- “What to do now” action steps.
- Document-preparation checklists.
- Urgent-risk escalation.
- State/district consultation-routing explanation.
- Clear general-information disclaimer.
- Content version and legal-review status.
- Helpful/not-helpful feedback.
- Lawyer-consultation handoff.
- Specific safety overlays for high-risk situations.
- Multilingual free-text aliases for common issues.
- Compatibility with seven older legal-guide button IDs.

Standalone checks covered 174 language/issue combinations. The longest guide
was 1,626 characters, below WhatsApp's 4,096-character text contract. List and
button identifiers, row counts, title lengths and feedback round-trips were
also checked.

### 5.4 Important limitations

- The current Hindi experience is conversational Hindi/Hinglish, not complete
  native-script Hindi throughout the whole product.
- The platform does not automatically select an advocate.
- It does not itself conduct a call or live consultation.
- It does not execute Razorpay refunds.
- Paid rescheduling/cancellation is not self-service.
- The shared admin token is not individual RBAC/MFA.
- Full privacy export, deletion, correction and legal-hold workflows are future
  work.
- Reminder infrastructure exists but must remain disabled until opt-in,
  template approval and language testing are complete.
- Static legal information can become stale and requires versioned review.
- One web worker is intentionally enforced; horizontal scaling needs shared
  throttles and load/concurrency evidence first.

---

## 6. Target users and jobs to be done

### 6.1 Primary user groups

1. **First-time legal-help seeker**  
   Does not know the category, documents, cost or next step.

2. **Low digital-confidence user**  
   Needs simple WhatsApp buttons, clear retry prompts and no installation.

3. **Urgent or distressed user**  
   Needs short safety-first direction and a human route, not a long intake.

4. **Employee or consumer with a common dispute**  
   Wants an understandable checklist before deciding whether to book.

5. **Small business owner**  
   Needs to organise a notice, cheque, recovery or contract problem.

6. **Returning or paid user**  
   Wants payment status, appointment details, preparation, receipt or support.

### 6.2 Core jobs

- “Help me identify what kind of issue this may be.”
- “Tell me what information and documents to organise.”
- “Tell me whether I should act urgently.”
- “Let me book a consultation without hidden steps.”
- “Confirm my payment only when it is actually verified.”
- “Help me recover my appointment or payment link.”
- “Give me a human support route when automation is insufficient.”

---

## 7. User experience and conversation design

### 7.1 Primary entry

```text
User sends Hi
  -> language selection
  -> home menu
     -> Legal Guides
     -> Ask informational question
     -> Book consultation
     -> More options
```

The first screen should make the product boundary clear without overwhelming
the user. The user should be able to proceed without knowing legal terms.

### 7.2 Legal Guides flow

```text
Legal Guides
  -> choose one of nine legal areas
  -> choose closest issue or Not Sure
  -> receive:
       issue focus
       organising questions
       next actions
       document checklist
       urgent warning
       location context
       disclaimer and review metadata
  -> mark helpful / need more help
  -> reopen guides / support / book lawyer
```

This flow intentionally uses structured selection before free text. It reduces
privacy risk, routing uncertainty and the need for a paid AI model.

### 7.3 Booking and payment flow

```text
Book consultation
  -> show service scope and price
  -> collect/reuse name
  -> state and district
  -> category and subcategory
  -> available date and slot
  -> final review
  -> explicit Pay now
  -> create one pending booking and Razorpay link
  -> verify signed provider event plus current provider evidence
  -> mark paid
  -> create fulfilment and notification work
  -> show status/preparation/support
```

No payment link should be created before final review. No typed confirmation,
receipt image or screenshot should mark the booking paid.

### 7.4 Self-service

The user can currently:

- reopen home without erasing booking progress;
- check appointment and pending-payment status;
- recover a current payment link;
- change language;
- view guides and preparation;
- submit support;
- view privacy information;
- provide post-consultation feedback;
- request a receipt when applicable.

### 7.5 Conversation acceptance rules

Every critical journey must satisfy:

- no dead end or unexplained loop;
- no false promise of outcome, representation or availability;
- urgent wording is short and safety-first;
- all buttons fit provider limits;
- `Not Sure` is available;
- the user understands what happens next;
- the user can reach support or return home;
- no unnecessary private narrative or identifier is requested;
- payment state is unambiguous;
- safety and privacy receive a 5/5 review score;
- clarity, relevance, ease, actionability, trust and language quality score at
  least 4/5.

---

## 8. Conversation and product review procedure

### 8.1 Review team

- facilitator;
- first-time-user tester;
- observer/note-taker;
- product owner;
- Hindi/Hinglish reviewer;
- Marathi reviewer;
- qualified legal reviewer for the separate content gate.

The user tester should receive only a persona and starting message. The
facilitator must not tell them what to click.

### 8.2 Review record

Record:

- test ID and language;
- persona and starting message;
- expected and actual route;
- messages/taps and completion result;
- hesitation, rereading, backtracking and confusion;
- exact risky or unclear wording;
- user understanding of what happens next;
- scores for clarity, relevance, ease, actionability, trust, safety, language
  and privacy;
- severity, owner, correction and retest result.

Use invented scenarios only. Do not use real client names, phone numbers,
documents, credentials or private legal facts.

### 8.3 Minimum scenario set

Test in all three languages where practical:

- greeting and language change;
- unknown category and `Not Sure`;
- spelling mistakes and mixed language;
- unsupported media;
- domestic violence;
- divorce and child custody;
- police notice, arrest and bail;
- cybercrime and unauthorised transaction;
- road accident and hit-and-run;
- property possession and builder delay;
- cheque bounce and money recovery;
- unpaid salary and workplace harassment;
- consumer refund;
- account freeze;
- legal notice and document review;
- complete booking;
- payment success, failure, delay and retry;
- duplicate tap/webhook from a user perspective;
- support, appointment status and returning user.

### 8.4 Severity

| Severity | Examples | Release consequence |
|---|---|---|
| Critical | Unsafe guidance, false payment, exposed secret/private data, missing consent, paid user stranded | Block release |
| High | Wrong routing, broken booking, misleading availability, inaccessible support, dangerous language error | Fix before launch |
| Medium | Excess text, confusing label, unnecessary steps, repetition | Fix before pilot where practical |
| Low | Minor tone, spacing or emoji preference | Batch as polish |

### 8.5 Review cycle

```text
Test -> record -> classify -> approve wording -> implement -> retest -> sign off
```

Do not edit wording live during review. First consolidate duplicates and
resolve conflicting feedback. Any change to approved legal content requires a
new content version and review.

---

## 9. Legal-information content governance

### 9.1 Content ownership

Assign:

- one product content owner;
- one qualified legal reviewer;
- one Hindi/Hinglish language reviewer;
- one Marathi language reviewer;
- one release owner who controls version and review metadata.

### 9.2 Required review

For every category and high-risk overlay, confirm:

- it is general information, not personalised advice;
- it does not predict an outcome;
- it does not invent statutes, deadlines, offices or procedures;
- it does not tell a user to ignore a notice, safety issue or approaching date;
- evidence guidance never encourages unlawful access, recording, fabrication,
  alteration or destruction;
- document requests are necessary and do not solicit OTP, PIN, CVV, password,
  full bank credentials or unrelated IDs;
- urgent wording is safe and does not claim NyaySetu dispatches emergency help;
- all three language meanings are equivalent;
- booking wording does not guarantee assignment, representation or outcome.

### 9.3 Version control

```text
LEGAL_CONTENT_VERSION=legal-content-2026-07-r4
LEGAL_CONTENT_REVIEWED_VERSION=legal-content-2026-07-r4
LEGAL_CONTENT_REVIEWED_ON=YYYY-MM-DD
```

Do not populate either review value until a reviewer approves that exact
version. Production readiness requires the reviewed version and active content
version to match. Any substantive wording change requires a new version. Keep the reviewer
identity, role, language scope, corrections and approval evidence in a secure
business record—not in the public repository.

### 9.4 Review cadence

Recommended internal policy:

- immediate review after a reported harmful or incorrect answer;
- monthly triage of “Need more help” and support themes;
- quarterly content accuracy review during the pilot/growth period;
- review whenever law, procedure, product scope or supported geography changes;
- annual full recertification at minimum, subject to counsel advice.

---

## 10. AI and knowledge strategy

### 10.1 Current approach

The default local provider is a deterministic knowledge engine. It routes a
question to reviewed content and does not require OpenAI, Claude or another
paid model API.

Benefits:

- predictable wording;
- no per-answer model charge;
- simpler privacy boundary;
- reviewable multilingual content;
- graceful operation during external AI outages;
- lower hallucination risk.

It still incurs content-review, development, hosting and maintenance cost.

### 10.2 When generative AI is not needed

Do not use a generative model for:

- menu navigation;
- issue/category selection;
- checklists;
- policy text;
- price, date, appointment and payment status;
- emergency/safety messages;
- deterministic support and booking workflows.

### 10.3 Conditions for future AI

Enable third-party or self-hosted generative AI only after:

- a measurable user need remains unresolved by reviewed content;
- privacy purpose and vendor terms/DPA are approved;
- consent and opt-out wording is approved;
- retention and deletion are defined;
- multilingual legal/safety evaluation passes;
- source grounding, uncertainty and human escalation exist;
- cost and response-latency limits are defined;
- provider failure returns to safe local content.

### 10.4 Home hardware

A 1 TB SSD, regular internet and spare phone can support:

- encrypted offline exports;
- a test device and business continuity contact;
- local model experiments;
- content authoring and quality evaluation.

They should not be the production web/database/payment host because home power,
internet, IP, physical security, monitoring and recovery are insufficient for
a dependable legal-payment service. A future local model should run on
suitable computing hardware, not the phone, and should remain optional.

---

## 11. Technical architecture

```text
WhatsApp user
    |
Meta Cloud API
    |
Signed Flask webhook
    |-----------------------> local/reviewed knowledge
    |-----------------------> optional approved AI provider
    |-----------------------> Razorpay payment links/API
    |-----------------------> SendGrid notifications
    |
SQLAlchemy + managed PostgreSQL
    |-- users and booking state
    |-- inbound/webhook idempotency
    |-- fulfilment and support
    |-- reconciliation and audit
    |-- durable outbox
    |
Scheduled jobs
    |-- outbox drain
    |-- payment reconciliation
    |-- reminder scheduler (disabled until approved)
    |-- maintenance/risk report
```

### 11.1 Runtime

- Python 3.11 target.
- Flask application.
- Gunicorn with exactly one `gthread` worker and eight threads.
- SQLAlchemy.
- PostgreSQL in production; SQLite only for development/testing.
- Alembic schema migration.
- Fully pinned production dependencies.
- Deterministic SBOM checked for drift.

### 11.2 Reliability controls

- signed Meta and Razorpay webhooks;
- unique provider/message IDs and idempotency;
- durable inbound claims and crash recovery;
- durable outbox with bounded retry/backoff;
- safe reply retry without replaying committed user state;
- provider evidence verification before payment entitlement;
- exact-evidence scheduled payment reconciliation;
- capacity-aware slot selection and database locks;
- fulfilment, support and payment-review queues;
- readiness/liveness endpoints;
- bounded maintenance and operational-risk exits.

### 11.3 Scale boundary

Do not add web workers or service instances merely because traffic increases.
Process-local rate limits, locks, caches and circuit breakers must first move
to shared infrastructure, and PostgreSQL concurrency/load tests must pass.

---

## 12. Data, privacy and retention strategy

### 12.1 Why a database remains necessary

A no-database design cannot reliably provide the same product. Email alone
cannot safely enforce:

- duplicate webhook protection;
- slot capacity;
- payment ownership and reconciliation;
- retryable notifications;
- appointment recovery;
- support/fulfilment state;
- audited operator actions;
- consent and policy versions.

The correct privacy strategy is not “no database.” It is “minimum necessary,
purpose-limited database.”

### 12.2 Data to retain

Keep only what is needed for:

- user language and structured profile;
- state/district and legal category;
- booking date, slot, stored amount and status;
- provider reference/evidence required for reconciliation;
- consent and terms versions;
- support and fulfilment lifecycle;
- minimal analytics events;
- delivery, webhook and operator audit evidence.

The normal conversation path should avoid storing full legal narratives.
Before launch, verify through tests and database inspection that no unexpected
message body is persisted. Do not add document upload until encryption,
malware scanning, access control, purpose and retention are designed.

### 12.3 Starting retention proposal

The following is a policy-design starting point, not a statement of legal
requirements:

| Data class | Proposed treatment |
|---|---|
| Completed delivery payload | Scrub recipient/content at terminal state; retain minimal status metadata temporarily |
| Terminal inbound/webhook events | Bounded short operational retention |
| Product analytics | Aggregate/minimise; short retention such as 90 days unless justified |
| Support records | Retain only while operationally necessary, then anonymise/delete subject to disputes/holds |
| Booking/payment/receipt evidence | Retain according to approved tax, accounting, payment, dispute and legal policy |
| Fulfilment/audit records | Retain under approved professional, consumer and security policy |
| Inactive user profile | Review for anonymisation/deletion after a defined inactivity period |
| Backups | Encrypt, limit access, test restore, expire under the same approved policy |

Qualified privacy/legal/accounting reviewers must approve exact periods.

### 12.4 User rights backlog

Before broad growth, implement:

- access/export request;
- correction;
- consent withdrawal;
- deletion/anonymisation;
- legal hold;
- backup deletion propagation;
- identity verification and request audit.

---

## 13. Security strategy

### 13.1 Built controls

- raw-body webhook signature verification;
- request-size limits and safe malformed-input handling;
- strict payment ownership, amount, capture and refund checks;
- no payment confirmation from user claims;
- transactionally durable outbox;
- pseudonymous/minimised logs and analytics;
- best-effort AI PII scrubbing;
- environment-based secrets;
- protected admin APIs and audit events;
- readiness enforcement for strong configuration;
- pinned dependencies, SBOM, CI and vulnerability audit workflow.

### 13.2 Required launch verification

- secret scan of source and release artifact;
- all `r4` CI jobs green;
- dependency audit with no unaccepted critical/high finding;
- missing/invalid signature tests;
- replay, duplicate and provider-failure tests;
- external webhook/admin API penetration test;
- TLS and platform identity/MFA around admin access;
- least-privilege database and provider credentials;
- secret-rotation rehearsal;
- database restore rehearsal;
- log inspection for phone, legal narrative, payment link, email, credentials
  or outbox payload;
- incident-response contacts and severity process.

### 13.3 Admin limitation

The application currently uses a shared admin secret. Platform access controls
and MFA must protect it during pilot. Individual RBAC/MFA is a priority before
more operators receive access.

---

## 14. Fresh production infrastructure plan

### 14.1 Required cloud components

1. Paid web service with no free-tier sleep.
2. New managed PostgreSQL database in the same region.
3. Scheduled outbox job.
4. Scheduled payment-reconciliation job.
5. Scheduled maintenance/risk job.
6. Reminder job present but inactive until approved templates.
7. Meta WhatsApp Cloud API configuration.
8. Razorpay test and later live configuration.
9. Verified SendGrid sender and operational recipients.
10. HTTPS policy/support pages and a controlled domain.
11. Monitoring and alert destination.

### 14.2 Fresh-release database procedure

Because no legacy data is required:

1. Create an empty managed PostgreSQL database.
2. Create least-privilege application credentials.
3. Run Alembic to the expected revision.
4. Confirm readiness rejects SQLite and schema drift.
5. Run booking/payment/provider scenarios only against a separate staging
   service and staging database.
6. Create or re-create the empty production database after staging acceptance;
   never copy staging test rows into it.
7. Enable managed backups and complete one restore test.

The old-bot SQLite cutover utility and old-data backup are not part of this
fresh-release path.

### 14.3 Environment separation

| Environment | Providers | Data | Purpose |
|---|---|---|---|
| Development | Mock/test | Synthetic | Engineering |
| Staging | Meta test, Razorpay test, isolated email/PostgreSQL | Synthetic | Acceptance and failure testing |
| Production | Live approved accounts | Real, minimised | Controlled users |

Never share secrets or databases across these environments.

---

## 15. Quality assurance and release gates

### 15.1 Automated checks

The exact candidate must pass:

```text
python -m compileall ...
python -m ruff check .
python -m pytest -q
python -m pip check
python -m jobs.generate_sbom --check
python -m pip_audit --progress-spinner off -r requirements.lock
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini check
```

GitHub Actions is the authoritative full automated gate for the uploaded
candidate. Local compilation alone is insufficient.

### 15.2 Staging cases

- complete every primary journey in all supported languages;
- payment exact amount, wrong amount, duplicate, delayed and provider-down;
- duplicate Meta/Razorpay events;
- WhatsApp and email failure followed by outbox recovery;
- pending-link expiry and capacity release;
- support, fulfilment, refund-review and availability operations;
- payment reconciliation recovers only exact evidence;
- maintenance dry run preserves protected records;
- reminder no-op with empty template pairs;
- fresh PostgreSQL migration, backup and restore;
- safe rollback to the previous saved release.

### 15.3 Production no-go conditions

Do not launch if any of these are true:

- `r4` CI is red or incomplete;
- legal/language review is missing;
- policy/support URLs or contacts are placeholders;
- production readiness endpoint is failing;
- the database is SQLite;
- Razorpay is incorrectly mixed between test/live mode;
- provider signature verification is bypassed;
- human consultation fulfilment is unstaffed;
- refund/cancellation/support procedure is undefined;
- alerts, backup or rollback are untested;
- critical/high product-review findings remain open.

---

## 16. Operations and human service model

### 16.1 Required roles

| Role | Core responsibility |
|---|---|
| Product owner | Scope, priorities, acceptance and metrics |
| Release/engineering owner | Code, CI, deployment, rollback |
| Legal-content owner | Accuracy, version and corrections |
| Language reviewers | Hindi/Hinglish and Marathi quality |
| Consultation operations lead | Capacity, advocate assignment and SLA |
| Support owner | User/payment/support queue |
| Payment/reconciliation owner | Unmatched/mismatch review |
| Privacy/security owner | Access, incidents, retention and requests |
| Marketing owner | Approved claims, channels and funnel |

One person may hold multiple roles during pilot, but each responsibility must
have a named owner and backup.

### 16.2 Daily operating routine

- check readiness and provider dashboards;
- check outbox age/dead jobs;
- check payment-reconciliation queue;
- check paid-but-unassigned fulfilments;
- check open/ageing support;
- verify next-day capacity;
- record incidents and user-impact decisions;
- never resolve ambiguity by manually marking payment without provider
  evidence and audit.

### 16.3 Weekly routine

- review failed journeys and “Need more help” themes;
- reconcile paid bookings and provider records;
- sample notification/fulfilment quality;
- review security/dependency alerts;
- review capacity, conversion and support SLA;
- approve content corrections for the next version;
- verify backup status.

### 16.4 Monthly/quarterly routine

- restore drill;
- secret/access review;
- legal/language content review;
- retention/cleanup review;
- incident and near-miss review;
- product roadmap and marketing-claim review;
- cost versus conversion and fulfilment capacity review.

---

## 17. Monitoring and service objectives

Initial pilot targets should be internal operating objectives, not public
guarantees:

| Measure | Suggested pilot target |
|---|---|
| Web availability | At least 99.5% measured monthly |
| Readiness | Continuously monitored |
| Ordinary response latency | Majority within a few seconds, excluding provider delay |
| Payment confirmation | Normally within provider event/reconciliation window |
| Dead outbox jobs | Zero unattended |
| Paid unassigned bookings | Zero beyond approved assignment SLA |
| Critical support/payment incident | Immediate owner notification |
| Backup | Automated plus documented restore test |
| Critical vulnerability | No unaccepted finding at release |

Alert on:

- webhook 5xx;
- readiness failure;
- database saturation;
- outbox backlog/dead jobs;
- unmatched or mismatched payment;
- payment confirmation latency;
- paid fulfilment SLA breach;
- support backlog age;
- scheduled-job failure;
- abnormal traffic/rate limiting.

---

## 18. Product improvement roadmap

### Phase 0: Acceptance and launch foundation

- conversation/product review;
- legal/native-language approval;
- `r4` CI;
- privacy, terms, refund, cancellation and support policy;
- fresh staging and production PostgreSQL;
- provider and rollback rehearsal;
- named fulfilment/support staffing.

### Phase 1: Controlled pilot

- launch to a capped group;
- manually assign qualified advocates;
- monitor payment, support and fulfilment every day;
- improve high-volume FAQ routes from privacy-safe feedback;
- publish clear consultation channel and response target;
- provide support-ticket acknowledgement/status.

### Phase 2: Service maturity

- user-visible assigned professional/channel;
- controlled paid reschedule/cancel/refund request;
- provider refund execution with approval/idempotency;
- individual operator RBAC/MFA;
- privacy export/correction/deletion/legal hold;
- settlement and chargeback reconciliation;
- stronger operator dashboard.

### Phase 3: Content leadership

- counsel-owned source repository;
- jurisdiction and source metadata;
- legal-review dates per content item;
- broader native Hindi content;
- more Marathi terminology review;
- decision trees for high-volume issues;
- source-backed “What to do now” and document checklists;
- correction/public-change workflow;
- uncertainty-to-human routing.

### Phase 4: Responsible engagement

- approved opt-in appointment reminders;
- preparation progress checklist;
- saved non-sensitive session summary;
- return-to-status shortcut;
- helpfulness-driven content iteration;
- user-visible support progress;
- carefully governed referral/education campaigns.

### Phase 5: Scale

- advocate qualification/conflict/availability matching;
- distributed rate limiting/WAF;
- shared cache/locks and multi-worker readiness;
- CRM/accounting integration after privacy review;
- performance baselines and synthetic provider monitoring;
- broader geography only after fulfilment capacity exists.

---

## 19. Engagement strategy

The objective is not to keep a distressed user chatting. The objective is to
help them complete a useful task and trust NyaySetu enough to return when
needed.

### 19.1 Healthy engagement

- fast category discovery;
- clear next action;
- preparation checklist;
- appointment status;
- support recovery;
- reviewed reminders with opt-in;
- feedback;
- returning-user shortcut;
- useful educational content outside private chat.

### 19.2 Patterns to avoid

- artificial urgency;
- repeated unsolicited WhatsApp messages;
- hidden price or payment pressure;
- fake typing/professional presence;
- “guaranteed win,” “best lawyer” or “instant legal solution” claims;
- forcing a user to disclose a private narrative;
- making guidance longer to increase session duration;
- activating reminder/campaign templates without approval and consent.

### 19.3 Core engagement metrics

- guide completion;
- helpful rate;
- `Not Sure` and support handoff rate;
- booking-review completion;
- payment-link-to-paid conversion;
- appointment fulfilment;
- support resolution;
- repeat useful action;
- complaint/refund rate.

Conversation length should be a diagnostic metric, not a success target.

---

## 20. Marketing and go-to-market strategy

### 20.1 Positioning

Recommended headline:

> **Understand your next legal step on WhatsApp.**

Supporting message:

> Choose your language, organise the issue, prepare documents and book a
> consultation when you are ready.

Avoid positioning NyaySetu as an “AI lawyer,” emergency service, guaranteed
resolution provider or automatic lawyer marketplace until those capabilities
and approvals exist.

### 20.2 First market

Start narrowly:

- one or a small number of districts where fulfilment is dependable;
- English, Hindi/Hinglish and Marathi users;
- high-volume, understandable categories such as job, consumer, family,
  property, banking/cyber and document/notice preparation;
- capped appointment capacity.

Do not market nationally before advocate coverage, language review, support
and capacity are proven.

### 20.3 Channel strategy

1. **Educational short-form content**  
   Simple checklists and myths/facts in the three languages. Every post should
   be reviewed and end with a general-information disclaimer.

2. **Local search presence**  
   Clear service scope, hours, geography, price approach, policy links and
   WhatsApp entry. Do not collect fabricated reviews.

3. **Professional partnerships**  
   Qualified advocates, accountants, HR consultants, housing/community
   organisations and lawful aid/NGO networks where interests and referral
   disclosures are controlled.

4. **Community education**  
   Webinars or local sessions on document preparation and how consultations
   work—not personalised mass advice.

5. **Opt-in WhatsApp education**  
   Only after consent/template/frequency rules are approved. Never upload
   scraped or purchased phone lists.

6. **Referral after successful fulfilment**  
   Ask for feedback or referral only after service delivery, without offering
   misleading incentives or pressuring users.

### 20.4 Content pillars

- “What documents should I keep?”
- “What happens in the first consultation?”
- “How to identify urgent versus non-urgent situations?”
- “How to avoid common online/payment fraud?”
- “How to organise a timeline.”
- “What NyaySetu can and cannot do.”
- Language-specific FAQ and user education.
- Product trust: privacy, verified payment and transparent booking.

Avoid publishing exact deadlines, statutory claims or jurisdiction-dependent
procedure without versioned legal review.

### 20.5 90-day go-to-market

**Days 1–30: Proof**

- complete product/legal/staging gates;
- recruit a small invitation-only pilot;
- publish essential trust pages;
- establish baseline funnel and support metrics;
- collect structured feedback, not private case stories.

**Days 31–60: Improve**

- fix high-frequency confusion;
- expand reviewed FAQ aliases/content;
- stabilise fulfilment and support;
- publish a small reviewed multilingual education library;
- begin limited local partnerships.

**Days 61–90: Controlled acquisition**

- increase traffic only to available capacity;
- test small channel budgets separately;
- measure paid fulfilment and complaint/refund outcomes;
- stop channels that produce poor-fit or unsupported cases;
- approve the next geography/category only with capacity and content.

### 20.6 Marketing funnel

```text
Educational/local discovery
  -> WhatsApp start
  -> language/home
  -> useful guide or booking scope
  -> booking review
  -> verified payment
  -> fulfilled consultation
  -> feedback/referral
```

Optimise the whole funnel. A high number of WhatsApp starts with poor
fulfilment is not growth.

### 20.7 Marketing metrics

- qualified WhatsApp starts by channel;
- guide completion/helpfulness;
- booking start/review/link/paid conversion;
- customer acquisition cost;
- fulfilled-consultation rate;
- support contacts per paid booking;
- refund/dispute/complaint rate;
- repeat/referral rate;
- contribution after provider, fulfilment and support cost;
- language/category/geography demand versus capacity.

Use minimum cohort sizes and avoid exposing identifiable user/legal data.

### 20.8 Marketing approval checklist

- claim is true in the live product;
- legal/professional advertising rules reviewed;
- no outcome guarantee;
- geography and operating hours accurate;
- price/scope accurate;
- disclaimer present where needed;
- consent/template approval for WhatsApp outreach;
- landing link, support and policy pages work;
- fulfilment capacity available;
- campaign can be paused immediately.

---

## 21. Commercial and pricing model

### 21.1 Current model

The code supports one configurable fixed-fee consultation. The repository has
used INR 499 as a default/example, but production price must be explicitly
approved. Partial payment is disabled. Revenue recognition and tax treatment
must be confirmed with accounting/legal owners.

### 21.2 Pricing decision factors

- advocate fulfilment cost;
- consultation duration;
- support and payment-provider cost;
- refund/no-show risk;
- taxes and receipt requirements;
- category/geography complexity;
- customer acquisition cost;
- target contribution margin;
- affordability and transparent scope.

### 21.3 Future monetisation—only after the core service works

- category-specific consultation products;
- reviewed document-preparation services;
- business/HR legal-information packages;
- enterprise or community access;
- subscriptions only when repeat value is genuine;
- advocate marketplace only after qualification, conflict, matching and
  professional-governance controls.

Never charge for an unclear or unavailable service.

---

## 22. INR 25,000 launch-budget framework

This is a planning allocation, not a vendor quotation:

| Area | Proposed allocation |
|---|---:|
| Paid hosting and managed database reserve | INR 7,000 |
| Domain, provider testing, email/communications and test payments | INR 3,000 |
| Qualified legal and native-language content review | INR 6,000 |
| Security, staging, operational rehearsal and contingency testing | INR 3,000 |
| Small controlled marketing pilot | INR 3,000 |
| General contingency | INR 3,000 |
| **Total** | **INR 25,000** |

Principles:

- do not spend marketing money before fulfilment and support are ready;
- do not choose sleeping/free production infrastructure for a payment service;
- keep generative-AI spend at zero initially;
- use a small pilot and scale from revenue/evidence;
- obtain actual quotations before approving the allocation;
- treat payment-provider transaction fees and advocate fulfilment as variable
  operating costs, not unlimited coverage under this one-time budget.

---

## 23. Metrics and management dashboard

### 23.1 North-star measure

**Percentage of users who complete a safe, useful next action**:

- receive a helpful guide;
- reach appropriate support/human escalation;
- complete a verified and fulfilled consultation.

### 23.2 Funnel

- new users;
- language selected;
- guide opened/completed/helpful;
- booking scope viewed;
- booking started;
- review reached;
- payment link created;
- payment verified;
- fulfilment assigned/completed;
- feedback submitted.

### 23.3 Reliability

- webhook success/failure;
- duplicate suppression;
- payment confirmation latency;
- reconciliation open/recovered/terminal;
- outbox queued/retry/dead/age;
- readiness uptime;
- scheduled-job success;
- database pool/latency.

### 23.4 Service quality

- paid-to-fulfilled rate;
- assignment/contact/completion time;
- no-show/reschedule/refund/dispute;
- support backlog and resolution time;
- complaint rate;
- category/language helpfulness;
- unclear/`Not Sure` routing.

### 23.5 Privacy and safety

- data incidents;
- sensitive-data log findings;
- urgent-route failures;
- legal-content corrections;
- consent/opt-out events;
- access and secret-rotation exceptions;
- retention/risk job findings.

---

## 24. Risk register

| Risk | Severity | Current mitigation | Required next action |
|---|---|---|---|
| Legal content is incomplete/outdated | High | Disclaimer, versioning, deterministic content | Counsel and native-language approval of `r4` |
| Paid user lacks human fulfilment | Critical | Fulfilment queue exists | Staff, qualify, assign and document SLA/channel |
| Payment/provider failure | High | Signed webhooks, idempotency, reconciliation, outbox | Staging tests, monitoring and staffed review |
| Sensitive data retained too long | High | Minimised logs/analytics and bounded cleanup | Approve retention, rights, backup and legal holds |
| Shared admin token compromised | High | Token/audit controls | Platform MFA/access, rotation, later RBAC |
| Free/sleeping infrastructure delays users | High | Paid topology recommended | Choose paid web/database for production |
| Unsupported marketing claim | High | Conservative positioning | Formal claim approval and campaign checklist |
| Demand exceeds advocate capacity | High | Configurable capacity | Geography/category caps and daily monitoring |
| Hindi/Marathi meaning error | High | Separate language content | Native moderated review and retest |
| Reminder violates consent/template rules | Medium | Empty configuration makes it inert | Keep disabled until approval and QA |
| In-memory controls fail at horizontal scale | Medium | One-worker enforcement | Shared controls and load test before scaling |
| Static guide cannot handle unique facts | Medium | Human booking/support handoff | Improve uncertainty routing and source-backed content |
| Home hardware outage/security | Medium | Not used for primary hosting | Limit it to test/offline auxiliary use |
| No legacy backup | Low for chosen fresh release | No legacy data will be imported | Document final approval and protect new data |

---

## 25. Six-month plan

### Month 1: Acceptance and staging

- partner decisions;
- conversation/product review;
- legal/language review;
- `r4` CI and security checks;
- policy pages;
- fresh staging PostgreSQL and provider tests.

### Month 2: Controlled production pilot

- paid production infrastructure;
- capped users/geography/capacity;
- daily operations;
- immediate P0/P1 fixes;
- no broad paid marketing.

### Month 3: Fulfilment and support maturity

- visible service channel and response expectation;
- stronger operator procedures;
- support status;
- paid-change request design;
- privacy-rights design.

### Month 4: Content depth

- review feedback themes;
- expand decision trees/checklists;
- native Hindi improvement;
- source/provenance model;
- category-level quality benchmarks.

### Month 5: Responsible engagement and partnerships

- approved reminder readiness;
- local professional/community partnerships;
- reviewed education library;
- small measured acquisition tests.

### Month 6: Scale readiness review

- restore, incident and rollback drill;
- RBAC/MFA and privacy-lifecycle status;
- unit economics and customer-acquisition review;
- capacity and advocate-quality review;
- decide whether to expand geography, categories or AI.

The next major release after six months should be based on operational
evidence, not a promise that the initial release can remain untouched.
Security patches, content corrections, secret rotation and provider-required
changes may still be needed during the six-month period.

---

## 26. Immediate action plan

### Step 1: Partner review of this document

Mark every unresolved decision as:

- approved;
- change requested;
- owner assigned;
- deferred with reason.

### Step 2: Conversation/product review

Run the structured scenario matrix. Resolve critical/high findings first.

### Step 3: Legal and language review

Review exact `r4` content and record secure sign-off. Change the content
version if corrections are made.

### Step 4: Freeze and upload the exact candidate

- rebuild archive after any change;
- verify SHA-256;
- upload/commit to GitHub;
- confirm `.env` and credentials are absent.

### Step 5: CI and security gate

All exact-commit jobs must pass. Resolve Dependabot only through reviewed
changes and passing CI.

### Step 6: Staging

Create isolated managed PostgreSQL and test provider resources. Execute the
complete acceptance/failure matrix.

### Step 7: Production approval

Sign off policy, price, capacity, staffing, monitoring, backup, rollback and
campaign scope.

### Step 8: Controlled launch

Launch to a capped cohort, monitor daily and pause acquisition if fulfilment,
payment, safety or support indicators breach limits.

---

## 27. Master production-readiness checklist

### Product

- [ ] Target users, geography and categories approved.
- [ ] Service scope, consultation channel and price approved.
- [ ] Conversation review passed in all three languages.
- [ ] No critical/high usability issue open.
- [ ] Support and booking recovery paths verified.

### Legal and policy

- [ ] Exact legal-content version approved.
- [ ] Native-language reviews completed.
- [ ] Privacy, terms, AI, refund and cancellation pages published.
- [ ] Advocate qualification/conflict/service process approved.
- [ ] Retention, grievance, tax/receipt and incident policies approved.

### Engineering

- [ ] Exact candidate committed and hashed.
- [ ] GitHub CI fully green.
- [ ] Dependency audit reviewed.
- [ ] Fresh PostgreSQL at expected Alembic revision.
- [ ] Signed webhook, payment and outbox failure tests passed.
- [ ] Release and rollback rehearsed.

### Security/privacy

- [ ] No secrets in repository/artifact/logs.
- [ ] Platform MFA/access around admin routes.
- [ ] Least-privilege credentials.
- [ ] Secret rotation rehearsed.
- [ ] Penetration/security review completed.
- [ ] Backup encryption and restore test completed.

### Providers

- [ ] Meta number/app/webhook approved and signed.
- [ ] Razorpay mode, key and webhook correctly matched.
- [ ] SendGrid sender and recipients verified.
- [ ] Policy/support URLs are HTTPS and correct.
- [ ] Reminder template pairs remain empty unless fully approved.

### Operations

- [ ] Fulfilment owner and backup named.
- [ ] Support owner and backup named.
- [ ] Payment review owner named.
- [ ] Capacity/calendar configured.
- [ ] Daily queue procedure rehearsed.
- [ ] Alerts active and tested.

### Marketing

- [ ] Claims match live capability.
- [ ] Initial geography/category capacity exists.
- [ ] Campaign links and support work.
- [ ] No unsolicited WhatsApp list.
- [ ] Pilot budget and stop conditions approved.

### Launch decision

- [ ] Product owner: GO
- [ ] Engineering/release owner: GO
- [ ] Legal/content owner: GO
- [ ] Privacy/security owner: GO
- [ ] Operations/fulfilment owner: GO
- [ ] Business owner: GO

Any required owner saying NO keeps the release in staging.

---

## 28. Definition of success

NyaySetu succeeds when:

- users understand their next step without needing legal terminology;
- high-risk users receive safe, short escalation;
- users do not have to install software;
- private narratives are not unnecessarily collected;
- payment is transparent and independently verified;
- every paid booking receives accountable human fulfilment;
- support and failures are recoverable;
- legal information is versioned and reviewed;
- growth stays within service capacity;
- the business learns from privacy-safe outcomes rather than maximising chat
  time.

The aim is not to claim that NyaySetu is “production ready forever.” The aim is
to operate a trustworthy platform with clear owners, measurable controls and a
repeatable review-and-release system.

---

## 29. Document governance

This file should remain the consolidated management blueprint. Update it when:

- product scope, geography, language or price changes;
- a capability moves from Future to Built, Staging verified or Live;
- a legal-content version changes;
- architecture, data model, provider or environment changes;
- retention, refund, support or fulfilment policy changes;
- a new material risk or incident occurs;
- a roadmap milestone is approved or completed.

Every update should record:

- date;
- author/owner;
- sections changed;
- reason;
- approvals required;
- related release/commit/content version.

Detailed technical runbooks remain in the repository, but this master must
always accurately summarise their business and release consequences.
