# Product and Scope

## Objective

Document Studio helps a person prepare a structured legal document without
typing a free-form prompt or knowing legal drafting terminology. It collects
only the facts required for a selected product, explains material choices,
validates completeness, shows a preview before payment, and preserves the exact
version reviewed or delivered.

It is a document-preparation and advocate-workflow product. It must not imply
that software alone has determined legal rights, guaranteed enforceability,
completed execution, or replaced advice from a qualified advocate.

## Primary users

| User | Need |
| --- | --- |
| Customer | Understand the product, enter facts, preview, pay and obtain the correct output |
| Advocate reviewer | Review the confirmed facts and rendered draft, request corrections, approve or reject |
| Operator | Resolve payment/delivery exceptions without editing legal content invisibly |
| Template owner | Maintain clauses, questionnaire rules, translations and legal-review evidence |
| Auditor/support | Reconstruct who changed, approved, generated, accessed and delivered an artifact |

## Output classifications

### Self-service draft

- Uses an approved template but has no matter-specific advocate review.
- Carries a visible draft classification and generated timestamp.
- Cannot include an advocate name, signature, stamp or statement of approval.
- Is priced and described separately from reviewed services.

### Advocate-reviewed document

- Starts from a customer-confirmed answer snapshot.
- Records reviewer, review timestamp, decision and template version.
- Any requested change returns to the customer or an authorized controlled
  correction workflow; it is never made silently.
- The final document identifies the review classification accurately.

### Advocate-issued or signed document

- Requires an explicit matter-specific advocate action after reviewing the
  final bytes or their canonical representation.
- Requires a documented signature/issuance method and authority.
- Does not treat a scanned signature, logo or name as proof of execution.
- May require parties, witnesses, stamp duty, registration, service or other
  steps outside NyaySetu. Those steps are product-specific and must be stated.

## V1 functional scope

- Product catalogue and eligibility/exclusion screen.
- Guided, schema-driven questionnaire with save/resume.
- Field-level and cross-field validation.
- Customer review and explicit answer confirmation.
- Watermarked PDF preview before payment.
- Razorpay payment link tied to an immutable order and price snapshot.
- Advocate review queue for products configured as reviewed.
- Controlled revision request and customer reconfirmation.
- Final PDF and DOCX rendering.
- Private S3 storage and short-lived download authorization.
- WhatsApp delivery of a secure link while the service window permits;
  otherwise manual communication.
- Audit events, artifact hashes, version history and retention processing.
- Admin search by safe business reference, not public storage path.

## Explicit V1 exclusions

- Customer uploads of evidence, identity documents or prior contracts.
- OCR, handwriting extraction or automated document interpretation.
- Generative AI clause creation or unsupervised legal analysis.
- Automatic advocate signature, stamp, letterhead or dispatch.
- Registration, notarization, e-stamping, physical service or court filing.
- Automatic determination of limitation periods or statutory eligibility.
- Bulk document generation, marketing mail or public document links.
- Collaborative multi-party editing and redlining.
- Automated refunds; existing reviewed Razorpay operations remain authoritative.

An excluded capability may be added only after its threat model, operating
procedure, price and acceptance tests are approved.

## Candidate product sequence

The catalogue below is discovery input, not legal approval:

1. Residential agreement information/draft for one approved state and use
   case, with execution, stamp-duty and registration limitations stated.
2. Cheque-related demand notice intake and advocate-reviewed draft, with all
   timing, service and eligibility decisions owned by the reviewing advocate.
3. Money-recovery notice.
4. Mutual non-disclosure agreement.
5. Simple service/consultancy agreement.
6. Consumer grievance/complaint draft.

The first engineering pilot should implement only one low-ambiguity product.
The second product should exercise the advocate-reviewed path. Publishing many
shallow templates is less safe than proving two complete workflows.

## Commercial rules

Every product record declares:

- Price and tax display.
- Whether the price covers drafting only, one review, revisions, issuance or
  consultation.
- Number and type of included revisions.
- Target turnaround expressed as a service target, not a legal guarantee.
- Cancellation/refund rule for each lifecycle stage.
- Artifact formats and download period.
- Exclusions and external costs, including stamp duty, registration, service,
  notarization or government fees where applicable.

Payment is taken only after the user sees the confirmed facts, preview
classification, price, scope and refund/revision terms.

## Experience requirements

- English first, followed by independently reviewed Hindi and Marathi
  questionnaire/help text. Legal clauses are not translated by machine in V1.
- Plain-language prompts with examples that contain no real personal data.
- Progress, save-and-return and a clear way to correct an earlier answer.
- A summary screen groups parties, dates, money, obligations and special terms.
- Material choices explain their effect without steering the user deceptively.
- Unsafe, urgent or out-of-scope matters route to consultation/support rather
  than generating a confident document.
- The user can identify the document version, status and whether an advocate
  reviewed it.

## Bot entry and navigation

WhatsApp reply buttons support only three actions. At Document Studio launch,
the home changes to a list-style service menu so all four primary destinations
remain visible and **More Options** stays last:

```text
Hi / MENU
  -> View NyaySetu services
     1. Ask NyaySetu
        General legal information
     2. Book Consultation
        Schedule a paid consultation
     3. Document Studio
        Create agreements and notices
     4. More Options
        Appointments, guides, support, privacy and language
```

The Document Studio landing list contains:

1. **Create a document** - show only active, approved products.
2. **Continue a draft** - resume the latest eligible in-progress order.
3. **My documents** - show status and authorized re-download actions.
4. **How it works** - explain preview, payment, review and output classes.

After **Create a document**, the user chooses an approved product such as a
residential agreement or advocate-reviewed notice, sees its scope and price,
and only then begins the questionnaire. Relevant legal-guide answers may also
offer a contextual **Prepare this document** action, but they must not create
an order or take payment without the same scope and confirmation screens.

Users may type `DOCUMENT`, `DRAFT`, `AGREEMENT` or `NOTICE` as discoverability
shortcuts. These keywords open the landing list; they do not infer a product.
The home message may mention document preparation only when at least one
product is active.

While `DOCUMENT_STUDIO_ENABLED=false`, the existing three-button home remains
unchanged. Enabling the feature switches the home to the four-row list above.
The flag also ignores contextual actions and returns a neutral unavailable
message for direct/old action identifiers. A second product allowlist prevents
an approved code deployment from publishing an unapproved legal template.

## Success measures

- Questionnaire completion rate and median completion time.
- Validation failure and abandonment point by non-sensitive field code.
- Preview-to-payment conversion.
- Advocate first-pass approval and revision rate.
- Payment-to-final turnaround.
- Delivery/download success without exposing document contents in analytics.
- Refund, complaint, wrong-template and unauthorized-access incidents.
- Percentage of artifacts deleted on schedule.

Metrics must use product/session identifiers and bounded categories. They must
not copy names, addresses, account numbers, notice text or full answers into
analytics events.
