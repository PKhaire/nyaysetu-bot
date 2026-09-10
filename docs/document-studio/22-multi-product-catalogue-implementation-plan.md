# Multi-Product Draft Studio Implementation Plan

**Status:** Phases A-B implemented locally through RC16; Phases C-E have not started  
**Sequence:** preserve RC14, complete the catalogue foundation, then build the
advocate-issued cheque-notice product through separate gated phases

## Objective

Allow Draft Studio to publish several independently versioned products without
weakening the current residential Leave & Licence release gate or creating a
second tester-only customer journey.

The same catalogue is visible to every user. Each product has exactly one
active schema for each approved language/jurisdiction combination. Products
may have different output classifications and workflows.

## Pre-RC15 constraints found in the repository

The current implementation is safe for one product but cannot add a second by
configuration alone:

- `document_catalogue.resolve_product()` rejects every code except the single
  Maharashtra Leave & Licence code.
- The catalogue imports one global `QUESTION_DEFINITIONS` collection.
- The renderer owns one `golden_answers()` payload.
- release approval validation resolves the default product instead of an
  explicitly requested product.
- workflow operations resolve the default product rather than
  `order.product_code`.
- health/readiness evaluates one release manifest.
- price configuration and payment description assume one document offer.
- WhatsApp product selection exposes one hard-coded product.

The database already snapshots `product_code`, template version, output
classification, schema/template hashes, price and currency on each order. The
template-approval ledger is also indexed by product/package. These foundations
should be preserved.

## Design decisions

### 1. Registry, not condition chains

Introduce an immutable registry:

```python
PRODUCTS: Mapping[str, DocumentProductDefinition]

resolve_product(product_code) -> DocumentProduct
visible_products() -> tuple[DocumentProduct, ...]
release_manifest(product_code) -> dict
workflow_for(output_classification) -> DocumentWorkflow
```

Every definition supplies:

- stable product code and display-translation keys;
- jurisdiction, language and output classification;
- template, questionnaire and renderer versions;
- typed questionnaire loader and validator;
- template/clause package loader;
- golden scenarios;
- price key, currency and retention class;
- eligibility and route-out contract;
- workflow type; and
- dependency/readiness checks.

Unknown, duplicate or partially configured entries fail startup/readiness.

### 2. One active schema per product

“One schema” means no simultaneous prototype and replacement schema for the
same product. It does not mean forcing rent and cheque facts into one legal
questionnaire.

| Product | One active schema |
| --- | --- |
| Maharashtra residential Leave & Licence | `mh-ll-questionnaire-2026-09-v3` |
| Single-cheque section 138 notice | Future approved `in-ni138-single-cheque-*` schema |

The common order table stores structured JSON revisions, while each product's
versioned schema owns permitted fields and validation.

### 3. Order-bound resolution everywhere

After an order exists, every preview, payment, rendering, approval, redelivery,
download and reconciliation operation must call:

```python
product = resolve_product(order.product_code)
```

No default product may be used for an existing order. The operation also
checks that the order's template/schema/hash/price snapshots match the resolved
package expected for its state.

### 4. Preserve existing product identity

The catalogue refactor must not change the current Leave & Licence:

- product code;
- template or schema version;
- aggregate hash;
- golden PDF/DOCX hashes;
- order states and payment reconciliation;
- existing S3 object keys; or
- advocate approval history.

A characterization test records those hashes before refactoring. Any change
fails CI and is investigated rather than automatically accepted.

### 5. Classification-specific deep workflows

Do not add cheque-notice conditions throughout the existing self-service
workflow.

```text
DocumentOrderCoordinator
  -> SelfServiceDraftWorkflow
  -> AdvocateIssuedNoticeWorkflow
```

The coordinator owns common authorization, order lookup, revision immutability,
payment evidence, artifact access and audit. Each workflow owns its permitted
states and transition rules.

The current agreement continues:

```text
DRAFT -> CONFIRMED -> PREVIEW_READY -> PAYMENT_PENDING
      -> PAID -> FINAL_AVAILABLE
```

The notice product uses:

