# NyaySetu RC7 — Consent-Based Case Brief and Manual Advocate Handover

Release date: 18 August 2026

## Outcome

RC7 gives the operations team the information and controls needed to prepare a
paid consultation without collecting document files or depending on outbound
WhatsApp template approval. A user creates a structured case brief, explicitly
consents to sharing it for the consultation, and the confirmed brief follows
the resulting booking into the protected appointment console.

## User-flow changes

- Captures a bounded factual summary, matter stage, dates, desired outcome,
  urgency, safety cue, available-document checklist, and opposing party.
- Does not accept or store Aadhaar, PAN, bank details, passwords, or document
  images/files.
- Shows the factual brief separately from a short, versioned consent prompt so
  WhatsApp interactive-message length limits cannot hide the consent decision.
- Allows the user to review, edit, cancel, or consent before appointment
  selection.
- Links only a confirmed brief to the booking created after the user chooses to
  pay.

## Operations and privacy changes

- Appointment operators can review the confirmed brief in the existing
  protected dashboard.
- Client and advocate phone numbers remain masked in ordinary list responses.
- Contact reveal requires a stable operator ID and purpose and creates an audit
  record.
- Operators can register verified advocates, assign them to paid matters, and
  record manual client/advocate contact attempts, outcomes, notes, and follow-up
  times.
- Manual notification is the launch procedure; outbound Meta template approval
  is not a dependency for this release.
- Unattached briefs are automatically eligible for bounded deletion after the
  configured retention period. Booking-linked briefs remain preserved.

## Database and configuration

- Current Alembic head: `20260818_01`.
- New environment values:
  - `CASE_BRIEF_CONSENT_VERSION=case-brief-sharing-2026-08`
  - `CASE_BRIEF_UNATTACHED_TTL_DAYS=7`
- The daily Render maintenance service inherits the same brief-retention value
  as the web service.

## Required deployment sequence

1. Upload every file in the RC7 upload package without flattening directories.
2. Commit to `main` and require all GitHub Actions jobs to pass.
3. Keep Render maintenance mode enabled and deploy the exact green commit.
4. Confirm the pre-deploy Alembic command upgrades PostgreSQL to
   `20260818_01` and the service becomes live.
5. Confirm `/health/live` and `/health/ready` return HTTP 200 and readiness
   reports schema `20260818_01`.
6. In staging/test payment mode, complete one synthetic case brief, consent,
   booking, and payment flow.
7. Confirm the admin queue masks the phone, shows the brief, allows only a
   verified advocate assignment, audits contact reveal, and records both
   manual notification attempts.
8. Run the maintenance dry-run and confirm only eligible unattached synthetic
   briefs are candidates for deletion.
9. Disable maintenance mode only after the recorded release checklist passes.

Do not use real identity numbers, evidence documents, bank details, passwords,
or sensitive case facts in deployment smoke tests.
