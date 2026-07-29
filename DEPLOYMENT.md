# PCIP Deployment

Last verified from the repository: 2026-07-28

## Status and scope

This document distinguishes repository behavior from live Azure state.

**Repository fact:** the Bicep and GitHub workflow describe a Linux Azure App
Service custom container backed by ACR, PostgreSQL Flexible Server, Blob
Storage, Key Vault, Log Analytics, Application Insights, and managed identities.

**Live evidence:** a read-only Azure inventory was captured on 2026-07-28. It
verified the production Web App, ACR manifest, selected non-secret app settings,
PostgreSQL configuration, and recent resource-group deployment records.

**Still unknown:** database constraint/index drift, the source commit that
produced the running image, the exact digest pulled by the current container,
App Service plan SKU/scale details, logs and telemetry, restore-test history,
alerts, and a proven last known good release.

Do not perform a production deployment or migration until the pre-deployment
inventory in `OPERATIONS.md` has been captured.

## Live production findings

The live Web App is running and references
`pcipprodceflpyg7acr.azurecr.io/pcip:0.6.0`. At inventory time that mutable tag
resolved to:

```text
sha256:6cd7e60983190f70143e2e64dfb34588858f743a142c5ebb7f47bd727af346dc
```

The manifest was created on 2026-07-27 at 17:00:56 UTC. This digest is a
rollback candidate, not yet a proven rollback release: the source commit and
exact digest pulled by the running container have not been independently
correlated.

After the controlled database baseline, the live `/health` endpoint returned
HTTP `200` and application version `0.6.0`. Its response still exposed
`environment` and `storage_backend`; the hardened branch removes those fields.
The live `/health/ready` endpoint returned HTTP `404`, confirming that the
running mutable `0.6.0` tag predates the hardened candidate despite using the
same application version label.

| Control | Live state | Repository desired state | Assessment |
|---|---|---|---|
| App state | Running; `/health` returned `200` after baseline | Running | Liveness proven after baseline |
| Image | Mutable tag `0.6.0` | Currently tag-based; roadmap is digest-based | Release provenance incomplete |
| Health check | Not configured; live `/health/ready` returns `404` | `/health/ready` | Do not configure until the hardened image is staged and deployed |
| Always On | `false` | `true` | Drift; cold starts/restarts are more likely |
| `RUN_MIGRATIONS` | `false` | `false` | Aligned; database revision must still be checked before a release migration |
| `SEED_DEMO_DATA` | Setting absent, application default `true` | `false` | Critical drift; hardened code now rejects this outside development |
| Secure cookies | Both explicit and `true` | Both `true` | Aligned |
| Storage | Azure Blob | Azure Blob | Aligned at the selected setting level |

Live PostgreSQL is version 16 on `Standard_B1ms` Burstable, with 14-day backup
retention, public network access enabled, high availability disabled, and
geo-redundant backup disabled. The inventory returned two recent
resource-group deployments and both were failed, including the named production
infrastructure deployment. This explains why repository intent and live state
diverged, but does not identify every manual change made during recovery.

A read-only schema inventory subsequently confirmed all 19 application tables,
the columns represented through repository revision `0005`, all expected
foreign keys, and the expected primary, unique, and application indexes. The
single production user has no conflicting email or Entra identity. A controlled
transaction subsequently created only Alembic's version table and recorded
`0005`. Legacy startup `create_all` is the likely reason the marker was
originally absent, but that cause remains an inference. Revision `0006` remains
unapplied and must be treated as a separate release migration.

## Release artifact

The release image:

- uses `python:3.12-slim`;
- installs `requirements.lock`, the exact runtime dependency set verified on
  Python 3.12/Linux;
- upgrades the image's package installer to the pinned patched version;
- copies only files allowed by `.dockerignore`;
- starts through `/app/entrypoint.sh`;
- listens on `${PORT:-8000}`.

Development and CI tools live in `requirements-dev.txt` and are not installed in
the release image.

## Current GitHub Actions deployment flow

`.github/workflows/deploy-azure.yml` is manually dispatched. It currently:

1. checks out the selected commit;
2. installs development dependencies and runs the test suite;
3. signs in to Azure using GitHub OIDC;
4. deploys `infra/main.bicep`;
5. selects the first ACR and first Web App in the configured resource group;
6. builds `pcip:<operator-supplied tag>` in ACR;
7. restarts the selected Web App;
8. polls `/health/ready` for up to five minutes.

This is not yet an approved production release process. Resource selection is
ambiguous, the tag is mutable/operator-supplied, infrastructure points the app
at the tag before the image build finishes, and there is no automated rollback
or staging-slot promotion. The permanent flow should use explicitly configured
resource names and a commit-SHA tag resolved to an immutable image digest.
Changing the release flow is intentionally deferred until the live database
revision and a tested staging/rollback route are established.

## Infrastructure represented by Bicep

