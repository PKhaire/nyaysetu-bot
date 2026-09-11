# Product Specification: Single-Cheque Section 138 Demand Notice

**Status:** revalidated for private Phase D implementation on 11 September
2026; not customer-visible, globally allowlisted or approved for launch  
**Research cut-off:** 10 September 2026  
**Activation rule:** fail closed until the exact questionnaire, legal text,
review workflow, evidence controls and golden artifacts receive authenticated
advocate approval

This document is a product boundary, not a legal opinion or reusable notice.
The assigned advocate remains responsible for every notice that is issued.

## Product identity

| Item | Candidate decision |
| --- | --- |
| Product code | `in_ni138_single_cheque_individual_advocate_issued` |
| Display name | Cheque Bounce Demand Notice |
| Output class | Advocate-Issued Notice |
| Governing statute | Negotiable Instruments Act, 1881, especially sections 138 and 142 |
| Geographic scope | India; only where the assigned advocate confirms authority and forum implications |
| Language | English first; no translated legal output before separate native legal review |
| Instrument scope | One cheque and one bank-return event |
| Parties | Individual payee and individual drawer, each acting personally |
| Matter-specific review | Mandatory before payment and again before issuance |
| Customer preview | Confirmed factual summary, not an issuable statutory notice |
| Paid output | Locked advocate-issued PDF plus dispatch and next-step record |
| Editable DOCX | Not supplied for an advocate-issued or signed notice |
| Price and turnaround | Matter-specific quote after advocate acceptance; no fixed catalogue price |

The code and marketing name are provisional until product, legal, privacy and
operations review. An activated code is stable. Every change to legal wording,
questions, derived dates, evidence requirements, output or review conditions
creates a new immutable package and approval decision.

## Customer promise

Draft Studio collects and organises customer-confirmed facts for an assigned
advocate. The advocate checks whether the matter is within the offered scope,
reviews the supporting material, accepts or declines the engagement, settles
the exact notice text, and explicitly approves the final artifact before it is
issued.

NyaySetu does not promise that:

- the cheque creates a legally enforceable debt;
- section 138 applies to a stated return reason or factual situation;
- a notice was or will be served on a particular date;
- a complaint is maintainable, timely or likely to succeed;
- an amount other than the exact cheque amount may safely be demanded;
- the drawer will pay; or
- criminal, civil, insolvency or other remedies are available.

## Why this is not self-service

Section 138 uses linked conditions involving the instrument, liability,
presentation, dishonour information, written demand and receipt of notice.
Section 142 then governs cognizance, complainant status, filing time and
territorial jurisdiction. Small factual or drafting errors can affect the
statutory route. The product therefore never produces an instant unsupervised
notice or automatically applies an advocate signature.

## Candidate eligibility matrix

Every `ALLOW` answer opens an advocate review; it is not a legal conclusion.
`ROUTE` stops product payment and offers consultation/manual handling.

| Code | Candidate condition | Result if not clearly satisfied |
| --- | --- | --- |
| CB-EL-01 | Customer is the named payee acting personally | Route; holder-in-due-course and representative cases need separate review |
| CB-EL-02 | Drawer is one living adult individual acting personally | Route companies, firms, associations, joint drawers, representatives, death or incapacity |
| CB-EL-03 | Exactly one cheque is involved | Route multiple or consolidated instruments |
| CB-EL-04 | Customer states the cheque was for a legally enforceable debt or liability | Route gifts, wagering, security-only, disputed consideration or uncertain liability |
| CB-EL-05 | Cheque was presented within its applicable validity period | Route stale, post-dated, altered or uncertain presentation cases |
| CB-EL-06 | A bank returned the cheque and issued identifiable return information | Route missing or contradictory return evidence |
| CB-EL-07 | No earlier section 138 notice has been issued for this dishonour | Route repeat, withdrawn, corrected or successive-notice cases |
| CB-EL-08 | No payment, part-payment, settlement, replacement instrument or material adjustment occurred after cheque issue | Route for individual legal analysis |
| CB-EL-09 | No complaint, suit, arbitration, insolvency, police case or settlement proceeding is already pending for the same demand | Route potential overlap and strategy issues |
| CB-EL-10 | Customer can provide a complete service address for the drawer | Route uncertain or foreign service |
| CB-EL-11 | Customer can provide the cheque, return memo and debt-supporting material for advocate review | Pause without payment until evidence is available |
| CB-EL-12 | Assigned advocate confirms sufficient time remains after reviewing actual dates | Urgent manual handling or decline; software does not cure expiry |

