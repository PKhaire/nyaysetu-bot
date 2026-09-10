# V2 Intake and Booking UX Reduction Plan

Status: **RC14 UX replacement candidate implemented; not approved or activated**.

Release fact: V1 has been used only for staging/UAT with synthetic test data.
No real customer has used V1, no production customer entitlement depends on
it, and V1 does not require a customer migration or public compatibility
period. Evidence from testing may be retained separately where operationally
useful, but test orders and artifacts are not customer records.

This document defines a shorter, safer customer journey for the Maharashtra
Residential Leave and Licence product and the paid-consultation booking flow.
It is the implementation and advocate-review baseline for the replacement.
The current code contains only this questionnaire schema, but payment remains
release-gated until an advocate approves its new aggregate hash. Existing test
artifacts and payments are not treated as customer entitlements.

## 1. Decision summary

1. Replace the fixed 43-question Draft Studio journey with a progressive,
   typical 19-answer journey organised into five sections.
2. Preserve every material eligibility fact, agreement variable, safety route,
   customer confirmation and external-execution disclosure.
3. Stop asking customers to re-enter fixed product rules or type `NONE` for
   optional facts.
4. Collect a complete property address through PIN-assisted suggestions plus
   customer-entered address lines and an exact final confirmation.
5. Never treat GPS coordinates, a third-party geocoder or an inferred address
   as the legal property description.
6. Show appointment availability earlier. Collect a minimal, consented matter
   summary before payment and offer the detailed advocate-preparation brief
   after payment without withholding a paid appointment.
7. Add progress, resume, section-specific edit and explicit `Skip` controls.
8. Expose exactly one active questionnaire schema to all users. Replace the
   test-only V1 schema with the approved simplified schema before real-user
   testing; do not build public V1 migration or compatibility machinery.

## 2. Goals and non-goals

### Goals

- Reduce abandonment and typing effort without weakening legal boundaries.
- Make every collected value visible in the draft, operational routing or an
  explicit safety/compliance control.
- Make optional questions conditional.
- Let customers correct one section without restarting the full journey.
- Improve the quality of the address and advocate-handover summary.
- Avoid new paid runtime dependencies for address entry.

### Non-goals

- No identity, title, authority or property-record verification.
- No Aadhaar, PAN, bank credential, signature or evidence-file collection.
- No address inference from a WhatsApp location pin.
- No generative drafting or AI-authored clauses.
- No change to the fixed V1 commercial/legal terms without advocate review.
- No automatic advocate assignment or outbound-template dependency.

## 3. Design rules

- **Ask for facts, disclose rules:** a fixed product rule is displayed and
  accepted as part of a grouped scope/terms confirmation; it is not presented
  as a customer-editable fact.
- **Progressive disclosure:** an optional detail opens only after a positive
  answer, such as parking, other occupants or inventory.
- **No silent inference:** official PIN data may suggest postal metadata, but
  the customer must select or confirm it. Unknown or disputed facts route to
  correction or consultation.
- **Exact review:** the confirmation screen shows the complete party names,
  notice addresses, property address, dates and money terms that will appear
  in the draft.
- **Deterministic implementation:** no AI is required to parse eligibility,
  money, dates or addresses. Free text is normalized and bounded, then shown
  back verbatim for confirmation.
- **Privacy minimisation:** no full address or matter narrative is sent to a
  third-party mapping or classification provider.
- **Version integrity:** question order, validations, derivations, template
  tokens, disclosures and hashes are versioned and approved together.

## 4. V1-to-V2 Draft Studio question mapping

The following mapping covers all 43 V1 questions in their current order.

