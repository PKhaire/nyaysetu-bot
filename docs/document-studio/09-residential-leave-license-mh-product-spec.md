# Product Specification: Maharashtra Residential 11-Month Leave and Licence

## Product identity

| Item | V1 decision |
| --- | --- |
| Product code | `mh_residential_leave_licence_11m_self_service` |
| Output class | Self-Service Draft |
| Jurisdiction | Maharashtra, India |
| Language | English |
| Use | Residential premises only |
| Term | Fixed 11 months |
| Parties | One adult individual licensor and one adult individual licensee, each acting for themselves |
| Review included | No matter-specific advocate review |
| Preview | Free watermarked PDF |
| Paid output | Final PDF and editable DOCX |
| Availability | 30 days after final release |

The product code is stable. Every legal wording, questionnaire or renderer
change creates a new immutable Template Version and content hash.

## Customer promise

NyaySetu converts confirmed answers into a structured draft using an
advocate-approved template. It does not verify identity, title, authority,
property or payment facts; determine rights; give matter-specific advice;
execute or register the agreement; pay government fees; or guarantee validity
or enforceability.

## Eligibility matrix

All `ALLOW` conditions must be true. A `ROUTE` condition stops generation and
offers a paid consultation or independent advocate.

| Code | Condition | Allow | Route and reason |
| --- | --- | --- | --- |
| EL-01 | Property is in Maharashtra | Yes | Other state needs a different product |
| EL-02 | Completed residential premises | Yes | Commercial, agricultural, PG/co-living or employee housing |
| EL-03 | Exactly one licensor and one licensee | Yes | Multiple/organizational party complexity |
| EL-04 | Both adult individuals competent to contract | Yes | Minor, guardian or capacity concern |
| EL-05 | Each acts for themselves | Yes | POA, representative, trust, company, LLP or partnership |
| EL-06 | Licensor confirms authority to license | Confirmation only | Authority uncertain/disputed; title is not verified |
| EL-07 | No ownership, possession, tenancy or eviction dispute | Yes | Existing dispute needs individual advice |
| EL-08 | No conflicting tenant/licensee/occupant | Yes | Conflicting occupancy |
| EL-09 | Term is exactly 11 months | Yes | Different, renewing or indefinite term |
| EL-10 | Not a sale, lease, sub-licence or financing arrangement | Yes | Different legal/commercial character |
| EL-11 | No coercion, threat or inability to understand | Yes | Safety/capacity/advice route |
| EL-12 | Standard clauses accepted without custom rights | Yes | Custom clauses, lock-in or unusual termination |
| EL-13 | No advocate signature/certification requested | Yes | Separate review/issuance workflow |
| EL-14 | Registration, fees and execution remain external | Yes | Cannot continue on a misleading basis |

## Commercial and artifact contract

1. Before payment show scope, exclusions, price/taxes, refund/cancellation
   rule, confirmed-fact summary and watermarked preview.
2. Preview manifest contains order reference, Confirmed Snapshot hash,
   Template Version/hash, renderer version and preview hash.
3. Create a Razorpay request only for that immutable manifest.
4. Grant entitlement only after signed webhook and provider lookup confirm
   order, amount, currency and paid state.
5. Generate final PDF/DOCX from the same manifest. Any answer/template change
   invalidates preview/payment request and requires reconfirmation.
6. Provide server-authorized short-lived download links for 30 days.

## Output package

- Final PDF and editable DOCX with identical substantive content.
- Visible classification, template version, reference and generation date.
- Plain-language review, execution, stamp-duty, registration and preservation
  checklist.
- Existing controlled payment receipt/invoice.

No output contains a NyaySetu advocate signature, stamp, letterhead or claim of
matter-specific approval.

## Product acceptance

- Advocate signs exact questionnaire, clause manifest, synthetic boundary
  outputs, disclosures and next-step checklist.
- PDF/DOCX parity is automated and manually sampled.
- Ineligible answers never create a payable order or ordinary draft.
- Cross-user, stale-preview, wrong-payment and expired-download tests deny.
- Activation makes the approved version visible to all eligible users with an
  audited global suspension action available.

