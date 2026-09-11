# NyaySetu Draft Studio

Status: Phase D cheque-notice package implemented privately after RC17.
Global menu visibility, one conditional questionnaire, PIN assistance,
deterministic rendering, exact payment, private artifact storage, short-lived
downloads, retention controls, strict per-product pricing and per-product
release readiness are implemented. The existing residential agreement remains
the only runtime product; production publication still requires current
release-gate, regression/UAT and operational evidence.

## Decision summary

NyaySetu will build a controlled document-preparation workflow using
advocate-approved, versioned templates. The first release will not use a
generative model to invent legal clauses. Its current public self-service
product does not accept customer evidence uploads; Phase C accepts only
synthetic scanned evidence through the private workflow seam. PostgreSQL stores
structured workflow metadata; a private Amazon S3
bucket in `ap-south-1` stores generated artifacts. Downloads are authorized by
NyaySetu and delivered through short-lived presigned URLs.

The product distinguishes these outputs visibly and operationally:

1. **Self-service draft**: generated from customer-confirmed answers; not
   reviewed, issued, signed, or certified by an advocate.
2. **Advocate-reviewed document**: reviewed by a named, authorized advocate
   under a recorded template version and review outcome.
3. **Advocate-issued or signed document**: produced only after an individual
   advocate explicitly accepts responsibility and completes the applicable
   issue/signature procedure. A stored signature image is never applied
   automatically.

## Current candidate flow

```text
Choose product
  -> understand scope and exclusions
  -> answer guided questions
  -> validate and confirm answers
  -> generate watermarked preview
  -> accept price, terms, and output classification
  -> pay through Razorpay
  -> advocate review when included
  -> generate immutable final PDF/DOCX
  -> authorize a 5-15 minute download
  -> retain/delete under the approved policy
```

## Documents in this package

| Document | Purpose |
| --- | --- |
| [Product and scope](01-product-and-scope.md) | Users, outputs, V1 boundaries, success measures |
| [Workflow and governance](02-workflow-and-governance.md) | State machine, template lifecycle, advocate controls |
| [Technical architecture](03-technical-architecture.md) | Services, data model, APIs, rendering and S3 design |
| [Security and privacy](04-security-privacy-retention.md) | Threat model, access, consent, retention and deletion |
| [Catalogue standard](05-catalogue-and-template-standard.md) | How document products and clauses are approved |
| [Delivery plan](06-implementation-test-launch.md) | Phases, tests, rollout gates and rollback |
| [Dependencies and cost](07-dependencies-and-cost.md) | Mandatory/optional dependencies and cost controls |
| [Source register](08-source-register.md) | Primary law, official guidance, provider constraints and review duties |
| [First product specification](09-residential-leave-license-mh-product-spec.md) | Exact V1 scope, eligibility and artifact contract |
| [Questionnaire contract](10-residential-leave-license-questionnaire.md) | Stable fields, validation, derivation and confirmation evidence |
| [Clause catalogue](11-residential-leave-license-clause-catalogue.md) | Clause intent, variables, branches and advocate decisions |
| [Retention register](12-data-retention-and-processing-register.md) | Purpose, location, retention trigger and deletion control by data class |
| [Implementation contract](13-implementation-contract.md) | Deep module interfaces, provider seams, invariants and test evidence |
| [Advocate review pack](14-advocate-review-pack.md) | Per-version content approval and activation record |
| [V1 legal-drafting decisions](15-v1-legal-drafting-decision-record.md) | Conservative selected terms, route-outs, limitations and final human gate |
| [Candidate agreement template](16-residential-leave-license-candidate-template.md) | Exact English candidate prose and renderer-token contract for authentication |
| [V2 intake and booking UX plan](17-v2-intake-ux-reduction-plan.md) | All-question keep/combine/conditional/remove mapping, PIN-assisted address design and shorter consultation journey |
| [Cheque-notice product specification](18-cheque-bounce-notice-product-spec.md) | Proposed advocate-issued V1 boundary, eligibility, evidence, payment, issuance and dispatch controls |
| [Cheque-notice questionnaire](19-cheque-bounce-notice-questionnaire.md) | Private versioned runtime schema, bounded validation, route-outs and advocate-only decisions |
| [Cheque-notice source and decision register](20-cheque-bounce-notice-source-and-decision-register.md) | Primary-law baseline and conservative revalidated Phase D decisions |
| [Cheque-notice advocate review pack](21-cheque-bounce-notice-advocate-review-pack.md) | Controlled discovery and exact-release authentication record |
| [Multi-product catalogue plan](22-multi-product-catalogue-implementation-plan.md) | Product-registry and separate self-service/advocate-issued workflow plan with phased acceptance criteria |
| [Cheque-notice clause catalogue](23-cheque-bounce-notice-clause-catalogue.md) | Exact clause purposes, tokens, prohibited branches and artifact contract |
| [Cheque-notice candidate template](24-cheque-bounce-notice-candidate-template.md) | Exact private English notice prose for assigned-advocate review and signing |
| [ADR 0001](../adr/0001-document-studio-publication-and-artifact-contract.md) | Universal publication and preview/payment/final binding decision |
| [ADR 0002](../adr/0002-advocate-identity-and-legal-decision-boundary.md) | Named advocate identity and operator/legal-decision separation |

## Non-negotiable launch principles

- No product is published without a recorded advocate-approved template,
  intake schema, exclusions, jurisdiction scope, version, price and review date.
- Payment never changes the wording of the document silently. The paid output
  is generated from the exact confirmed answer snapshot and template version.
- No user can fetch another user's artifact. A storage URL alone is not an
  authorization mechanism.
- No public S3 objects, personal data in object keys, permanent download links,
  reusable advocate signature images, or documents in application logs.
- Failed payment, rendering, review or delivery never produces a misleading
  success state.
- Development and UAT use synthetic people, addresses, account numbers and
  disputes only.

## Required approval before publication

Approval of this design baseline authorized engineering work but does not
approve any legal template. Template approval is a separate, per-version,
authenticated advocate decision recorded using the standard in this package.
The product owner reports advocate approval of the cheque-notice discovery
pack for template drafting. That decision does not authorize an exact runtime
template, customer visibility, payment collection, advocate signature,
issuance or dispatch.

## Implemented RC9 boundary

RC9 implements the controlled workflow described in
[the RC9 release notes](../RELEASE_NOTES_2026-08-27_RC9.md). Once the global
switch is enabled, the same Draft Studio menu is visible to every user; no
named-user UAT allowlist exists. Eligibility, answer confirmation,
deterministic watermarked preview, exact test-payment verification, private
final PDF/DOCX generation, owner-authorized download and bounded deletion are
implemented behind fail-closed release controls.

The runtime release ledger, rather than repository prose, determines whether
the exact residential package is active. The product owner has reported a
successful authenticated staging activation, but production must independently
verify that the same exact approval is current, unexpired and non-revoked.
Repository implementation, synthetic testing or a general green signal cannot
replace that evidence. Production can expose only a package that passes
[ADR 0001](../adr/0001-document-studio-publication-and-artifact-contract.md)
for every globally enabled product.
