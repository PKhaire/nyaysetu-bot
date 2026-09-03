# Data Retention and Processing Register

Policy baseline for the first self-service product. Legal, finance and privacy
owners must approve statutory finance retention before activation. A legal
hold suspends deletion only for narrowly scoped, audited records.

| Data class | Purpose/location | Retention trigger | End action |
| --- | --- | --- | --- |
| In-progress answers | Resume; PostgreSQL | 7 days after last activity unless confirmed | Delete payload; terminalize order |
| Eligibility failure | Explain route; PostgreSQL | 7 days | Delete answers; retain bounded reason counter |
| Confirmed Snapshot | Bind output; PostgreSQL | Final window ends or unpaid order expires | Delete payload; keep hash/version/time |
| Temporary render files | Generate/upload; runtime | End of job on success/failure | Private unlink in `finally` |
| Preview PDF | Inspect before payment; private S3 | 7 days or superseded/paid/cancelled | Delete/verify/mark |
| Final PDF/DOCX | Paid delivery; private S3 | 30 days after release | Delete/verify/mark |
| Presigned URL | Download capability | 5-15 minutes | Never persisted; natural expiry |
| Payment/invoice evidence | Reconciliation/accounting | Finance-approved statutory period | Minimum evidence then delete |
| Minimal Audit Record | Integrity/access/dispute | Approved legal/security period | Delete/anonymize; no content |
| Operational logs | Reliability/security | 30 days or shortest supported period | Provider expiry; no content/PII |
| Analytics | Product improvement | 13 months maximum | Aggregate/anonymize/delete |

The Digital Personal Data Protection Rules, 2025 use phased commencement. The
30-day operational-log baseline must be re-evaluated before the later notice,
security, breach and retention rules commence. If then-applicable Rule 8(3) or
another law requires a one-year record for a covered processing purpose, retain
only the mapped privacy-minimised data and logs for that required period; do
not extend that requirement to document text or answers without a recorded
legal basis. This commencement mapping is a production release gate.

## Processing rules

- Use answers only for eligibility, drafting, payment, delivery and necessary
  support/security/retention operations.
- Do not use them to train AI, advertise, profile or make a legal decision. V1
  sends no customer facts to generative AI.
- Never put document bytes/answers in analytics, notification subjects,
  WhatsApp logs, exception traces or ordinary support notes.
- Object keys and public references contain no name, phone, address or property
  identifier.
- Access is owner- or purpose-authorized and audited.

## Customer controls

Show a concise notice before intake. Support correction before confirmation,
abandon/delete for unpaid drafts, and a privacy route for access, correction,
erasure and grievances. Withdrawal stops optional future processing but does
not remove evidence lawfully required for an already-paid order.

## Deletion job contract

A bounded leased job deletes objects idempotently, verifies absence, records
only IDs/outcomes, deletes answer payloads and retries transient errors.
Overdue deletion, orphan objects, inconsistency or permission failure alerts
operations and prevents a false completion claim. Backups and noncurrent S3
versions must expire consistently.

## Cross-region statement

The Render app/PostgreSQL are in Singapore and planned S3 is Mumbai
(`ap-south-1`). Notices must state this accurately; do not claim all data stays
only in India.
