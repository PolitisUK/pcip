# Deployment Checklist for Release Candidate 1

## 1. Environment and secrets

- Set a strong non-default `SECRET_KEY`.
- Set `ENVIRONMENT=production` (or equivalent hosted non-dev value).
- Set `COOKIE_SECURE=true`.
- Set `SESSION_COOKIE_SECURE=true`.
- Set `TRUSTED_HOSTS` to explicit production hostnames only.
- Set `ALLOWED_ORIGINS` to explicit HTTPS origins only.
- Set `AZURE_DEFENDER_WEBHOOK_SECRET`.

## 2. Identity and authentication

- Confirm intended login mode:
  - local password login and/or Microsoft Entra.
- If Entra is enabled, validate:
  - tenant/client settings
  - domain allow-list
  - provisioning controls

## 3. Database and migrations

- Run:
  - `alembic upgrade head`
- Confirm migration level includes latest revision.
- Verify app startup no longer depends on implicit schema drift fixes.

## 4. Storage and malware controls

- Set production storage backend (recommended: `azure_blob`).
- Confirm Defender scan workflow is active.
- Confirm unscanned-download bypass is disabled.
- Validate webhook auth by sending signed test request.

## 5. Security middleware checks

- Confirm response headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy`
  - `Permissions-Policy`
  - CSP without `unsafe-inline`
- Confirm HTTPS and HSTS behavior in hosted environment.

## 6. Privacy controls

- Validate admin-only participant export.
- Validate deletion workflow and anonymisation fallback.
- Configure retention settings:
  - `PRIVACY_RETENTION_DAYS`
  - `PRIVACY_RETENTION_STATUSES`
  - `PRIVACY_RETENTION_ACTION`

## 7. CI/CD validation

- CI passing on main branch:
  - tests
  - pip-audit
  - bandit
  - release image smoke test
- Confirm deployment workflow identity/OIDC credentials.

## 8. Operational smoke tests

- Validate `/health` returns status ok.
- Perform login/logout flow.
- Create project/study/participant.
- Send and accept participant invitation.
- Submit participant response and download CLEAN evidence.
- Verify audit entries are generated.

## 9. Observability and support

- Confirm log collection and retention.
- Confirm alerting for failed startup and repeated auth failures.
- Confirm backup/restore procedure for production database.