| # | V1 field | V2 decision | V2 handling and reason |
|---:|---|---|---|
| 1 | `property_state` | Combine | `Property eligibility`: property is in Maharashtra. Preserve as an explicit customer fact. |
| 2 | `premises_use` | Combine | Same property screen: private residential use only. |
| 3 | `completed_premises` | Combine | Same property screen: completed and ready for occupation. |
| 4 | `party_structure` | Combine | `Party eligibility`: exactly one individual licensor and one individual licensee. |
| 5 | `parties_adult_competent` | Combine | Same party screen: both are adults able to understand and agree. |
| 6 | `self_represented_parties` | Combine | Same party screen: each acts personally, not through a company, trust, agent or representative. |
| 7 | `licensor_authority_confirmed` | Combine | `Authority and dispute check`: licensor confirms authority. Preserve route-out on uncertainty. |
| 8 | `existing_dispute` | Combine | Same screen: no ownership, possession, tenancy, licence or eviction dispute. |
| 9 | `conflicting_occupant` | Combine | Same screen: no conflicting occupant or claimant. |
| 10 | `term_months` | Remove as input | Display fixed 11-month scope and derive the expiry date. Do not ask the customer to type `11`. |
| 11 | `standard_terms_accepted` | Combine | `Standard product terms` screen. One acceptance covers the visible fixed terms. |
| 12 | `non_refundable_zero` | Remove as input | Display INR 0 as a fixed V2 condition. A customer wanting a premium is routed to consultation. |
| 13 | `external_steps_understood` | Combine | Preserve in the final scope/execution acknowledgement: stamping, signing and registration remain external. |
| 14 | `facts_uncontested` | Combine | Preserve in final fact confirmation: facts are customer-confirmed and not verified by NyaySetu. |
| 15 | `licensor_full_name` | Keep | Required legal name; validate and show in final review. |
| 16 | `licensor_age_years` | Keep | Required template fact and adult range check. |
| 17 | `licensor_notice_address` | Redesign | One bounded multi-line address response followed by exact confirmation. Never infer it from the premises. |
| 18 | `licensee_full_name` | Keep | Required legal name; validate and show in final review. |
| 19 | `licensee_age_years` | Keep | Required template fact and adult range check. |
| 20 | `licensee_notice_address` | Conditional | Ask `Same as licensed premises?`; copy only after explicit `Yes`. Otherwise collect and confirm a separate address. |
| 21 | `premises_unit` | Combine | Collect with building/floor/road as bounded premises address lines. |
| 22 | `premises_building` | Combine | Optional component inside the premises address response; no `NONE` reply. |
| 23 | `premises_floor` | Combine | Optional component inside the premises address response; no separate question. |
| 24 | `premises_street_locality` | Combine | Collect as part of the premises address response, assisted by the selected postal locality. |
| 25 | `premises_city` | PIN-assisted | Suggest from official postal data; customer selects/confirms and may correct it. |
| 26 | `premises_taluka` | Conditional/editable | Include in the address prompt when known. Do not infer it from a PIN where the official source is not unambiguous. Advocate review decides whether it remains mandatory. |
| 27 | `premises_district` | PIN-assisted | Suggest the Maharashtra district from official postal data and require confirmation. |
| 28 | `premises_pin` | Keep and move first | Validate six digits, then load matching Maharashtra postal choices. |
| 29 | `premises_property_reference` | Conditional | Ask `Add CTS/survey/property reference?`; collect only after `Yes`. Never imply title verification. |
| 30 | `included_areas` | Conditional | Ask `Include identified parking/store/terrace?`; collect exact identifiers only after `Yes`. |
| 31 | `commencement_date` | Keep | Required; derive and display the 11-month expiry date for confirmation. |
| 32 | `monthly_licence_fee_inr` | Keep | Required bounded whole-rupee value; render digits and words. |
| 33 | `fee_due_day` | Keep | Required contractual payment term, day 1-28. |
| 34 | `fee_payment_mode` | Keep | Controlled selection; never collect bank credentials. |
| 35 | `refundable_deposit_inr` | Keep | Required bounded value; zero remains permitted. |
| 36 | `occupant_count` | Derive | Ask whether anyone besides the licensee will occupy. Derive total from confirmed names and enforce the six-person product limit. |
| 37 | `permitted_occupant_names` | Conditional | Collect only after `Other occupants: Yes`; otherwise store `NONE`. |
| 38 | `furnishing` | Remove | V1 collects this value but the approved candidate template does not render or otherwise use it. Inventory remains the meaningful fact. |
| 39 | `inventory_items` | Conditional | Ask `Add an inventory schedule?`; collect up to 25 bounded items only after `Yes`. |
| 40 | `no_lock_in_ack` | Combine | Display in `Standard product terms`; do not ask again near the end. |
| 41 | `possession_process_ack` | Combine | Display in the same terms screen and final review. |
| 42 | `no_transfer_ack` | Combine | Display in the same terms screen and final review. |
| 43 | `lawful_use_ack` | Combine | Display in the same terms screen and final review. |

