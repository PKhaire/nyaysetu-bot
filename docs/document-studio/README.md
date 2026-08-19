# NyaySetu Document Studio

Status: design baseline plus an RC8 staging-only synthetic UAT harness. No
legal output, payment, signature, file upload, S3 object or public download is
created by the implemented harness.

## Decision summary

NyaySetu will build a controlled document-preparation workflow using
advocate-approved, versioned templates. The first release will not use a
generative model to invent legal clauses and will not accept customer evidence
uploads. PostgreSQL stores structured workflow metadata; a private Amazon S3
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

## V1 flow

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

## Required approval before implementation

Approval of this design baseline authorizes engineering work but does not
approve any legal template. Template approval is a separate, per-version
advocate decision recorded using the standard in this package.

## Implemented UAT boundary

RC8 implements only the navigation and answer-capture slice described in
[the RC8 release notes](../RELEASE_NOTES_2026-08-19_RC8.md). It uses one
synthetic allowlisted product, persists resumable test drafts, stores an
immutable confirmed-answer revision, and emits privacy-minimised audit events.
The complete V1 flow above remains the future product design, not current
customer functionality.
