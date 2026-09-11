# Questionnaire Contract: Single-Cheque Section 138 Demand Notice

**Status:** revalidated private Phase D runtime schema; not connected to the
customer journey or global allowlist  
**Schema:** `in-ni138-single-cheque-en-2026-09-v1`  
**Output:** advocate-triage facts, not an automatic legal conclusion

Exactly one approved schema may be active for this product, language and
jurisdiction. No tester-specific questionnaire or simultaneous V1/V2 route is
permitted.

## Experience target

The shortest supported WhatsApp path targets **18 customer response screens
before separate evidence upload**. The 18 include final fact confirmation,
review consent and contact permission. Questions are arranged in six visible
sections. The user can `Save & Exit` at every non-payment step and can correct
one section without repeating the entire intake.

Where the customer already has a confirmed NyaySetu name or address, the bot
offers explicit reuse. It never silently copies an address into the legal
record. Long legal explanations are shown once as help, not repeated after
every answer.

## Global data rules

- Collect only facts needed for triage, drafting, issuance and service.
- Reject control characters, executable markup and over-limit values.
- Preserve both normalized and exact customer-confirmed display values where
  spelling, cheque number, return reason or address is material.
- Never infer payee status, enforceability, service, jurisdiction or deadline.
- Never ask for Aadhaar, PAN, card details, bank password, OTP, PIN or CVV.
- Do not ask the user to paste a full bank account number in chat.
- Every question records stable field code, version, purpose, sensitivity,
  validation and source.
- A route-out records a reason code without reproducing confidential facts in
  logs or analytics.

## Section 1: Suitability

Four grouped confirmations keep the intake short while preserving each
individual proposition in the confirmed snapshot.

| Field code | Customer-facing proposition | Result |
| --- | --- | --- |
| `claimant_scope` | I am the individual named as payee; I act for myself; the drawer is one living adult individual | `YES` continues; otherwise route |
| `instrument_scope` | This request concerns one cheque, one return event and no earlier statutory notice | `YES` continues; otherwise route |
| `liability_scope` | The cheque was issued for a real legally payable debt/liability, not a gift or uncertain security arrangement | `YES` records a statement only; advocate decides |
| `conflict_scope` | There has been no part-payment, settlement, replacement cheque, insolvency or existing proceeding concerning this demand | `YES` continues; otherwise route |

Each grouped proposition must be displayed in full before the button. The
stored confirmed snapshot retains its exact sub-statements so later text
changes alter the schema hash.

## Section 2: People and addresses

| Field code | Meaning | Validation |
| --- | --- | --- |
| `payee_full_name` | Name exactly as intended in the notice | 2-160 bounded Unicode characters |
| `payee_notice_address` | Complete address used in the notice | Structured/bounded; explicit profile reuse allowed |
| `drawer_full_name` | Drawer name from cheque and supporting material | 2-160 bounded characters; no inferred honorific |
| `drawer_service_address` | Primary notice-service address | Complete bounded address with PIN when available |
| `drawer_alternate_address_present` | Whether advocate should review a second known address | `YES`/`NO` |
| `drawer_alternate_address` | Second service address | Asked only after `YES`; not merged with primary |

The customer confirms a rendered address card for each address. PIN/reference
data may suggest a locality but never proves residence, business presence or
service.

## Section 3: Debt and cheque

| Field code | Meaning | Validation |
| --- | --- | --- |
| `liability_category` | Personal loan for the first standard package | Every other category routes before standard drafting/payment |
| `liability_summary` | Short factual origin of the stated debt | 20-800 characters; no generated accusation |
| `liability_due_date` | Date payment was allegedly due | Valid date; uncertainty routes |
| `cheque_number` | Exact cheque number | Digits/characters permitted by reviewed bank formats; confirm twice |
| `cheque_date` | Date written on cheque | Valid date; no automatic conclusion |
| `cheque_amount_inr` | Exact cheque amount | Positive INR with two-decimal maximum; render digits and words |
| `payee_name_on_cheque` | Payee text as written on cheque | Exact bounded text; advocate compares evidence |
| `drawer_bank_name` | Drawee bank | Controlled suggestion plus confirmed display value |
| `drawer_bank_branch` | Branch shown/known | Bounded text; do not require account number |

The review screen displays the cheque number and amount twice: once in the
cheque facts and once in the proposed statutory-demand control. A mismatch
blocks rendering. The user cannot override that block through free text.

## Section 4: Presentation and dishonour

| Field code | Meaning | Validation |
| --- | --- | --- |
| `presented_on` | Date cheque was presented/deposited | Valid date, not before cheque date without advocate route |
| `return_memo_date` | Date on bank return memo/advice | Valid date |
| `dishonour_information_received_on` | Date payee received bank information | Explicit customer answer; never default to memo date |
| `return_reason_exact` | Exact bank return reason | Only exact `FUNDS INSUFFICIENT` is in the first standard package; every other reason routes for separate review |
| `return_bank_name` | Bank that communicated return | Bounded confirmed value |

The application may show:

