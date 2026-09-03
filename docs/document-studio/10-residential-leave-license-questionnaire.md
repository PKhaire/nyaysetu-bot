# Questionnaire Contract: Maharashtra Residential Leave and Licence

This is the stable intake contract for advocate and engineering review. Field
codes, types, conditions and clause mappings are versioned.

## Data rules

- Collect no Aadhaar, PAN, bank account, signature image or identity-document
  upload in V1.
- Normalize whitespace/Unicode and preserve confirmed display values.
- Reject control characters, markup and values over field limits.
- Never infer an unknown legal fact; uncertainty routes to consultation.
- Show a grouped final summary and require explicit confirmation.

## A. Eligibility

| Field code | Meaning | Validation/effect |
| --- | --- | --- |
| `property_state` | Property state | Must be `MAHARASHTRA`; EL-01 |
| `premises_use` | Intended use | Must be `RESIDENTIAL`; EL-02 |
| `party_structure` | Party count/type | One individual each; EL-03 |
| `parties_adult_competent` | Both adults able to understand/agree | Explicit yes; EL-04/11 |
| `self_represented_parties` | Both act for themselves | Explicit yes; EL-05 |
| `licensor_authority_confirmed` | Licensor confirms authority | Yes required; EL-06 |
| `existing_dispute` | Title/possession/tenancy/eviction dispute | No required; EL-07 |
| `conflicting_occupant` | Conflicting occupant exists | No required; EL-08 |
| `term_months` | Duration | Fixed `11`, confirmed; EL-09 |
| `standard_terms_accepted` | No custom clauses | Explicit yes; EL-12 |
| `external_steps_understood` | Execution/fees/registration external | Explicit yes; EL-14 |

Failures produce a reason-coded route, not a legal conclusion.

## B. Parties

| Field code | Meaning | Validation |
| --- | --- | --- |
| `licensor_full_name` | Legal full name for draft | 2-120 chars, bounded punctuation |
| `licensor_age_years` | Age | Integer 18-120; not date of birth |
| `licensor_notice_address` | Notice address | Structured; max 500 rendered chars |
| `licensee_full_name` | Legal full name for draft | Same controls |
| `licensee_age_years` | Age | Integer 18-120 |
| `licensee_notice_address` | Notice address | Structured; max 500 rendered chars |

The summary warns that identity is not verified and names must be checked
against documents used for execution/registration.

## C. Premises

| Field code | Meaning | Validation |
| --- | --- | --- |
| `premises_unit` | Flat/house/unit | Required, max 80 |
| `premises_building` | Building/society | Optional, max 120 |
| `premises_floor` | Floor | Optional, max 30 |
| `premises_street_area` | Street/locality | Required, max 160 |
| `premises_city` | City/town/village | Required, max 100 |
| `premises_taluka` | Taluka | Required, max 100 |
| `premises_district` | District | Controlled Maharashtra district list |
| `premises_pin` | PIN | Six digits |
| `premises_property_reference` | CTS/survey reference if known | Optional bounded text; no title inference |
| `included_areas` | Parking/terrace/store | Controlled options and bounded identifiers |

Unknown or disputed property identity routes out.

## D. Dates and money

| Field code | Meaning | Validation/derivation |
| --- | --- | --- |
| `commencement_date` | Start date | Valid date; IST presentation |
| `expiry_date` | End date | Derived for 11 months ending one day earlier; display/confirm |
| `monthly_licence_fee_inr` | Monthly fee | Positive bounded integer INR |
| `fee_due_day` | Monthly due day | 1-28 |
| `fee_payment_mode` | Payment method | `BANK_TRANSFER`, `UPI` or `ACCOUNT_PAYEE_CHEQUE`; no account data |
| `refundable_deposit_inr` | Refundable deposit | Integer INR; zero allowed |
| `deposit_refund_days` | Target return timing | Fixed seven business days; not customer-editable |
| `non_refundable_consideration_inr` | Non-refundable premium | Must be zero in V1; otherwise route out |
| `maintenance_payer` | Property tax/society maintenance | Fixed `LICENSOR`; another allocation routes out |
| `utilities_payer` | Metered consumption utilities | Fixed `LICENSEE`; shared/unusual allocation routes out |

Display amounts in words and digits. Any stamp-duty figure is informational
and requires current official calculation/disclaimer.

## E. Occupation and standard terms

| Field code | Meaning | Validation |
| --- | --- | --- |
| `permitted_occupant_count` | Total resident count including licensee | Integer 1-6 |
| `permitted_occupant_names` | Other occupants | Optional names; no IDs; bounded |
| `furnishing_level` | Furnishing | Controlled enum |
| `inventory_summary` | Short inventory schedule | Optional, maximum 25 bounded lines; no upload |
| `notice_period_days` | Ordinary termination notice | Fixed 30 calendar days |
| `inspection_notice_hours` | Prior inspection notice | Fixed 24 hours, subject to genuine emergency |
| `no_lock_in_ack` | No lock-in or minimum stay | Explicit yes |
| `possession_condition_ack` | Vacant possession/condition understood | Yes |
| `no_transfer_ack` | No assignment/sub-licensing | Yes |
| `lawful_residential_use_ack` | Lawful residential use | Yes |

The seven-day curable-breach period, no-automatic-renewal rule, no-self-help
rule and selected cost/repair allocation are system terms rather than customer
inputs. Any requested variation routes to consultation. See the
[V1 Legal-Drafting Decision Record](15-v1-legal-drafting-decision-record.md).

## Confirmation evidence

Record consent/disclosure versions, schema version, normalized payload hash and
confirmation time. State that the customer supplied/checked facts; identity,
title and authority were not verified; output is not advice/advocate approval;
execution/fees/registration remain external; and changing an answer creates a
new revision that invalidates the prior preview.