```text
INTAKE -> EVIDENCE_PENDING -> ADVOCATE_TRIAGE -> ACCEPTED_AND_QUOTED
       -> PAYMENT_PENDING -> PAID -> ADVOCATE_DRAFTING
       -> CUSTOMER_FACT_CHECK -> ADVOCATE_FINAL_APPROVAL
       -> ISSUED -> DISPATCH_RECORDED
```

Decline, conflict, unsupported, expiry, refund and needs-attention transitions
are explicit, audited terminal/exception paths.

### 6. Product-specific pricing

Replace the single price lookup with a strictly validated product-price map or
equivalent typed settings. It must:

- contain exactly every enabled payable product;
- accept only positive whole INR values within a bounded range;
- reject unknown codes and missing prices;
- snapshot price/currency/quote scope on the order;
- never mutate an accepted or paid order when configuration changes; and
- support an advocate-issued matter-specific quote without trusting a client
  amount.

The cheque-notice product creates no payment entitlement until an advocate has
authenticated acceptance and the customer confirms the immutable quote.

### 7. Per-product release readiness

Readiness returns a non-secret item for every allowlisted product:

```json
{
  "draft_studio_release": {
    "ok": false,
    "products": {
      "mh_residential_leave_licence_11m_self_service": {
        "ok": true,
        "reason_code": "APPROVED"
      },
      "in_ni138_single_cheque_individual_advocate_issued": {
        "ok": false,
        "reason_code": "ADVOCATE_APPROVAL_MISSING"
      }
    }
  }
}
```

Production policy must be explicit: either all allowlisted products are
required for overall readiness, or an unavailable product is removed from the
allowlist and catalogue for everyone. There is no per-user bypass.

### 8. Evidence, review, issuance and dispatch records

The cheque product requires additive models not present in the current
self-service order:

- `DocumentEvidenceArtifact`: kind, checksum, type/size validation, private
  object reference, review status, expiry and legal hold.
- `DocumentAdvocateAssignment`: advocate, authority scope, conflict result,
  assigned/accepted/declined timestamps and SLA.
- `DocumentMatterReview`: immutable intake revision, legal decision, reasons,
  conditions and authenticated reviewer.
- `DocumentQuote`: amount, currency, service-scope version, expiry, acceptance
  and supersession.
- `DocumentIssueApproval`: exact final artifact hash, advocate decision,
  authentication/signing method and time.
- `DocumentDispatchEvent`: method, tracking reference, address snapshot hash,
  status, proof artifact and recorder.
- `DocumentLegalHold`: reason, authority, opened/closed time and retention
  override.

Do not store a reusable advocate signature image. Store the exact signed final
artifact and verifiable per-order approval/signing evidence.

### 9. Menu and UX

The four-row home menu stays unchanged:

1. Ask Legal Question
2. Book Consultation
3. Draft Studio
4. More Options

Inside `Create a Document`, render catalogue rows returned by
`visible_products()`. Every row shows:

- plain-language name;
- self-service or advocate-reviewed/issued classification;
- jurisdiction/language;
- starting price or “quote after advocate review”; and
- realistic completion/turnaround expectation.

List pagination and numbered-text fallback must remain within current WhatsApp
provider limits. Save/resume and section editing are common capabilities, not
copied per product.

## Delivery phases

### Phase A: Characterization and seams

- Freeze current product identity/hash tests.
- Add registry types with the current product as the only entry.
- Make catalogue, workflow, renderer, payment, release, admin and health APIs
  accept explicit product code.
- Prove all existing RC14 behaviour and hashes are unchanged.

**Exit:** current product passes full regression through the new interfaces;
no second product is visible.

### Phase B: Multi-product catalogue

- Add `visible_products()` and data-driven WhatsApp product rows.
- Add strict allowlist and product-price validation.
- Return readiness/release evidence per product.
- Extend admin operations, metrics and audit filtering by product.
- Test unknown, disabled, unpriced and unapproved products fail closed.

**Exit:** a synthetic non-legal dummy product can exercise routing in tests,
but only the approved agreement is enabled in staging.

### Phase C: Advocate-issued workflow foundation

- Add the new additive models and migration.
- Implement advocate assignment/conflict/acceptance and immutable quotes.
- Add private evidence ingestion/validation/access audit.
- Add exact per-order final approval/signing evidence.
- Add dispatch and proof tracking.
- Extend maintenance, retention, outbox and operations commands.

