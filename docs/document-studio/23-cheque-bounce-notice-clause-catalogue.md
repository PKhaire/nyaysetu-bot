# Clause Catalogue: Single-Cheque Section 138 Demand Notice

**Package:** `in_ni138_single_cheque_individual_advocate_issued`  
**Version:** `in-ni138-single-cheque-en-2026-09-candidate-1`  
**Status:** private Phase D implementation baseline; never customer-visible
without the separate authenticated release and Phase E activation decisions

This catalogue records the exact purpose and data boundary of each candidate
clause. It is not a reusable notice and does not replace the assigned
advocate's matter-specific review and per-order approval.

## Narrow first-package decisions

- One individual named payee acting personally.
- One living adult individual drawer acting personally.
- One cheque, one presentation/return event and no earlier statutory notice.
- Personal-loan liability only for the standard package.
- Exact bank return reason `FUNDS INSUFFICIENT` only.
- Exact cheque amount is demanded; no automatic interest, damages, costs or
  professional charges.
- Customer receives only a factual summary before payment.
- Matter-specific price follows advocate acceptance; no fixed catalogue price.
- Final customer artifact is a locked advocate-issued PDF; no editable DOCX.
- Signing is a deliberate per-order advocate event. No reusable signature
  image is stored or applied.

Every other liability category, return reason, party form, multiple-instrument
case, part-payment, settlement, replacement cheque, earlier notice, existing
proceeding or uncertain fact routes out before standard drafting and payment.

## Clause register

| ID | Purpose | Runtime fields | Mandatory control |
| --- | --- | --- | --- |
| `CB-CL-01` | Identify the document as an advocate-controlled legal demand notice | `notice_date` | Date supplied through advocate context; never inferred from memo or intake completion |
| `CB-CL-02` | State the approved dispatch baseline | none | Does not assert dispatch or service; actual dispatch is a separate immutable event |
| `CB-CL-03` | Identify the one noticee and primary service address | `drawer_full_name`, `drawer_service_address` | Customer-confirmed data and advocate evidence review required |
| `CB-CL-04` | Identify client instructions and address | `payee_full_name`, `payee_notice_address` | Must not imply that software or an operator is the advocate |
| `CB-CL-05` | Recite the stated personal-loan facts neutrally | `liability_summary`, `liability_due_date` | Bounded factual text; accusation terms route out and are never inserted automatically |
| `CB-CL-06` | Record exact cheque particulars | `cheque_number`, `cheque_date`, `cheque_amount_inr`, `cheque_amount_words`, `drawer_bank_name`, `drawer_bank_branch`, `payee_name_on_cheque` | Amount is independently confirmed twice and must match before rendering |
| `CB-CL-07` | Record presentation and bank return facts | `presented_on`, `return_memo_date`, `dishonour_information_received_on`, `return_reason_exact` | Dates remain separate; exact return reason is not paraphrased |
| `CB-CL-08` | Make the exact cheque-amount demand | `cheque_amount_inr`, `cheque_amount_words` | Same normalized amount as `CB-CL-06`; no additional amount is calculated |
| `CB-CL-09` | State the payment period and possible legal follow-up | none | Assigned advocate confirms wording and timing; no outcome or maintainability guarantee |
| `CB-CL-10` | Reserve other lawful rights without an omnibus monetary demand | none | Does not add or quantify another claim |
| `CB-CL-11` | Bind issue responsibility to the assigned advocate | `advocate_practice_name`, `advocate_full_name`, `advocate_enrolment_ref`, `advocate_service_address` | Advocate-controlled context and exact signed-PDF ingestion only |

## Prohibited branches

The renderer contains no optional branch for fraud, cheating, criminal intent,
director/officer liability, guarantors, interest, damages, costs, multiple
cheques, successive presentation, service presumptions or complaint timing.
Such material cannot be inserted through customer free text or configuration.
Adding one requires a new template/schema/package hash and authenticated
advocate approval.

## Artifact contract

The package gate binds these deterministic synthetic review artifacts:

1. `FACTUAL_SUMMARY_PDF` — customer-confirmed facts and explicit statement that
   legal eligibility, deadline, service and remedy have not been decided.
2. `NOTICE_REVIEW_PDF` — exact candidate notice prose rendered with synthetic
   advocate-review context solely for package authentication.

The second artifact is not a live issued notice. A real order becomes issued
only after the Phase C workflow records the assigned advocate, exact intake
revision, customer fact confirmation, clean PDF scan, advocate-controlled
signed upload and immutable per-order artifact hash.

## Invalidating changes

Any change to this catalogue, candidate template, questionnaire prompts,
supported category/reason, renderer, token set, factual-summary wording or
golden scenario creates a different aggregate or artifact hash and therefore
requires a new release decision.
