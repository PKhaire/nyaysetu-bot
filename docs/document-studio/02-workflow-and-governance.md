# Workflow and Governance

## Aggregate state machine

The document order owns one explicit state. State changes occur in database
transactions and append an audit event.

```text
IN_PROGRESS
  -> ANSWERS_CONFIRMED
  -> PREVIEW_GENERATING
  -> PREVIEW_READY
  -> PAYMENT_PENDING
  -> PAID
  -> REVIEW_PENDING        (reviewed products)
  -> REVISION_REQUIRED     -> ANSWERS_CONFIRMED
  -> APPROVED
  -> FINAL_GENERATING
  -> FINAL_AVAILABLE
  -> DELIVERED
```

Terminal/exception states are `CANCELLED`, `EXPIRED`, `REJECTED`,
`RENDER_FAILED`, `PAYMENT_REVIEW`, `DELIVERY_FAILED` and `REFUND_REVIEW`.
An exception does not erase the earlier audit or payment evidence.

## Transition requirements

| Transition | Required evidence |
| --- | --- |
| `IN_PROGRESS -> ANSWERS_CONFIRMED` | Valid schema, eligibility acknowledged, exact answer hash, consent version |
| `ANSWERS_CONFIRMED -> PREVIEW_READY` | Active approved template, successful deterministic render, preview hash |
| `PREVIEW_READY -> PAYMENT_PENDING` | Price/scope snapshot, accepted terms, unique order/payment reference |
| `PAYMENT_PENDING -> PAID` | Existing exact Razorpay provider verification and idempotency contract |
| `PAID -> REVIEW_PENDING` | Review work item and target SLA |
| `REVIEW_PENDING -> REVISION_REQUIRED` | Reviewer, reason codes, bounded notes, affected answer/section codes |
| `REVIEW_PENDING -> APPROVED` | Active authorized advocate and explicit approval of answer/template/artifact hashes |
| `APPROVED -> FINAL_AVAILABLE` | Immutable render, checksum, private storage receipt and artifact metadata |
| `FINAL_AVAILABLE -> DELIVERED` | Authorized download or recorded manual delivery outcome |

The system must compare the current answer and template hashes with the values
approved by the reviewer. If either differs, approval becomes stale and final
generation is blocked.

## Answer management

- Intake schemas use stable field codes; labels can change without changing
  meaning or stored evidence.
- Answers are typed: text, date, money, party, address, enum, boolean or
  repeated structured group.
- Normalization is separate from the original user-entered value where the
  original is material.
- The customer sees the normalized final summary and confirms it explicitly.
- Material changes after confirmation create a new answer revision and require
  reconfirmation.
- A template renderer reads only fields declared in the product schema.
- Unknown client-supplied keys are rejected rather than merged into a template.

## Advocate review procedure

1. Operator assigns only an active, verified advocate who is authorized for
   the product/jurisdiction.
2. Reviewer opens the confirmed summary and the exact rendered review artifact.
3. Reviewer checks identity of parties as represented, material facts,
   jurisdiction/scope, timing/eligibility where applicable, clause selection,
   exclusions and requested outcome.
4. Reviewer selects `APPROVE`, `REQUEST_REVISION` or `REJECT` and records
   structured reason codes plus a concise operational note.
5. Approval records reviewer ID, answer revision/hash, template version/hash,
   artifact hash, timestamp and output classification.
6. Issuance/signature, if sold, is a separate action against the immutable
   final artifact and is never inferred from approval.

Reviewer notes must not become an ungoverned alternate drafting channel.
Reusable legal improvements are made through a new clause/template version,
not pasted invisibly into one customer's output.

## Template lifecycle

```text
DRAFT -> LEGAL_REVIEW -> APPROVED -> ACTIVE -> RETIRED
                         |             |
                         +-> REJECTED  +-> SUSPENDED
```

- Only one explicitly selected active version is offered for a product and
  jurisdiction at a time.
- Approval records legal owner, reviewer, effective date, next-review date,
  source/reason summary and a cryptographic content hash.
- Published versions are immutable. Corrections create a new version.
- Suspending a version blocks new previews/payments but preserves existing paid
  orders and artifacts for controlled resolution.
- A scheduled review becoming overdue prevents new sales unless a formally
  approved grace policy exists. It never mutates already generated documents.

## Price and payment governance

- The order stores currency, base price, taxes/fees display, discount if any,
  scope and product/template version before a link is created.
- The Razorpay notes/reference must identify exactly one document order.
- The existing webhook principle applies: signed webhook plus authenticated
  current provider evidence, exact amount/currency/reference and idempotent
  processing.
- Payment success creates entitlement to the purchased service, not automatic
  legal approval.
- If final generation or review cannot be completed, the order enters an
  operator queue; it does not fabricate delivery.

## Signature and execution governance

The following are distinct and must not be conflated:

- Advocate reviewed the draft.
- Advocate issued a notice or opinion.
- Advocate digitally/electronically signed the artifact.
- Parties executed an agreement.
- A witness, notary, registrar, government portal or service provider completed
  an external act.

V1 supports manual, individually authorized advocate issuance. It does not
store a signature asset for automatic reuse. The final document and dashboard
must say exactly which events occurred and which remain the customer's
responsibility.

## Manual operations

Manual contact is acceptable for the pilot and avoids depending on outbound
Meta template approval. Each manual handover or delivery attempt records
operator, audience, channel, outcome, timestamp and bounded notes. Document
contents and permanent download URLs are not placed in notes.

## Suspension and incident response

An operator with appropriate authority can suspend a product or template from
new sales. Existing orders are triaged by state:

- Unpaid orders: expire preview/payment link.
- Paid but unreviewed: queue for replacement, manual handling or refund review.
- Approved but not generated: block generation until compatibility is decided.
- Final available: preserve according to retention/legal-hold rules and notify
  only if the identified issue affects that version.

Suspension, replacement and reactivation are audited. They are not implemented
as deletion of history.