**Exit:** synthetic notice matters traverse every success/decline/refund/error
path without real legal content or public availability.

### Phase D: Cheque-notice legal package

- Complete advocate workshop using documents 18-21.
- Write exact clause catalogue and template only after discovery approval.
- Implement the approved questionnaire and validators.
- Produce golden supported/boundary/decline artifacts.
- Authenticate the exact package and dependency evidence.

**Exit:** product-specific gate reports approved in staging.

### Phase E: Staging UAT and controlled launch decision

- Use synthetic data first; then advocate-controlled tester matters only with
  documented consent and no actual dispatch.
- Verify mobile UX, save/resume, uploads, quote/payment, advocate approval,
  final PDF, dispatch simulation, reconciliation, retention and suspension.
- Conduct security/privacy review and restore drill before real evidence.
- Record go/no-go separately from the Leave & Licence decision.

**Exit:** documented approval to add the product to the global allowlist. Once
enabled, every eligible user sees the same catalogue entry.

## Required regression matrix

- Current agreement start/resume/preview/pay/download remains unchanged.
- Product A cannot resolve Product B schema, template, approval or artifact.
- Order product code cannot be changed after creation.
- Unknown/disabled/unpriced/unapproved product cannot create payment.
- Approval for one package cannot authorize another product or version.
- Evidence access requires customer ownership or assigned authorized advocate.
- Operator cannot make an advocate legal decision.
- Quote amount and Razorpay amount/currency must match exactly.
- Payment webhook/reconciliation is idempotent across both workflow classes.
- Post-approval edit cannot reuse signed artifact or approval.
- Dispatch status cannot be inferred from WhatsApp status.
- Retention never deletes active legal hold, paid evidence or unresolved
  financial evidence.
- Global catalogue has no tester phone, cohort or percentage gate.

## Cost and dependency impact

The catalogue refactor itself requires no new hosting service. Existing
PostgreSQL, web service, payment reconciliation, outbox and private S3 can be
extended.

Potential incremental costs arise from:

- evidence storage and transfer;
- malware/file scanning;
- compliant electronic signing, if adopted;
- speed-post/dispatch and proof retrieval;
- advocate review and operational SLA; and
- additional monitoring/support load.

These costs must be measured in the synthetic/advocate pilot before a public
price is promised.

## Phase A implementation result

RC15 introduced a private product-definition registry and the small catalogue
interface `registered_product_codes()`, `resolve_product(code)`,
`customer_visible(code)` and `visible_products()`. The current agreement is
the only registered product. WhatsApp selection now carries its explicit code
into order creation, and preview, payment, final rendering and release checks
resolve the product from the immutable order code. Unknown or mismatched
packages fail closed.

The existing agreement's template, schema, aggregate and golden artifact
hashes remained byte-for-byte unchanged. No second product, migration, price,
menu item, feature flag or tester-specific route was added.

## Phase B implementation result

RC16 adds strict global catalogue validation, a preferred immutable per-product
INR price map with a backward-compatible RC14 price fallback, and per-product
release evidence in readiness. A malformed, unknown, disabled, unpriced or
unapproved product fails closed before payment. Staging and production require
every globally allowlisted product to pass its exact release gate.

The runtime registry is immutable and rejects duplicate, mismatched or partial
definitions. Existing-order package comparisons require every identity field
to be present and exactly equal; empty legacy/corrupt snapshots fail closed.
Translated product rows use bounded eight-product pages plus navigation, and a
numbered text reply resolves only within the page the customer was shown.

The WhatsApp catalogue is generated from the registered visible products.
Operator catalogue, order, metrics and audit views can report or filter by
product without exposing client answers, contacts or advocate identity
evidence. Automated tests temporarily inject a synthetic non-legal definition
to prove routing and cross-product configuration. That definition is absent
from the runtime registry and cannot be deployed or shown to customers.

The existing Maharashtra residential agreement remains the only runtime
product. Its legal/package identity and golden artifacts remain unchanged.
No cheque-notice content, payment, evidence upload, migration or customer
visibility is included.

## Immediate next implementation ticket

After RC16 is uploaded and CI is green, start **Phase C only**: implement the
advocate-issued workflow foundation using synthetic matters and no real legal
content or public product registration.