### Fields removed versus preserved

Only `furnishing` is removed because it has no current output, routing or
operational effect. Fixed values and repeated acknowledgements are removed as
separate questions but remain visible, versioned product terms. Eligibility
facts remain auditable even when grouped.

## 5. Proposed V2 customer journey

The exact WhatsApp text remains subject to language and advocate review.

### A. Scope and eligibility

1. Product, price, output classification and external-step summary.
2. Property eligibility confirmation.
3. Party eligibility confirmation.
4. Authority/no-dispute confirmation.
5. Standard fixed-term confirmation.

A negative or uncertain response stops ordinary generation, releases reserved
capacity and offers consultation. The route-out message states the unsupported
fact without presenting a legal conclusion.

### B. Parties

6. Licensor full legal name.
7. Licensor age.
8. Licensee full legal name.
9. Licensee age.

### C. Licensed premises and notice addresses

10. Six-digit property PIN.
11. Bounded district/taluka/post-office suggestions from the local postal
    reference, with a safe manual fallback.
12. Customer-entered premises address lines: unit/flat, building/society, floor if applicable,
    road/locality and taluka if known.
13. Complete rendered premises-address confirmation.
14. Licensor notice address.
15. Licensee notice address: `Same as premises` or a separate address.
16. Optional property reference branch.
17. Optional specifically included area/parking branch.

### D. Dates and money

18. Commencement date and derived-expiry confirmation.
19. Monthly licence fee.
20. Monthly due day.
21. Payment mode.
22. Refundable deposit.

### E. Conditional occupation details

23. Other permitted occupants: no, or bounded names.
24. Inventory schedule: no, or bounded items.

### F. Exact review

25. Grouped full-fact review, fixed-term summary, limitations, external steps
    and explicit confirmation.

The implemented no-optionals path uses 19 answers before final confirmation.
One `Skip optional details` answer bypasses all property-reference,
included-area, additional-occupant and inventory branches. Positive optional
branches add only their associated details. The interaction count remains an
observed UAT measure, not a target that overrides correctness.

## 6. Address design

### 6.1 Data source

Use a versioned, locally cached Maharashtra subset of the Department of Posts
`All India Pincode Directory` published by the Government of India Open Data
Platform:

<https://www.data.gov.in/catalog/all-india-pincode-directory-through-webservice>

Retain only the fields required to suggest PIN, office/locality, district and
state. Record the upstream update date and local file hash. Refresh through a
reviewed maintenance process; do not make document creation depend on the
availability of the external site.

### 6.2 Privacy and correctness

- Query the local reference data by PIN; do not send the customer address to a
  mapping provider.
- A PIN may return multiple post offices. Present bounded choices and require
  customer selection.
- Treat district/state as suggestions until confirmed.
- Do not derive flat/unit, building, street, title reference or authority.
- Do not assume taluka solely from PIN when multiple administrative areas are
  possible.
- Preserve the normalized confirmed value and a separately rendered value.
- Reject control characters, markup and values exceeding field limits.
- Show the exact complete property and notice addresses in the final review.

### 6.3 WhatsApp location messages

A location pin may be evaluated later as an optional convenience for directions
or consultation coordination. It is not a V2 dependency and never replaces the
confirmed postal/property description. Coordinates must not be retained unless
a separately approved purpose and retention rule exist.

## 7. Consultation-booking V2

### 7.1 Principle

Let a customer see real appointment availability before completing a long
advocate-preparation questionnaire. Preserve minimum routing and safety facts
before payment, then enrich the paid booking through a resumable preparation
flow.

### 7.2 Before payment: required minimum

1. Show consultation scope, configured price and manual coordination model.
2. Confirm saved name and district/state, with an edit option.
3. Select legal category; always provide `Not sure`.
4. Select a subcategory only when it materially improves routing; otherwise
   make it optional or retain `General/Not sure`.
5. Collect a bounded short description of what happened.
6. Triage urgency:
   - routine;
   - known hearing/notice/limitation or other deadline; or
   - immediate safety concern.
7. If a deadline is selected, collect the exact known date or `Unknown`.
8. If immediate safety is selected, display the emergency limitation and
   capture the existing bounded safety note before continuing.
9. Show available dates and time slots.
10. Show one final booking/price/policy review and create a payment link only
    after explicit `Pay now`.

