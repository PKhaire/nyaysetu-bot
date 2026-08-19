# Catalogue and Template Standard

## Purpose

This standard prevents Document Studio from becoming a folder of unreviewed
Word files. A product is publishable only when its legal content, intake,
commercial scope, rendering and operations form one versioned package.

## Product definition

Every catalogue entry contains:

| Field | Requirement |
| --- | --- |
| Product code | Stable, non-marketing identifier such as `residential_agreement_mh_v1` |
| Display name | Plain-language user name |
| Output classification | Self-service, advocate-reviewed or advocate-issued |
| Jurisdiction/scope | Exact supported geography, transaction and user type |
| Eligibility | Facts required before offering the workflow |
| Exclusions | Conditions that route to consultation/manual handling |
| Questionnaire schema | Versioned typed fields, help, validation and materiality |
| Clause manifest | Stable clause codes, variants, conditions and order |
| Output formats | Preview PDF, final PDF, DOCX and any issuance artifact |
| Price/scope | Fee, revisions, review, turnaround and external costs |
| Retention class | Approved artifact/metadata lifecycle |
| Legal ownership | Content owner, reviewer, approval and next-review dates |
| Test pack | Golden scenarios, negative cases and expected clause manifest |

## Template package structure

```text
legal_templates/<product_code>/<semantic_version>/
  manifest.yaml
  questionnaire.schema.json
  clauses/
    <clause_code>.md-or-structured-source
  layouts/
    document.docx-template
    preview-layout
  translations/
    en.yaml
    hi.yaml
    mr.yaml
  examples/
    synthetic-basic.json
    synthetic-boundary.json
  legal-review.md
  CHANGELOG.md
```

This path is conceptual until implementation chooses a safe parser and
repository format. The manifest and every included file contribute to the
published content hash.

## Questionnaire rules

- Each field has a stable code, purpose, type, required condition, maximum
  length/count, normalization, help text and sensitivity classification.
- Conditional questions declare readable rules; they do not execute arbitrary
  code.
- Material answers are highlighted on the confirmation page.
- Derived values record their formula/rule version and source fields.
- Free text is minimized. Where needed, it is bounded and rendered as factual
  user-provided content, not silently converted into legal conclusions.
- A user can select `not known` only where the product defines how that affects
  eligibility and output.

## Clause rules

- Stable clause code and title.
- Legal purpose and inclusion/exclusion conditions.
- Required answer fields.
- Mutually exclusive or dependent clause relationships.
- Jurisdiction and language availability.
- Material-choice explanation shown to the customer.
- Legal source/review note maintained privately where appropriate.
- Golden test cases proving inclusion, exclusion and ordering.

No clause is constructed through concatenation of an untrusted instruction or
model response. User facts are escaped and placed only in declared fields.

## Review record

The advocate review file for a version records:

- Product code and semantic version.
- Complete content hash.
- Supported jurisdiction and effective date.
- Eligibility and exclusions reviewed.
- Questionnaire and clause manifest reviewed.
- Preview/final disclaimers and execution instructions reviewed.
- Price description and included service checked for accuracy.
- Reviewer name/internal ID, professional authorization evidence reference,
  decision, timestamp and next-review date.
- Known limitations, operational dependencies and reason for change.

A verbal or general "green signal" is not sufficient publication evidence for
a future modified version. Each published content hash needs its own decision.

## Candidate 1 discovery: residential agreement

Before drafting, the advocate workshop must decide at least:

- Supported state and exact agreement type.
- Parties and capacity/authority.
- Premises description and permitted use.
- Term, commencement, rent/license fee, deposit and escalation.
- Utilities, maintenance, repairs and access.
- Restrictions, termination, notice and possession/handover.
- Stamp duty, registration, witnesses and execution instructions.
- Situations requiring title/authority review or manual consultation.

V1 will not infer ownership or verify title because evidence upload and
verification are excluded.

## Candidate 2 discovery: cheque-related demand notice

This should be advocate-reviewed, not an unsupervised instant notice. The
workshop must define supported legal basis, instrument/payment facts, parties,
presentation/return evidence, dates, bank communication, amount, service
address/method, timing checks, exclusions and escalation. The software must not
present an automatically calculated deadline or eligibility conclusion until
the exact rules and edge cases are approved and tested by advocates.

## Language governance

- Questionnaire/help translation and legal-clause translation are separate.
- Machine translation may assist internal drafting but cannot publish a legal
  language version without independent review.
- Dates, currency, names, addresses, numbering and defined terms are tested in
  every enabled script.
- The final document states its authoritative language and treatment of any
  translation where applicable.

## Change classes

| Change | Version/review treatment |
| --- | --- |
| Typographical display help only | Recorded patch review; prove no legal output change |
| Validation/help affecting answers | New schema/template patch and tests |
| Clause wording/condition/order | New immutable version and legal approval |
| Jurisdiction/eligibility change | New version; existing-order impact review |
| Price/service scope change | New commercial snapshot; no retroactive mutation |
| Renderer dependency/layout change | Output regression review and new renderer version |

## Publication checklist

- [ ] Product, jurisdiction, eligibility and exclusions are precise.
- [ ] Questionnaire data minimization and validation are approved.
- [ ] Every branch maps to an expected clause manifest.
- [ ] Synthetic golden outputs pass PDF/DOCX rendering review.
- [ ] Classification, limitations and execution instructions are visible.
- [ ] Price, revisions, turnaround and refund rules match operations.
- [ ] Advocate owner/reviewer and next-review date are recorded.
- [ ] Security, retention and access class are assigned.
- [ ] Suspension and existing-paid-order plan is documented.
- [ ] Product/version is activated through an audited release action.
