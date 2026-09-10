# Questionnaire Contract: Maharashtra Residential Leave and Licence

**Active schema:** `mh-ll-questionnaire-2026-09-v3`

**Runtime rule:** exactly one questionnaire schema is active for every user.

This contract replaces the test-only 43-question prototype. No real customer
used that prototype, so there is no public compatibility or migration path.
Question codes, order, conditions, validations and derivations are hashed as
part of the release package.

## Data and navigation rules

- Collect no Aadhaar, PAN, bank account, signature image or identity-document
  upload.
- Normalize whitespace and preserve the customer-confirmed display values.
- Reject control characters, markup and values over field limits.
- Never infer an unknown legal fact. An ineligible scope answer routes to
  consultation without creating a payment entitlement.
- A conditional detail is not shown when its controlling answer is `NO`.
- Official postal data provides suggestions only. The customer types and
  confirms the complete property address.
- Show the exact parties, notice addresses, premises, dates and money terms in
  the final review.
- Present the journey as five sections, allow `Save & Exit` without deleting
  answers, and let review correction reopen only the selected section.

## A. Grouped eligibility

| Field code | Required confirmation | Effect |
| --- | --- | --- |
| `property_eligibility` | Maharashtra, completed/occupiable premises, private residential use | `YES` required |
| `party_eligibility` | One adult individual licensor and licensee, each acting personally | `YES` required |
| `authority_dispute_eligibility` | Licensor states authority; no material property/occupation dispute or conflicting claimant | `YES` required |
| `standard_product_terms` | Fixed 11-month/no-lock-in/notice/use/external-execution scope is suitable | `YES` required |

Any `NO` routes out with a reason code. The grouped wording is visible in full
and each answer remains in the immutable confirmed snapshot.

## B. Parties and addresses

| Field code | Meaning | Validation/condition |
| --- | --- | --- |
| `licensor_full_name` | Licensor legal name | 2-120 bounded characters |
| `licensor_age_years` | Licensor age | Integer 18-120; do not collect date of birth |
| `licensee_full_name` | Licensee legal name | 2-120 bounded characters |
| `licensee_age_years` | Licensee age | Integer 18-120 |
| `premises_pin` | Property PIN | Six digits |
| `premises_address_lines` | Complete customer-entered property description | Bounded text; postal hints are not copied as legal facts |
| `premises_address_confirmed` | Exact rendered address check | `CONFIRM` or return to address entry |
| `licensor_notice_address` | Licensor notice address | Complete bounded response |
| `licensee_address_same_as_premises` | Explicit reuse decision | `YES` copies the confirmed premises address |
| `licensee_notice_address` | Separate licensee notice address | Required only when the reuse decision is `NO` |

The renderer adds `Maharashtra` and the confirmed PIN when the customer did
not already include them. It does not infer a unit, building, road, locality,
taluka, ownership or authority.

## C. Dates and money

| Field code | Meaning | Validation/derivation |
| --- | --- | --- |
| `commencement_date` | Start date | Valid permitted date; normalized to ISO |
| `expiry_date` | End date | Derived as 11 months ending one day earlier |
| `monthly_licence_fee_inr` | Monthly fee | Whole INR, 1-100,000,000 |
| `fee_due_day` | Monthly due day | Integer 1-28 |
| `fee_payment_mode` | Contractual payment method | Bank transfer, UPI or account-payee cheque; no account data |
| `refundable_deposit_inr` | Refundable deposit | Whole INR, zero permitted |

The renderer displays money in digits and words. Fixed product allocations and
rules remain part of the reviewed product/template contract rather than
repeated customer questions.

## D. Optional details

The first control is `optional_details_mode`. `SKIP` bypasses every optional
property, occupant and inventory question in one response; `ADD` opens the
following conditional controls.

| Control field | Detail field | Behaviour |
| --- | --- | --- |
| `property_reference_present` | `premises_property_reference` | Ask exact CTS/survey/reference only after `YES`; otherwise derive `NONE` |
| `included_areas_present` | `included_areas` | Ask exact parking/storage/terrace identifiers only after `YES`; otherwise derive `NONE` |
| `other_occupants_present` | `permitted_occupant_names` | Up to five other names after `YES`; total count is licensee plus names |
| `inventory_present` | `inventory_items` | Up to 25 comma-separated items after `YES`; otherwise derive `NONE` |

These values identify what the parties describe; they do not verify title.

`furnishing` is not collected because the current candidate template does not
render or route on it.

## Typical path and confirmation evidence

The path with one licensee notice address reused from the premises and no
optional property/occupant/inventory details reaches review after 19 answers,
down from 43. Positive optional branches add only their relevant detail.

Confirmation records the consent/disclosure version, schema version,
normalized payload hash and time. The review states that the customer supplied
and checked the facts; identity, title and authority are not verified; the
output is not legal advice or advocate approval; and stamping, signing,
registration and statutory fees remain external.