## Explicit exclusions for the first release

- Company, LLP, partnership, trust, association, government or representative
  parties, including director/officer liability under section 141.
- Holder-in-due-course, endorsement, assignment or collection-agent cases.
- Joint accounts, joint drawers, guarantors or multiple proposed noticees.
- Multiple cheques, successive presentment, earlier notice or replacement
  cheque scenarios.
- Lost, materially altered, unsigned, stale, post-dated or foreign cheques.
- Unclear return reasons or cases not accepted by the reviewing advocate as
  falling within the supported statutory route.
- Security cheques, time-barred or disputed debts, part-payment, set-off,
  novation, accord, settlement or insolvency implications.
- Fraud, forgery, coercion, identity theft, police complaint or immediate
  safety concerns.
- Claims requiring interest, damages, legal charges or an omnibus amount unless
  an advocate separately approves the exact treatment.
- Notice already dispatched, limitation already uncertain, or any litigation
  already filed.

These exclusions are intentionally conservative. They may be expanded only
through a new reviewed product version, never through operator discretion.

## Timing controls

The system records dates and shows an **indicative review clock**. It does not
tell the customer that a statutory deadline is conclusively available.

| Event | Candidate control |
| --- | --- |
| Cheque date | Capture exact date from customer and evidence |
| Presentation | Compare with the applicable validity period; current RBI guidance uses three months |
| Bank return | Capture presentation date, memo date and exact return reason |
| Receipt of bank information | Capture the date the payee actually received dishonour information; do not silently substitute the memo date |
| Written notice | Flag the section 138 thirty-day period for advocate confirmation |
| Receipt by drawer | Record dispatch, delivery evidence and returned/unclaimed status separately |
| Drawer payment period | Show the statutory fifteen-day period only after advocate confirms the service event |
| Complaint follow-up | Refer to an advocate; section 142 timing and forum are outside automatic document delivery |

No weekend, holiday, service-presumption, condonation, successive-presentment
or cause-of-action rule is applied automatically in V1. Every displayed date
is labelled provisional until the assigned advocate confirms it.

## Evidence contract

The product cannot activate until a private, authenticated evidence workflow
exists. WhatsApp text alone is insufficient for an issued notice.

Minimum requested material:

1. Clear front copy of the cheque.
2. Bank return memo/advice containing the return reason and date.
3. Evidence supporting the stated debt or liability, such as a written
   agreement, invoice and delivery evidence, or relevant transaction record.
4. Payee and drawer service-address evidence requested by the advocate.
5. Evidence of any payment, adjustment or communication after cheque issue.

Controls:

- Never ask for PIN, password, OTP, CVV, internet-banking credentials or an
  unredacted full bank statement.
- Warn customers to redact unrelated account numbers, balances and
  transactions where the advocate does not require them.
- Treat OCR as a suggestion only. Customer and advocate must confirm cheque
  number, date, amount, bank, return reason and every address.
- Store evidence in a separate private S3 prefix with encryption, malware/file
  validation, strict size/type limits, short-lived access and access audit.
- Do not place evidence content, presigned URLs or financial identifiers in
  application logs, analytics or outbox payloads.
- Retention remains an activation blocker until the privacy owner and advocate
  approve matter-record obligations, deletion triggers and legal-hold handling.

## Commercial and payment contract

No payment link is created merely because the customer completes intake.

```text
INTAKE_SAVED
  -> EVIDENCE_PENDING
  -> ADVOCATE_TRIAGE
  -> ACCEPTED_AND_QUOTED
  -> CUSTOMER_CONFIRMS_SCOPE
  -> PAYMENT_PENDING
  -> PAID
  -> ADVOCATE_DRAFTING
  -> CUSTOMER_FACT_CHECK
  -> ADVOCATE_FINAL_APPROVAL
  -> ISSUED
  -> DISPATCH_RECORDED
```

