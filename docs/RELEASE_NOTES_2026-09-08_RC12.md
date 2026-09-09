# NyaySetu RC12 - Named Administrator MFA

**Candidate date:** 8 September 2026  
**Schema:** `20260908_01`  
**Release decision:** required security hardening before the first public launch.

## Outcome

RC12 replaces the shared browser password with individually attributable human
operations identities. Each named account has a Werkzeug scrypt password hash,
encrypted RFC 6238 TOTP seed, one-use recovery codes stored only as keyed
digests, persistent failed-attempt lockout, role, and session-invalidation
counter. The browser supports `ADMIN`, `OPERATOR`, and read-only `VIEWER`
authorization.

Named browser mutations always use the verified session identity for audit.
An `X-Operator-ID` request header cannot impersonate another actor. The header
remains required for approved machine calls authenticated by the separate
`ADMIN_TOKEN`.

The legacy `ADMIN_PASSWORD` is available only as a staging bootstrap while the
database has zero named identity rows. Creating the first pending identity
disables that fallback, and production never accepts it. Production readiness
requires at least two active named identities including one active `ADMIN`.

## Account controls

- Six-digit TOTP accepts the current 30-second interval with a one-interval
  clock window and rejects replay of an already accepted interval.
- An unused recovery code may replace TOTP for one login and is then consumed.
- Five failed identity attempts lock the account for 15 minutes in the
  database; the existing address-level browser throttle remains defence in
  depth.
- Disable/re-enable, password reset, and MFA reset invalidate prior browser
  sessions.
- The last active `ADMIN` cannot be disabled.
- Passwords, authenticator seeds, and recovery codes are prompted/displayed
  only through the privileged interactive shell and are never accepted as
  command-line arguments or stored in audit events.

## Operator lifecycle command

`python -m jobs.manage_admin_operator` provides:

- `enroll` and `activate`;
- privacy-safe `list`;
- `disable` and `enable`;
- `reset-password`; and
- `reset-mfa` with replacement one-use recovery codes.

After the first active administrator exists, enrollment, activation, and every
lifecycle change require an existing active `ADMIN` `--actor-id`. This records
accountability; it is not another Render-shell authentication factor. Render
access must therefore have separate provider MFA and least privilege.

## Migration and configuration

Revision `20260908_01` adds `admin_operators` and `admin_recovery_codes`. It
does not rewrite earlier migration files or Document Studio/payment evidence.
Downgrade deliberately refuses to discard identity/security evidence.

Set one unique durable `ADMIN_MFA_ENCRYPTION_KEY` generated as a Fernet key
before deployment. It must remain separate from `SECRET_KEY`, must never be
committed or pasted into evidence, and must be backed up in the approved secret
store. Losing or changing it makes stored TOTP seeds and recovery-code digests
unusable; any rotation requires a controlled MFA replacement plan.

The release pins `cryptography==50.0.1` and its locked runtime dependencies for
Fernet authenticated encryption. No new paid provider, DNS change, or external
identity service is required; operators use an ordinary standards-compatible
authenticator app.

## Safe deployment order

The current Render backend is still configured as staging. Keep it that way
for the RC12 bootstrap:

1. Add `ADMIN_MFA_ENCRYPTION_KEY` privately to the backend environment.
2. Deploy the exact RC12 SHA while `ENV=staging`; pre-deploy applies
   `20260908_01` and readiness may report `legacy_bootstrap` without failing.
3. In the protected backend shell, enroll and activate the first `ADMIN`, then
   enroll and activate a second named identity using the first administrator as
   `--actor-id`.
4. Confirm `python -m jobs.manage_admin_operator list` exposes no secret and
   `/health/ready` reports named-MFA production compatibility.
5. Test named login, role denial, recovery, lockout, disable/reset session
   invalidation, logout, and audit attribution in staging.
6. Complete the remaining integrated checklist and restore drill.
7. Only at the recorded production cutover switch to `ENV=production`, live
   Razorpay/provider configuration, isolated production storage/data, and the
   approved production secrets.

Do not switch an empty database directly to production before enrolling the two
required identities: readiness is designed to fail closed in that state.

## Required validation

- Local focused identity, command, admin-route, configuration, and migration
  tests: **69 passed**.
- Local full suite: **361 passed**; combined `app.py`/`services` coverage
  **68.74%**, above the required 60% gate.
- Local Ruff, Python compile, dependency lock consistency, SBOM parity, and
  `pip check`: passed.
- Local `pip-audit` against `requirements.lock`: no known vulnerabilities at
  the candidate date.
- Gunicorn configuration validation remains a GitHub CI/Linux check because
  Gunicorn imports the POSIX-only `fcntl` module and cannot execute on the
  Windows development host.
- PostgreSQL migration `upgrade head`, `current`, and `check` evidence in CI.
- Manual staging identity/recovery/role/session/audit tests with sanitized
  evidence.

Passing local or CI tests does not authorize public traffic. The integrated
production checklist remains `NO-GO` until every mandatory external gate and a
recorded GO decision are complete.