> This appears urgent based on the dates you entered. Only an advocate can
> confirm the applicable deadline after checking the documents and service
> facts.

It must not show “eligible”, “deadline guaranteed”, “X days safely remain” or
an automatic complaint-filing date.

## Section 5: Evidence and changes after cheque issue

The customer completes one checklist, followed only by applicable uploads or
questions.

| Field code | Meaning | Behaviour |
| --- | --- | --- |
| `evidence_checklist` | Cheque copy, return memo and debt support available | Missing mandatory items pauses without payment |
| `post_issue_change` | Any payment, part-payment, settlement, set-off, replacement instrument or written adjustment | Any positive/uncertain answer routes to advocate before standard drafting |
| `prior_demand_or_notice` | Any earlier demand/statutory notice for the same cheque | Any positive/uncertain answer routes |
| `existing_proceeding` | Any complaint, suit, arbitration, insolvency or police proceeding | Any positive/uncertain answer routes |

Candidate evidence kinds:

- `CHEQUE_FRONT`
- `RETURN_MEMO`
- `LIABILITY_SUPPORT`
- `POST_ISSUE_COMMUNICATION` when applicable
- `ADDRESS_SUPPORT` only when requested by the advocate

Every upload has a random artifact reference, private object key, declared
type, detected type, checksum, size, malware-validation state, uploader,
access audit and retention state. OCR values remain untrusted suggestions.

## Section 6: Review and advocate handover

The final customer review contains:

1. Parties and both service addresses.
2. Liability category, due date and factual summary.
3. Cheque number, date, exact amount in digits and words, bank and branch.
4. Presentation, return memo, receipt-of-information date and exact reason.
5. Evidence received/missing status.
6. Explicit disclosure of any post-issue change or existing proceeding.
7. Statement that no notice, deadline, service or remedy has been legally
   confirmed yet.

| Field code | Meaning | Validation |
| --- | --- | --- |
| `facts_confirmed` | Customer confirms displayed facts match their records | Exact `CONFIRM`; otherwise section editor |
| `review_consent` | Customer permits the assigned advocate to access the stated facts and uploaded evidence for this request | Versioned explicit consent |
| `contact_permission` | Advocate/operator may contact the customer about missing facts, scope and quote | Explicit channel choice |

Confirmation creates an immutable intake revision but does **not** create a
payment entitlement or advocate-client relationship. The next state is
`ADVOCATE_TRIAGE` only after evidence validation succeeds.

## Advocate-only fields

These fields are never answered or altered by the customer:

| Field code | Purpose |
| --- | --- |
| `conflict_check_status` | Passed, failed or more information required |
| `advocate_scope_decision` | Accept standard product, route custom, decline or urgent manual action |
| `advocate_deadline_assessment` | Reviewed event dates, assumptions, confidence and next action |
| `advocate_liability_assessment` | Whether evidence supports use of the proposed statutory route |
| `advocate_return_reason_assessment` | Whether exact return reason is within approved treatment |
| `advocate_demand_amount` | Exact reviewed statutory demand amount |
| `advocate_service_plan` | Approved address and dispatch method |
| `quote_minor` | Matter-specific immutable quote in INR minor units |
| `quote_scope_version` | Included work, revisions, dispatch, tax and refund terms |
| `final_review_decision` | Approved, changes required or declined |
| `final_artifact_hash` | Exact locked PDF approved for issue |

Advocate decisions record the authenticated advocate identity, order,
revision, time, reason and source version. Operators cannot substitute their
own legal decision.

## Correction and expiry rules

- Customer corrections before advocate acceptance create a new intake
  revision and return the matter to evidence validation.
- Corrections after quote invalidate the quote unless the advocate confirms no
  scope impact.
- Corrections after payment invalidate the draft approval and require
  advocate re-review without silently changing refund/SLA obligations.
- Corrections after final approval invalidate issuance; the approved PDF is
  never overwritten.
- Incomplete intake expiry releases capacity and deletes/redacts data according
  to the approved retention schedule.
- No evidence or matter record is destroyed when a legal hold, paid-order
  dispute or professional record obligation applies.

## Questionnaire acceptance tests

- [x] Shortest package schema contains 18 non-conditional customer responses,
  including final fact confirmation and consent, before separate evidence
  upload.
- [ ] Save/resume restores the exact section and does not duplicate an order.
- [ ] Profile/address reuse is always explicit and separately confirmed.
- [ ] Every unsupported or uncertain answer routes before payment.
- [ ] Missing cheque or return memo cannot reach advocate acceptance.
- [ ] Cheque amount is confirmed twice and an inconsistency fails closed.
- [ ] Memo date and receipt-of-information date remain separate.
- [ ] Date warnings never claim a conclusive statutory deadline.
- [ ] OCR cannot alter a confirmed fact or populate an issued document without
  customer and advocate confirmation.
- [ ] Customer cannot write an accusation into a legal clause through free
  text.
- [ ] Every post-confirmation edit invalidates dependent review evidence.
- [ ] Hindi/Marathi navigation cannot expose an English legal notice as if it
  were translated or reviewed in that language.
