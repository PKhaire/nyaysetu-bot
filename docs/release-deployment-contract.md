# Release Deployment Contract

This file defines the immutable production process contract for the six-month
NyaySetu candidate. It complements the broader deployment runbook.

## Exact commands

| Phase | Command |
| --- | --- |
| Build | `python -m pip install --disable-pip-version-check --no-deps -r requirements.lock && python -m pip check` |
| Migration | `python -m alembic -c alembic.ini upgrade head` |
| Web | `gunicorn --config gunicorn.conf.py app:app` |
| Outbox | `python -m jobs.process_outbox` |
| Payment reconciliation | `python -m jobs.reconcile_payments --limit 100` |
| Consultation reminders | `python -m jobs.consultation_reminders` |
| Maintenance | `python -m jobs.maintenance --batch-size 500 --fail-on-risk` |

The web service uses one `gthread` worker with eight threads. The single process
is a correctness constraint while any coordination or throttling remains
process-local. `gunicorn.conf.py` rejects an accidental worker-count override.
Its access-log format records the URL path but excludes query strings and
referrers, preventing webhook verification tokens from entering access logs.

## One-time SQLite data cutover

This is a separate, controlled release gate, not a recurring deploy command.
Stop the web service and all four cron writers; create and restore-test an
untouched source through SQLite's Online Backup API or CLI `.backup`; upgrade a
separate disposable working copy selected through an explicit working-copy
`DATABASE_URL` with `AUTO_CREATE_SCHEMA=false`; and clear those variables when
Alembic `upgrade head`, `current`, and `check` finish. Never run Alembic on the
untouched restore artifact. After every process closes, use SQLite's backup
mechanism again to create a distinct frozen artifact without WAL, SHM, or
journal sidecars. The managed PostgreSQL target must be empty and at the same
Alembic head. The runbook contains the exact safe environment sequence.

Set the short-lived target credential only in
`NYAYSETU_CUTOVER_TARGET_URL`. The default command is a no-write preflight:

```powershell
python -m jobs.migrate_sqlite_to_postgres --source-sqlite <frozen-backup.db>
```

After `status=ready`, recorded go/no-go approval, and proven restore, use the
exact import confirmation:

```powershell
python -m jobs.migrate_sqlite_to_postgres --source-sqlite <frozen-backup.db> --confirm-import IMPORT_SQLITE_COPY_INTO_EMPTY_POSTGRESQL
Remove-Item Env:NYAYSETU_CUTOVER_TARGET_URL
```

Clear the dedicated variable on any preflight/import failure before
investigation.

The command deliberately ignores application `DATABASE_URL`, refuses a
non-empty target, and rolls back an incomplete import. Validate counts,
constraints, sequences, backfills, and every payment state before any service
uses the target. Retain the untouched SQLite backup through the rollback window.
The authoritative sequence is in the
[PostgreSQL cutover runbook](deployment-operations.md#postgresql-cutover).

## Render release controls

All five services are declared in `singapore` and use
`autoDeployTrigger: off`. Production deployments must therefore be started
manually from an approved immutable commit after CI and staging acceptance.
Render regions cannot be changed on an existing service, so moving an existing
service to Singapore requires a separately rehearsed service migration.

The paid web service runs Alembic as its pre-deploy command. A migration failure
stops the new release before traffic moves to it. Deploy in this order:

1. Back up production and record the current application and migration revision.
2. Deploy the web service from the approved commit and verify migration output.
3. Verify `/health/ready`, schema revision, signed webhooks, and payment status.
4. Deploy outbox, payment reconciliation, and reminders from the same commit.
5. Verify reminder scheduling is a no-op while template pairs are empty, or
   verify every explicitly approved staging template.
6. Run maintenance `--dry-run`, then deploy its cron and assign every risk.
7. Run bounded payment reconciliation and assign every open review item.

The outbox runs every minute. The maintenance job runs daily at 20:30 UTC
(02:00 IST) and affects only the conservative, bounded categories implemented
by `services.maintenance_service`. Its TTL, payment-lookback, and support-SLA
settings are copied from the web service so maintenance cannot silently drift
from the production policy. Its scheduled `--fail-on-risk` run exits `2` after
a successful transaction when overdue fulfilment/support or stale
payment-review work requires attention.

Payment reconciliation runs every five minutes. It auto-recovers only evidence
that agrees across current Razorpay Payment Link and Payment resources and is
captured, exact, and non-refunded; ambiguity enters the operator queue. The
payment webhook independently enforces that same dual-resource contract before
entitlement. Current-resource failure stays retryable, invalid current evidence
stays unpaid in review, and terminal manual dispositions remain authoritative
over delayed events. Before release, a two-session production-like PostgreSQL
rehearsal must prove that webhook-first and operator-first decisions serialize
through the shared booking-to-review lock order, without deadlock or a lost
terminal disposition.
Consultation-reminder scheduling runs every ten minutes but is inert until an
exact Meta-approved template name/language pair is configured. The outbox
rechecks live eligibility before sending.

## CI and rollback evidence

CI runs on pushes, pull requests, manual dispatch, and weekly. It:

- uses commit-SHA-pinned checkout and Python setup actions;
- installs/audits the fully pinned runtime lock and runs `pip check`;
- verifies that deterministic CycloneDX `sbom.cdx.json` exactly matches the
  production lock;
- validates the Gunicorn configuration;
- runs application tests and dependency auditing;
- starts disposable PostgreSQL;
- upgrades to the Alembic head and checks model parity; and
- rehearses the schema-compatible downgrade/re-upgrade sequence.

The SBOM is an offline component inventory, not a vulnerability result. The
weekly `pip-audit` job against `requirements.lock` remains the time-sensitive
vulnerability gate.

The current baseline downgrade intentionally preserves additive operational and
payment evidence. A code rollback does not imply a destructive schema rollback.
If a migration or payment reconciliation fails, keep the last healthy web
release serving, stop new payment intake if integrity is uncertain, preserve a
database snapshot, and follow the reviewed database recovery procedure.

Meta app-secret and Razorpay webhook-secret rotations use the optional
corresponding `_PREVIOUS` variables only for a bounded retry/rollback overlap.
When nonempty, readiness requires at least 32 characters for the previous Meta
app secret and 16 for the previous Razorpay webhook secret.
Clear them after the provider dashboard uses the new primary secret and both
new-signature success and old-signature rejection have been verified.

Authoritative configuration references:

- [Render Blueprint YAML reference](https://render.com/docs/blueprint-spec)
- [Render deploy and pre-deploy behavior](https://render.com/docs/deploys)
- [Gunicorn settings](https://docs.gunicorn.org/en/stable/settings.html)