Declined, unsupported, conflicted, expired or evidence-incomplete matters do
not become payable. The quote states what is included: one advocate review,
one notice, included correction rounds, dispatch responsibility, taxes,
refund conditions and turnaround. A signature is never advertised as “free”;
it records professional responsibility and is included only when the assigned
advocate has accepted that exact engagement.

## Issuance and signature contract

- Only an authenticated, active advocate assigned to the order may issue it.
- The advocate sees the confirmed facts, source/evidence checklist, exact
  rendered notice and all calculated warnings before approval.
- Approval binds advocate ID, enrolment reference, order, revision, artifact
  hash, template version, decision, time and conditions.
- NyaySetu never reuses a signature image or applies one automatically.
- If electronic signing is later supported, it must be a deliberate
  advocate-controlled signing event through an approved provider.
- Any customer fact or legal-text change after approval invalidates the
  approval and creates a new immutable revision.
- The issued artifact is a locked PDF. An editable DOCX is not delivered as an
  advocate-signed final because later edits would not be covered by approval.

## Dispatch and service contract

V1 uses **speed post with registration and proof of delivery**, subject to the
assigned advocate's current-law confirmation. Courier, hand delivery, email
or WhatsApp may be recorded only as advocate-approved additional methods.

The system stores privacy-minimised operational evidence:

- dispatch method and date;
- tracking/reference number;
- destination-address snapshot hash;
- delivery/return status and date;
- proof artifact reference and access audit; and
- operator/advocate who recorded the event.

The product never marks `SERVED` from a WhatsApp delivery tick or customer
assumption. Service consequences remain for advocate assessment.

## Customer outputs

Before payment:

- product scope, exclusions, indicative price and turnaround;
- confirmed factual summary;
- evidence checklist and missing-item status;
- assigned-advocate acceptance and quote; and
- cancellation/refund terms.

After advocate approval:

- immutable issued PDF;
- advocate identity and issue record appropriate to the engagement;
- payment receipt;
- dispatch responsibility and instructions; and
- plain-language next-step timeline marked as advocate-confirmed or pending.

The user-known-advocate DOCX handoff is a later, separately priced and
classified product. It must say “Draft for independent advocate review” and
must not carry a NyaySetu advocate identity, signature or issuance claim.

## Operational dependencies and blockers

- Authenticated advocate roster, authority scope, conflict check and order
  assignment.
- Advocate acceptance/decline, quote, SLA, revision and final-approval queue.
- Secure evidence and issued-artifact upload/download with access audit.
- No reusable signature store; safe per-order signing or signed-artifact
  ingestion.
- Dispatch and proof-of-delivery operating procedure.
- Privacy notice, processor inventory, retention, erasure and legal-hold rule.
- Product-specific Razorpay description, refund policy and reconciliation.
- Durable user/advocate/operator notifications or documented manual fallback.
- Exact English template, clause manifest, golden cases and advocate approval.
- Production suspension/redelivery/refund and paid-order continuity procedure.

Existing PostgreSQL, Razorpay reconciliation and private S3 can be reused, but
the current self-service workflow is not sufficient for advocate acceptance,
evidence review, issuance, signing or dispatch evidence.

## Go/no-go acceptance

- [ ] Every supported and excluded fact is approved by a practising advocate.
- [ ] Current statute, RBI direction, 2025 postal amendment and controlling
  Supreme Court decisions are checked as of the approval date.
- [ ] No software path makes a final eligibility, service or limitation
  conclusion without advocate confirmation.
- [ ] Incorrect cheque amount, date, number, bank, return reason or address
  fails closed before issuance.
- [ ] Payment is impossible before advocate acceptance and quote confirmation.
- [ ] Cross-user, cross-advocate and expired access is denied and audited.
- [ ] Every post-approval change invalidates the prior approval.
- [ ] Issued PDF hash matches the advocate-approved revision.
- [ ] Dispatch and service status cannot be inferred from chat delivery.
- [ ] Decline, refund, redraft, missed-SLA and urgent-expiry paths are tested.
- [ ] Native legal-language review exists for every enabled translation.
- [ ] Synthetic end-to-end UAT passes before any real customer is offered the
  product.