| Resource | Repository configuration |
|---|---|
| App Service | Linux, HTTPS-only, system identity, always-on, one minimum instance, `/health/ready` |
| App Service plan | `B1` default |
| ACR | Basic, admin user disabled, App Service identity has `AcrPull` |
| PostgreSQL | Version 16 Flexible Server, 32 GB, 14-day backup, no HA, no geo-redundant backup |
| Blob Storage | Standard ZRS, public blob access disabled, shared-key access disabled, 14-day soft delete |
| Defender for Storage | On-upload malware scanning with blob result tags |
| Key Vault | RBAC, soft delete, versioned secret references |
| Monitoring | Workspace-based Application Insights and 30-day Log Analytics retention |

The template currently permits public network access to ACR, Storage, Key
Vault, and PostgreSQL. PostgreSQL allows Azure services through the
`0.0.0.0` firewall rule. These are deployment foundations, not an approved
production network boundary.

## Configuration and secrets

Non-secret settings are supplied as App Service application settings. Database,
session, Defender webhook, and optional Entra client secrets are stored as Key
Vault secrets and consumed through versioned Key Vault references. The app's
system identity has Key Vault Secrets User, Blob Data Contributor, and ACR Pull
roles.

The Bicep template explicitly configures:

- `ENVIRONMENT`;
- `SEED_DEMO_DATA=false`;
- HTTPS base URL, trusted host, and allowed origin;
- `COOKIE_SECURE=true` and `SESSION_COOKIE_SECURE=true`;
- PostgreSQL and Key Vault-backed application secrets;
- Azure Blob evidence storage and Defender enforcement;
- Application Insights;
- `RUN_MIGRATIONS=false` by default;
- Entra configuration when supplied;
- `LOCAL_LOGIN_ENABLED=true`.

Hosted startup independently validates security-critical configuration. A bad
configuration should prevent the app from becoming ready instead of silently
running with development defaults.

## Container lifecycle

`entrypoint.sh` executes `alembic upgrade head` when `RUN_MIGRATIONS=true`, then
uses `exec` so Uvicorn receives platform termination signals directly.

Application lifespan startup then:

1. configures logging;
2. validates runtime security settings;
3. tests database connectivity;
4. verifies the database is at all Alembic heads in hosted environments;
5. verifies the storage container;
6. calls SQLAlchemy `create_all`;
7. applies local SQLite compatibility changes;
8. optionally seeds a development database.

Hosted containers do not run migrations by default. A reviewed migration must
run once as an explicit release operation before the new application version is
promoted. Local Docker Compose opts into automatic migration for developer
convenience.

## Health and availability

- `/health` is a liveness endpoint and returns only status and application
  version.
- `/health/ready` runs `SELECT 1`. It returns `503` without leaking dependency
  details when the database is unavailable.
- Bicep configures App Service to use `/health/ready`.
- The deployment workflow checks readiness after restart.

Readiness does not yet test Blob, Key Vault, SMTP, Defender, or migration state
on each request. Migration and storage readiness are checked during startup.

## Logging and telemetry

Uvicorn writes application and access logs to standard output/error. The app
uses Python logging for startup/configuration, rate-limit events, webhook
rejections, and readiness failures. When
`APPLICATIONINSIGHTS_CONNECTION_STRING` is present,
`configure_azure_monitor()` installs the Azure Monitor OpenTelemetry distro.
Telemetry setup failure is logged and does not block startup.

Whether App Service container log collection, diagnostic settings, dashboards,
alerts, and retention are active in the live environment is unknown.

## Database deployment

Alembic has revisions `0001` to `0006`. Revision `0006` is an additive
global-identity expansion: it creates and backfills organisation memberships
while retaining the legacy user organisation/role columns for compatibility.
CI upgrades an empty PostgreSQL 16
database, reports the current revision, and runs `alembic check`. The later
revisions tolerate schemas created by the legacy `0001` behavior.

Production migration rules:

- take and verify a recoverable database backup before a risky migration;
- record the current revision and running image digest;
- review generated SQL and lock/rewriting behavior against production volume;
- deploy only backwards-compatible revisions while old containers could still
  serve traffic;
- never assume application rollback also rolls back the schema;
- define a forward-fix or explicit data-safe downgrade for every release.

The live database is 9,399 kB, its schema is verified as equivalent to revision
`0005`, and the controlled Alembic baseline now records `0005`.

## Permanent release design

After live inventory, implement this sequence:

1. CI tests, audits, migration checks, and builds once.
2. ACR stores an image tagged with `github.sha`.
3. The workflow resolves the pushed manifest digest.
4. A staging slot or staging app is configured with
   `registry/pcip@sha256:<digest>`.
5. A dedicated migration job runs once.
6. Staging readiness and smoke tests pass.
7. The immutable digest is promoted to production.
8. Post-deployment health, authentication, database, evidence, and telemetry
   checks pass.
9. The deployment record stores commit, digest, migration revision, operator,
   and rollback digest.

The choice between an App Service deployment slot and a separate staging app
depends on the live App Service SKU and isolation requirements.

## Authoritative external references

- [Azure CLI custom-container configuration](https://learn.microsoft.com/en-us/cli/azure/webapp/config/container?view=azure-cli-latest)
- [Azure App Service custom-container CI/CD](https://learn.microsoft.com/en-us/azure/app-service/deploy-ci-cd-custom-container)
