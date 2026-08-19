# Security, Privacy and Retention

## Data classification

Document Studio handles confidential legal and personal information. Treat
confirmed answers, rendered artifacts, review notes, access grants and delivery
records as restricted business data. Payment secrets, cloud credentials and
webhook secrets remain security credentials and are never document data.

Potential inputs include names, addresses, dates, financial facts, dispute
details and relationships. V1 questionnaire design must prove that every field
has a defined purpose. Avoid collecting identity documents, bank statements,
signatures, health data or evidence files unless a later approved product
cannot operate without them.

## Threat model

| Threat | Required control |
| --- | --- |
| Public or guessed document URL | Private bucket, random IDs, application authorization, short presigned URL |
| One customer accesses another order | Ownership check on every read/mutation plus negative authorization tests |
| Operator browses without purpose | Role, stated purpose, audited access, masked queue summaries |
| Stolen runtime credential | S3-prefix least privilege, rotation, no bucket administration, alerts |
| Presigned URL copied | 5-15 minute expiry, HTTPS, no logs/messages beyond intended delivery |
| Template changed after payment/review | Immutable versions and answer/template/artifact hashes |
| Malicious answer breaks renderer | Typed schema, length/count limits, escaping and no executable templates |
| Temporary file remains on Render | Random private temp file and unconditional deletion |
| Old versions retained forever | Explicit current/noncurrent lifecycle expiry and deletion verification |
| Signature applied without authority | No reusable signature asset; individual issuance audit |
| Sensitive data enters logs/analytics | ID/reason-code logging only; automated log tests |
| Dependency/template supply-chain change | Pinned lock, SBOM, review, content hashes and controlled publishing |

## Identity and access

### Customer

WhatsApp identity alone is not sufficient for a permanent public download URL.
The workflow binds access to the active verified conversation/order and issues
a short-lived capability only after current entitlement checks. Any web portal
added later needs its own authenticated session and account-recovery design.

### Operator and advocate

Roles should separate support, document operations, advocate review, template
publishing and security administration. An advocate may access only assigned
orders and artifacts required for review. Template publishers cannot approve
their own version unless a formally accepted small-team exception is recorded.

Every unmasked access requires a reason and creates an audit event. Bulk export
is excluded from V1.

### Cloud runtime

- Use a new S3-specific IAM identity; never reuse root or SES credentials.
- Store credentials only in Render secret environment variables.
- Do not put secret values in `.env.example`, source, logs or support messages.
- Rotate on suspected disclosure and verify the old credential is disabled.
- Budget alerts do not replace access restrictions.

Any credential previously pasted into chat, screenshots or tickets must be
treated as disclosed and rotated before Document Studio production access.

## Consent and notices

The user must see and affirm, with version evidence:

- Purpose and categories of information collected.
- Whether the output is self-service, reviewed, issued or signed.
- Who may review it and why.
- Storage/delivery providers and cross-region processing at an appropriate
  level of transparency.
- Retention/download period and deletion request channel.
- Price, included revisions and refund/cancellation rules.
- Product limitations and external execution/service obligations.

Consent is specific to this document workflow; existing AI or case-brief
consent is not silently reused.

## Proposed retention classes

These are engineering defaults for legal/privacy approval, not final legal
retention advice:

| Record/artifact | Proposed period | Rationale |
| --- | --- | --- |
| Unconfirmed intake | 7 days after inactivity | Resume without indefinite collection |
| Unpaid preview | 7 days after payment expiry | Customer recovery and support |
| Temporary render file | Delete immediately; maximum 24 hours on failure | No operational need after upload |
| Paid preview/review copies | 30 days after final delivery | Short dispute/review support |
| Final self-service artifact | 90 days after delivery | Re-download window |
| Advocate-reviewed/issued artifact | 180 days after delivery initially proposed | Operational/legal review required |
| Access/audit metadata | Separate approved period | Accountability without preserving document text |
| Payment/accounting evidence | Existing finance retention policy | Not deleted by object lifecycle |

The user can download and retain their copy. NyaySetu must not promise deletion
where law, dispute handling, accounting or a documented legal hold requires
preservation. Conversely, a vague possibility of litigation is not permission
to retain every document indefinitely.

## S3 lifecycle design

Use separate prefixes/tags or buckets so lifecycle rules can distinguish
temporary, unpaid and final artifacts. If versioning is enabled, rules must
expire current versions, permanently expire noncurrent versions, remove expired
delete markers and abort incomplete multipart uploads. A simple delete marker
is not proof of permanent erasure.

The retention job reconciles database metadata with S3 outcomes in bounded
batches. It records `DELETION_REQUESTED`, verifies absence where practical,
then records `DELETED`. Failures enter an operator queue and alert without
logging object contents or signed URLs.

## Legal hold

A hold is applied only by an authorized role with case/order, reason, scope,
requester and review/expiry date. It blocks lifecycle deletion through a
controlled tag/prefix/policy process and is reviewed periodically. V1 may
choose not to automate holds, but must then define a manual freeze and release
runbook before production.

## Backup and recovery

PostgreSQL recovery protects metadata, not S3 files. S3 versioning can protect
against accidental overwrite/delete but increases retention cost and privacy
complexity. The versioning decision requires a tested recovery and permanent
deletion procedure.

Recovery tests use synthetic artifacts and prove:

- Metadata-to-object consistency.
- Accidental deletion recovery inside the approved recovery window.
- Permanent deletion of current/noncurrent versions after expiry.
- Application behavior when metadata exists but an object is missing.
- Application behavior when an orphan object has no database metadata.

## Customer uploads in a future phase

Uploads remain blocked until all of these exist:

- Allowlisted MIME types verified from bytes, not filename.
- Size/page/count limits and safe randomized names.
- Direct private upload into a quarantine prefix.
- Malware scanning before any operator/renderer access.
- Parser isolation and protection against decompression/archive bombs.
- Metadata stripping where appropriate.
- Consent, purpose and shorter retention.
- Operator UI that never renders unsafe active content.
- Failure/quarantine/delete workflow and tests.

Confidential legal evidence must not be submitted to public multi-engine
scanning services as an implementation shortcut.

## Incident response minimum

1. Stop new document generation/download authorization if confidentiality or
   integrity is uncertain.
2. Revoke/rotate affected IAM credentials and invalidate application access.
3. Preserve privacy-minimized audit and provider evidence.
4. Identify affected objects, users, versions and time range.
5. Follow the approved breach assessment/notification procedure.
6. Repair, test with synthetic data and obtain recorded approval before resume.
7. Document root cause and preventive action without copying legal contents
   into the incident ticket unnecessarily.
