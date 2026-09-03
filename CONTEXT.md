# NyaySetu Domain Language

This glossary defines product language used by code, tests, operations and
documentation. It describes the domain, not the implementation.

- **Document Product**: A bounded document-preparation service with one
  jurisdiction, eligibility policy, questionnaire, clause catalogue, price,
  output classification and retention class.
- **Template Version**: An immutable, content-addressed version of a Document
  Product's questionnaire, clauses, renderer inputs, disclosures and customer
  instructions.
- **Product Publication**: The audited decision that one approved Template
  Version is available to every eligible NyaySetu user. Publication is never a
  per-customer, tester or cohort permission.
- **Document Order**: One customer's attempt to use one Template Version,
  including its answer revisions, commercial snapshot and output entitlement.
- **Answer Revision**: An immutable revision of facts entered for a Document
  Order.
- **Confirmed Snapshot**: The exact Answer Revision explicitly confirmed by
  the customer and bound to preview, payment and final output.
- **Self-Service Draft**: A document produced from customer-provided facts and
  an approved Template Version without matter-specific advocate review. It is
  not advocate-issued, signed or certified.
- **Preview Artifact**: A free, visibly watermarked PDF generated from a
  Confirmed Snapshot before payment.
- **Final Artifact**: The PDF or DOCX generated after verified payment from the
  same Confirmed Snapshot and Template Version as the accepted preview.
- **Entitlement**: The server-side authorization to obtain a particular Final
  Artifact after payment evidence and order state have been verified.
- **Artifact Availability Window**: The 30-day period during which a customer
  may re-download Final Artifacts before scheduled deletion.
- **Advocate Review**: A future, separately described and priced service in
  which a named advocate reviews a specific matter. It is not included in the
  first self-service product.
- **Execution**: Party signature and related completion acts. NyaySetu's first
  product prepares a draft; it does not execute it.
- **Registration**: The statutory submission and registration process outside
  the first Document Studio product.
- **Suspension**: An audited global stop on new orders or releases for a
  Product or Template Version due to legal, security, payment or operational
  risk.
- **Minimal Audit Record**: A record of identifiers, versions, decisions,
  hashes, amounts and timestamps that excludes document text and substantive
  customer answers.