The short description, category and urgency are sufficient for initial
operations routing. The customer explicitly consents to sharing the supplied
booking brief with the assigned advocate for the booked service.

### 7.3 After payment: advocate preparation

After payment confirmation, offer `Prepare for your advocate` with:

- important dates and chronology;
- desired outcome;
- opposing/other party, with `Skip`;
- available document types, with `None`;
- up to three questions the customer wants answered.

Preparation is strongly recommended and resumable, but an incomplete brief
does not revoke, hide or delay the customer's paid appointment entitlement.
The operations desk displays `BRIEF_INCOMPLETE` until the customer confirms the
preparation section. An operator may complete coordination manually.

### 7.4 Booking V1-to-V2 mapping

| Existing step | V2 decision |
|---|---|
| Scope and fee | Keep, shorten and show manual coordination expectation. |
| Name and district | Reuse confirmed profile; ask again only when missing or edited. |
| Category | Keep with `Not sure`. |
| Subcategory | Conditional/optional; never trap the customer in taxonomy. |
| Issue summary | Keep before availability. |
| Legal stage | Move to post-payment preparation unless needed to clarify a deadline. |
| Important dates | Convert to deadline triage before payment; detailed chronology after payment. |
| Desired outcome | Move to post-payment preparation. |
| Urgency | Keep before availability. |
| Safety note | Keep as a conditional pre-payment safety route. |
| Document types | Move to post-payment preparation; replace numeric-only instructions with clearer staged controls. |
| Opposing party | Move to post-payment preparation and provide `Skip`. |
| Full brief review/consent | Split into minimum booking consent before payment and enriched-brief confirmation after payment. |
| Date and slot | Keep and show earlier. |
| Booking/payment review | Keep exact price and policy binding. |

## 8. Shared interaction improvements

- Display `Section X of 5` so progress remains truthful when optional branches
  change the number of individual answers.
- Keep `Save & Exit`, `Continue Draft` and typed cancellation semantics
  consistent. Saving never cancels or redacts the draft.
- Resume at the first unanswered step, not at the start.
- Review and edit by section: Eligibility, Parties, Property & addresses,
  Dates & money, and Optional details.
- `Edit` opens a section picker and invalidates only dependent derived values.
- Changing a confirmed value invalidates the preview and payment request.
- Never accept a stale button answer for a different question/revision.
- Use stable reason codes for validation, route-out, cancellation and resume.
- Record privacy-safe funnel events by step code only; never copy names,
  addresses, narratives or other answers into analytics/logs.

## 9. Single-schema replacement contract

There is exactly one active Draft Studio questionnaire schema at runtime.
Because V1 contains only synthetic staging/UAT data, the replacement is a
clean pre-production cutover rather than a customer migration. The replacement
still requires new identifiers because its questions, navigation and confirmed
snapshot differ from V1:

- questionnaire schema version;
- template version;
- template hash;
- schema hash;
- aggregate release hash;
- customer disclosure/consent version when wording or purpose changes.

Rules:

1. V1 is a test-only prototype and is not a supported customer product.
2. Do not implement public dual-schema selection, customer migration, grace
   periods or V1 restart messaging.
3. Before replacement, stop new Draft Studio test-order creation, let or
   cancel test payment links, reconcile test-mode payment events and confirm
   that no preview/payment operation is in flight.
4. Export the minimum synthetic evidence needed for the test report, then use
   the approved maintenance/reset procedure to remove V1 test drafts, orders
   and artifacts from the staging dataset and private test storage. Do not use
   ad-hoc SQL or manual S3 deletion.
5. Replace the V1 question catalogue and renderer contract with the simplified
   schema in one controlled code release. Only the replacement can create an
   order after deployment.
6. The replacement remains fail-closed until a licensed Maharashtra advocate
   approves the exact questionnaire, route-outs, template, disclosures and
   golden PDF/DOCX hashes.
7. Run fresh end-to-end UAT from an empty Draft Studio test dataset. The
   final production database starts without V1 test orders or artifacts.
8. Rollback restores the prior application/database checkpoint as a complete
   release action; it does not operate two questionnaire schemas concurrently.
9. If an active synthetic V1 draft is encountered after the code cutover, the
   application marks it `SCHEMA_SUPERSEDED`, releases any unused capacity
   reservation, records an audit event and starts an empty V2 draft. It never
   maps old answers into the new schema.

