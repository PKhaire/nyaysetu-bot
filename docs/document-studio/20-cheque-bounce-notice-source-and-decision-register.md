# Source and Legal-Decision Register: Section 138 Demand Notice

**Status:** source baseline revalidated for private Phase D implementation on
11 September 2026; authenticated exact-package approval remains a runtime gate  
**Retrieved/checked:** 10 September 2026  
**Product:** `in_ni138_single_cheque_individual_advocate_issued`

This register is not legal advice and does not approve a template. The
assigned legal owner must check the current statute, amendments, binding
precedent, local practice and facts before activating a version and before
issuing each notice.

## Source status labels

- `AUTHORITATIVE_TEXT`: legislation or direction published by an official
  authority.
- `BINDING_PRIMARY_DECISION`: judgment published by the Supreme Court of
  India; the advocate must decide its application and continuing authority.
- `OFFICIAL_GUIDANCE`: current official operational guidance that may change.
- `ADVOCATE_DECISION_REQUIRED`: software must not turn the source into a final
  legal conclusion.
- `PROVIDER_CONTRACT`: platform behaviour requiring current integration tests.

## Primary source register

| ID | Source | Status | Product implication | Required approval action |
| --- | --- | --- | --- | --- |
| CB-SRC-NI-138 | [Negotiable Instruments Act, 1881](https://www.indiacode.nic.in/bitstream/123456789/2189/1/a1881-26.pdf), section 138 | `AUTHORITATIVE_TEXT` | Controls stated liability, presentment, written demand, thirty-day notice period and fifteen-day payment period. | Verify current text and approve every eligibility, timing and demand control. |
| CB-SRC-NI-139 | Same Act, section 139 | `AUTHORITATIVE_TEXT` and `ADVOCATE_DECISION_REQUIRED` | Statutory presumption does not permit the product to declare that the customer's debt is proved. | Approve neutral recital and prevent outcome claims. |
| CB-SRC-NI-141 | Same Act, section 141 | `AUTHORITATIVE_TEXT` | Company/officer liability is fact-sensitive and excluded from the first product. | Confirm route-out wording and future separate product boundary. |
| CB-SRC-NI-142 | Same Act, section 142 and 142A | `AUTHORITATIVE_TEXT` and `ADVOCATE_DECISION_REQUIRED` | Complainant status, filing time and territorial jurisdiction are outside automatic document issuance. | Approve follow-up language; no automatic filing deadline. |
| CB-SRC-NI-146 | Same Act, section 146 | `AUTHORITATIVE_TEXT` | Bank slip/memo has evidentiary relevance but the product must still validate and expose it to the advocate. | Define acceptable evidence and mismatch handling. |
| CB-SRC-RBI-VALIDITY | [RBI circular DBOD.AML BC.No.47/14.01.001/2011-12](https://www.rbi.org.in/commonman/Upload/English/Notification/PDFs/CVC041111.pdf) | `OFFICIAL_GUIDANCE` | Banks were directed not to pay cheques presented beyond three months for instruments dated on/after 1 April 2012. | Recheck current RBI direction at approval and avoid relying only on the Act's six-month wording. |
| CB-SRC-KAVERI-2025 | [Kaveri Plastics v. Mahdoom Bawa Bahrudeen Noorul, 2025 INSC 1133](https://api.sci.gov.in/supremecourt/2024/24253/24253_2024_1_1501_64452_Judgement_19-Sep-2025.pdf) | `BINDING_PRIMARY_DECISION` | The statutory demand must state the exact cheque amount; even a claimed typographical mismatch was treated as fatal. Separately identified additional claims require advocate control. | Require dual amount confirmation and exact artifact check; prohibit omnibus auto-calculation. |
| CB-SRC-SUMAN-SETHI | [Suman Sethi v. Ajay K. Churiwal](https://api.sci.gov.in/jonew/judis/20274.pdf) | `BINDING_PRIMARY_DECISION` | Notice is read as a whole, but a specific cheque-amount demand remains central; treatment of additional claims depends on drafting. | Default to exact cheque amount only in V1 unless the advocate approves a separated additional claim. |
| CB-SRC-YOGENDRA | [Yogendra Pratap Singh v. Savitri Pandey](https://api.sci.gov.in/jonew/judis/41940.pdf) | `BINDING_PRIMARY_DECISION` | A complaint filed before expiry of the statutory fifteen-day period was addressed as premature. | Do not automate complaint readiness; record service and obtain advocate confirmation. |
| CB-SRC-ALAVI | [C.C. Alavi Haji v. Palapetty Muhammed](https://api.sci.gov.in/jonew/judis/29085.pdf) | `BINDING_PRIMARY_DECISION` and `ADVOCATE_DECISION_REQUIRED` | Service, correct address, dispatch and avoidance involve legal presumptions and facts. | Preserve dispatch/delivery evidence; never mark service from WhatsApp delivery. |
| CB-SRC-MSR | [MSR Leathers v. S. Palaniappan](https://api.sci.gov.in/jonew/judis/40759.pdf) | `BINDING_PRIMARY_DECISION` | Successive presentation/dishonour can change analysis. | Exclude all successive-presentment cases from the first product. |
| CB-SRC-PART-PAYMENT | [Dashrathbhai Trikambhai Patel v. Hitesh Mahendrabhai Patel](https://api.sci.gov.in/supremecourt/2022/12508/12508_2022_2_1501_38899_Judgement_11-Oct-2022.pdf) | `BINDING_PRIMARY_DECISION` and `ADVOCATE_DECISION_REQUIRED` | Part-payment or altered enforceable liability before presentment can affect section 138 treatment and the cheque amount. | Route every part-payment, settlement or adjustment case out of V1. |
| CB-SRC-GCA | [General Clauses Act, 1897](https://www.indiacode.nic.in/bitstream/123456789/2328/1/189710.pdf), sections 9, 10 and 27 | `AUTHORITATIVE_TEXT` and `ADVOCATE_DECISION_REQUIRED` | Time computation and postal presumptions cannot be reduced to a simple customer-facing countdown. | Approve any calculation rule and service language; V1 shows only warnings. |
| CB-SRC-RAA-2025 | [Repealing and Amending Act, 2025](https://www.indiacode.nic.in/bitstream/123456789/22046/1/a2025-37.pdf), Second Schedule | `AUTHORITATIVE_TEXT` | Section 27 terminology changed from registered post to speed post with registration; related CPC language uses proof of delivery. | Remove outdated registered-AD boilerplate and approve dispatch instructions against current practice. |
| CB-SRC-ADVOCATES | [Advocates Act, 1961](https://www.indiacode.nic.in/bitstream/123456789/1631/1/A1961_25.pdf), sections 29-35 | `AUTHORITATIVE_TEXT` | NyaySetu must not present software or an operator as the practising advocate. | Require a properly enrolled, authenticated advocate for acceptance and issuance. |
| CB-SRC-IT | [Information Technology Act, 2000](https://www.indiacode.nic.in/bitstream/123456789/13116/1/it_act_2000_updated.pdf), sections 3, 3A and 5 | `AUTHORITATIVE_TEXT` | A pasted signature image is not an adequate electronic-signature control. | If enabled later, approve a signatory-controlled compliant method and provider evidence. |
| CB-SRC-DPDP | [Digital Personal Data Protection Act, 2023](https://www.indiacode.nic.in/bitstream/123456789/22037/2/a2023-22.pdf) | `AUTHORITATIVE_TEXT` | Cheque, debt and address evidence requires clear purpose, access, correction, security and deletion controls. | Privacy owner maps provisions in force, notice, processors, rights and incident handling. |
| CB-SRC-DPDP-RULES | [Digital Personal Data Protection Rules, 2025](https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?hl=en-US) | `AUTHORITATIVE_TEXT` with phased commencement | Release review must account for rules then in force and scheduled commencement, not the earlier research snapshot. | Record effective provisions at candidate approval and next-review date. |

## Candidate legal decisions

These are conservative product recommendations. A licensed advocate must mark
each `ACCEPT`, `CHANGE` or `REJECT` and provide reasons.

| Decision | Candidate recommendation | Advocate outcome |
| --- | --- | --- |
| Product classification | Advocate-Issued Notice; never self-service | |
| Parties | One individual named payee and one individual drawer only | |
| Instrument | One cheque, one presentation/return event, no prior notice | |
| Liability | Personal-loan statement only in the standard package; advocate verifies evidence and sufficiency | Revalidated Phase D baseline |
| Validity | Check current three-month RBI direction plus instrument facts | |
| Notice clock | Record receipt-of-bank-information date separately; advocate confirms section 138(b) treatment | |
| Demand amount | Exact cheque amount, confirmed twice and matched to evidence; no automatic interest/cost/damages | |
| Part payment/adjustment | Route out without payment | |
| Return reason | Exact `FUNDS INSUFFICIENT` only; every other reason routes | Revalidated Phase D baseline |
| Company/firm drawer | Route out to a future section 141 product | |
| Successive presentment/prior notice | Route out | |
| Service | Speed post with registration and proof of delivery as baseline, subject to current advocate confirmation | |
| Electronic/courtesy delivery | May supplement but does not automatically establish service | |
| Fifteen-day period | Display only after advocate reviews the service event | |
| Complaint timing/forum | Outside this document product; offer separate advocate follow-up | |
| Customer preview | Facts and scope only; no issuable statutory text before payment | |
| Signature | Per-order advocate-controlled signing; never reusable auto-application | |
| Final format | Locked PDF; no editable signed DOCX | |
| User's own advocate | Separate later product labelled Draft for Independent Advocate Review | |
| Retention | Remains blocked pending professional-record/privacy/legal-hold decision | |

## Non-automatable decision register

The following must remain explicit advocate decisions in the first release:

- whether the customer is the legally proper notice sender;
- whether a legally enforceable debt or liability existed for the cheque;
- whether the cheque and return reason fall within section 138 as currently
  interpreted;
- whether presentment, notice and service facts are timely and sufficient;
- whether part-payment, settlement, limitation, security or insolvency changes
  the position;
- whom to address and whether another person/entity must be included;
- the exact demand and any additional severable claim;
- the approved dispatch method and address;
- whether to sign and issue the final notice; and
- any complaint, forum, condonation or follow-up advice.

The software may validate formatting, compare exact repeated values, show
date-risk warnings and preserve evidence. It must not label these legal
decisions as deterministic calculations.

## Mandatory source-monitoring events

Suspend new sales and require impact review when any of the following occurs:

- amendment to sections 138-148 of the Negotiable Instruments Act;
- RBI change to cheque validity, return practice or cheque clearing;
- Supreme Court decision affecting demand amount, debt, presentment, service,
  limitation, company liability or forum;
- change to postal-service law or India Post product terminology;
- change to advocate practice/authentication requirements;
- commencement or amendment of relevant DPDP provisions; or
- failure of the approved evidence, signing, dispatch or payment provider.

The source owner performs a documented check before every new package and at
least every three months while this time-sensitive product is active. A source
change never silently modifies an accepted, paid or issued order.

## Phase D decisions; recheck before activation and every issue

- The first standard package accepts only the exact recorded reason `FUNDS
  INSUFFICIENT`; every other reason routes without standard-product payment.
- India is the product jurisdiction, but an order cannot be assigned unless
  the verified advocate's immutable authority scope includes the product.
- Personal-loan support is mandatory and remains for matter-specific advocate
  sufficiency review; software does not approve the debt.
- The notice demands the exact cheque amount only. No interest, damages, costs
  or professional charges are calculated or added.
- Advocate responsibility is proved by named MFA identity, assignment,
  conflict/matter decision, exact revision/hash and per-order offline-signed
  PDF ingestion. Reusable signature images are prohibited.
- Speed post with registration and proof of delivery is the baseline record.
  Returned, refused, unclaimed or additional-method consequences remain an
  advocate decision.
- Existing bounded retention, paid-evidence preservation and legal-hold rules
  apply pending the final Phase E privacy/operations sign-off.
- Reported payment or settlement after intake suspends standard drafting or
  dispatch and returns the matter to the assigned advocate; no automatic legal
  consequence is recorded.

These decisions permit private implementation and synthetic artifact review.
They do not permit customer visibility, payment collection or issue until the
exact deployed hashes and dependencies receive authenticated approval.
