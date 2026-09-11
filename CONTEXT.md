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
- **Advocate-Issued Notice**: A separately priced service in which a Verified
  Advocate accepts one matter, approves an immutable quote, reviews the
  customer's evidence and issues one exact locked PDF. The cheque-notice
  package is registered privately after Phase D, but it is not globally
  allowlisted or published.
- **Verified Advocate**: An active advocate whose enrolment evidence and
  product authority scope have been recorded before assignment.
- **Advocate Identity**: A named password-plus-TOTP identity linked one-to-one
  to a Verified Advocate. It can make only advocate-authorized matter
  decisions and cannot use the general operations console.
- **Advocate Assignment**: The immutable authority snapshot and SLA that bind
  one Advocate Identity to one Document Order.
- **Matter Review**: The assigned advocate's conflict result and acceptance,
  decline or unsupported decision for one exact intake revision.
- **Quote**: An immutable INR amount and service-scope snapshot created only
  after advocate acceptance and explicitly accepted by the customer before
  payment can be requested.
- **Issue Approval**: The per-order advocate decision binding one confirmed
  fact revision, candidate draft and exact issued-PDF hash. It is not a
  reusable signature or general template approval.
- **Dispatch Record**: Evidence that an issued notice was handed to the
  configured dispatch channel. It does not prove legal service or receipt.
- **Legal Hold**: An active administrator-authorized retention override that
  prevents scheduled deletion of the order's artifacts and evidence until an
  audited closure.
- **Operator**: A named operations identity that may assign work, reconcile
  payment, coordinate redelivery and record dispatch, but cannot decide a
  conflict, accept legal scope, create an advocate quote or issue a notice.
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