## 10. Implementation seams

The implementation should separate these concerns:

- immutable question/section catalogue;
- a single active-schema resolver with a fail-closed candidate/active state;
- conditional navigation policy;
- answer validation and normalization;
- local PIN reference lookup;
- confirmed address representation and rendering;
- dependency invalidation after section edits;
- booking-minimum brief and post-payment preparation;
- customer consent and advocate-sharing gate;
- deterministic renderer and release manifest.

Do not add natural-language AI classification to the critical state machine.
AI may later suggest a category, but the customer must confirm it and a failed
provider must not block booking.

## 11. Required tests

### Draft Studio

- Every V1 field has an approved V2 disposition.
- Negative grouped eligibility answers route out with the correct reason.
- Fixed rules appear in scope, review and output without separate input fields.
- PIN with one/multiple/no matches follows deterministic correction paths.
- Non-Maharashtra PIN cannot satisfy Maharashtra eligibility.
- Customer correction overrides a suggestion only through a confirmed path.
- Same-as-premises copies the exact confirmed address; later property edits
  invalidate/reconfirm the dependent notice address.
- Full address review includes unit, building/floor when supplied,
  street/locality, city/taluka when supplied, district and PIN.
- Optional branches do not demand `NONE`.
- Occupant count is derived and the six-person boundary is enforced.
- Removed `furnishing` has no missing-token or output effect.
- Section edit preserves unrelated answers and invalidates preview/payment.
- No new V1 order can be created after replacement deployment.
- Replacement is blocked while any V1 test payment is pending or unreconciled.
- Approved cleanup removes V1 synthetic drafts/artifacts without touching
  production payment or customer data.
- Fresh UAT creates only replacement-schema records.
- Golden PDF/DOCX parity and new approval gate pass.

### Consultation booking

- Returning profiles skip redundant name/location entry but can edit them.
- `Not sure` reaches availability without taxonomy failure.
- Routine, deadline and safety paths preserve the correct controls.
- Capacity is never consumed before the existing reservation point.
- Price and policies remain visible before payment-link creation.
- Paid entitlement succeeds even when preparation is incomplete.
- Enriched brief attaches only to the owning paid booking.
- Advocate sharing requires the correct recorded consent.
- Resume, skip, edit and stale-button cases are idempotent.
- Admin operations clearly distinguish incomplete and confirmed briefs.

## 12. Measurement and acceptance

Use synthetic-data staging events to measure:

- starts, eligibility route-outs and cancellations by reason code;
- median interactions and elapsed time to preview/availability;
- section validation retry counts;
- address correction rate after the formatted review;
- preview-to-payment and slot-to-payment conversion;
- post-payment brief completion before the appointment SLA;
- operator requests for missing information;
- user and advocate clarity feedback.

No answer content is placed in analytics. Initial acceptance targets must be
set after baseline V1/UAT measurement; a lower question count alone is not a
success if address accuracy, safety triage or advocate preparation worsens.

## 13. Review gates

Before V2 coding:

- product owner approves this mapping and which post-payment fields are
  optional;
- operations confirms how `BRIEF_INCOMPLETE` is handled;
- privacy review approves PIN reference data and the revised consent purpose;
- a Maharashtra advocate decides whether taluka remains a mandatory separate
  fact and approves the grouped eligibility wording.

Before V2 activation:

- exact English copy and translations are frozen;
- implementation and migration tests pass;
- synthetic and advocate UAT pass;
- golden artifacts and hashes are reviewed and authenticated;
- the single-schema replacement, synthetic-data reset and rollback are
  rehearsed.

## 14. Primary sources

- Maharashtra Rent Control Act, 1999, including sections 24 and 55:
  <https://www.indiacode.nic.in/handle/123456789/15817?view_type=browse>
- Government of Maharashtra reference Leave and License Agreement:
  <https://lj.maharashtra.gov.in/Site/Upload/Pdf/Leave-and-License-Agreement.pdf>
- Department of Posts All India Pincode Directory through the Government of
  India Open Data Platform:
  <https://www.data.gov.in/catalog/all-india-pincode-directory-through-webservice>

These sources define the legal/official baseline only. The exact V2 product
scope, drafting and grouped confirmations remain subject to authenticated
Maharashtra-advocate review.
