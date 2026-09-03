# Clause Catalogue: Maharashtra Residential Leave and Licence

This catalogue defines clause intent, data dependencies and branch control. It
does not approve final legal wording. Exact prose lives in an immutable
template package and requires advocate sign-off.

The selected V1 values and route-outs are recorded in the
[V1 Legal-Drafting Decision Record](15-v1-legal-drafting-decision-record.md).
The exact candidate prose is in the
[Candidate Template](16-residential-leave-license-candidate-template.md).

| Code | Required intent | Inputs | Safety/branch rule | Review basis |
| --- | --- | --- | --- | --- |
| `LL-MH-001` | Parties/capacity | Party fields | One each; never claim verification | Contract Act |
| `LL-MH-002` | Licensor authority recital | Authority confirmation | Confirmation only; no title conclusion | Advocate |
| `LL-MH-003` | Premises description | Premises fields | Complete fields; uncertainty routes out | Advocate/IGR |
| `LL-MH-004` | Residential licence/use | Use | Fixed use; no tenancy/enforceability guarantee | Rent Control/Easements |
| `LL-MH-005` | 11-month term | Dates | Server derivation plus confirmation | Advocate |
| `LL-MH-006` | Fee/due/payment | Fee fields | Digits/words; no bank details | Stamp Act |
| `LL-MH-007` | Refundable deposit | Deposit fields | No non-refundable amount in V1 | Stamp Act/advocate |
| `LL-MH-008` | Maintenance/utilities | Fixed V1 allocation | Licensor: property tax/society/major repair; licensee: metered use | Advocate |
| `LL-MH-009` | Occupants | Occupant fields | Names only; no IDs | Privacy/advocate |
| `LL-MH-010` | Furnishing/inventory | Inventory fields | Optional bounded schedule; no upload | Advocate |
| `LL-MH-011` | Lawful use/conduct | Acknowledgements | Fixed lawful standard terms | Advocate |
| `LL-MH-012` | No transfer/sub-licence | Acknowledgement | Consistent with named occupants | Easements/advocate |
| `LL-MH-013` | Repairs/damage/condition | Approved text | No uncapped/ambiguous automated damages | Advocate |
| `LL-MH-014` | Inspection/access | Fixed 24-hour notice | Reasonable hours/frequency; genuine emergency exception | Advocate |
| `LL-MH-015` | Termination/notice | 30-day ordinary; 7-day curable breach | No lock-in; custom/asymmetric terms route out | Statutes/advocate |
| `LL-MH-016` | Vacant possession | Dates/ack | No automatic/forcible recovery promise | Rent Control s.24 review |
| `LL-MH-017` | Notices | Notice addresses | No unapproved deemed-service mechanism | Advocate |
| `LL-MH-018` | Stamp/registration responsibility | Money summary | Informational; current IGR verification | s.55/Stamp Act/IGR |
| `LL-MH-019` | Governing law/forum | Scope | Fixed wording; no outcome claim | Advocate |
| `LL-MH-020` | Entire understanding/amendment | None | Must preserve mandatory law | Advocate |
| `LL-MH-S01` | Premises schedule | Premises | Exact match with clause 003 | IGR/advocate |
| `LL-MH-S02` | Inventory schedule | Inventory | Only when non-empty | Advocate |
| `LL-MH-N01` | Output classification | Manifest | Visible Self-Service Draft statement | Product/legal |
| `LL-MH-N02` | Next-step checklist | Sources | External execution/fee/registration steps | IGR/current review |

## Manifest rules

- Record clause code, content hash and display order for every output.
- Never treat free-form answers as executable template syntax or raw HTML.
- Wording, condition, order or defined-term change creates a new Template
  Version and aggregate hash.
- Help changes influencing an answer also require version review.
- Approval lists every clause hash, synthetic golden artifact hash,
  exclusions, effective date and next review date.
- Missing, duplicate or unknown clause codes fail rendering closed.

## Advocate authentication required

The candidate now resolves deposit deductions/refund timing, maintenance,
utilities, repairs, inspection, termination, possession, notices, forum,
witness/execution blocks, stamp explanation and registration checklist. A
licensed Maharashtra advocate must still authenticate the exact candidate
wording and hashes. Any rejection or condition creates a new immutable
candidate and blocks `APPROVED` until resolved.
