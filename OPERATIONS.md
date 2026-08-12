# PCIP Operations Runbook

Last verified from the repository: 2026-07-28

## Safety rules

- Treat production data and configuration as authoritative; do not infer them
  from Bicep.
- Record the running image digest and Alembic revision before any change.
- Do not expose secret values in tickets, chat, workflow logs, or inventory
  files.
- A code rollback does not automatically reverse a database migration.
- Do not run a production migration until backup recovery and forward-fix or
  downgrade behavior are understood.
- Prefer staging verification and incremental promotion.

## Ownership information still required

The on-call owner, escalation contacts, Azure subscription/resource IDs,
service-level objective, RTO, RPO, data owner, and security/privacy escalation
route cannot be determined from the repository. Add them here after approval.

## Pre-deployment inventory

Capture these read-only facts:

1. Azure account/subscription and resource group.
2. Exact Web App, plan/SKU, slots, instance count, health path, and current
   container image reference.
3. Exact ACR and the digest/timestamp/tag set for the running and last known good
   images.
4. Non-secret app settings and Key Vault reference statuses.
5. PostgreSQL server, database, version, HA, backup retention, network rules,
   storage, current Alembic revision, size, and connection count.
6. Storage account/container, network access, soft delete, Defender status, and
   managed-identity role assignments.
7. Application Insights/Log Analytics diagnostic settings, latest telemetry,
   alerts, and retention.
8. Most recent deployment, operator, source commit, and outcome.

Suggested non-secret repository-side checks:

```bash
git rev-parse HEAD
git status --short
git log --oneline --decorate -10
```

Suggested Azure checks, after replacing the explicit placeholders:

```bash
az account show --query '{subscriptionId:id,tenantId:tenantId}' -o json
az webapp show \
  --resource-group <resource-group> \
  --name <app-name> \
  --query '{name:name,state:state,host:defaultHostName,plan:serverFarmId,image:siteConfig.linuxFxVersion,health:siteConfig.healthCheckPath,alwaysOn:siteConfig.alwaysOn}' \
  -o json
az webapp config container show \
  --resource-group <resource-group> \
  --name <app-name> \
  -o json
az webapp config appsettings list \
  --resource-group <resource-group> \
  --name <app-name> \
  --query "[?name=='ENVIRONMENT' || name=='BASE_URL' || name=='TRUSTED_HOSTS' || name=='ALLOWED_ORIGINS' || name=='COOKIE_SECURE' || name=='SESSION_COOKIE_SECURE' || name=='STORAGE_BACKEND' || name=='RUN_MIGRATIONS' || name=='SEED_DEMO_DATA' || name=='ENTRA_ENABLED' || name=='LOCAL_LOGIN_ENABLED'].{name:name,value:value}" \
  -o json
```

Do not query or export secret-bearing application settings. Use Key Vault
reference status and secret version metadata rather than values.

## Release gates

All gates must pass before production promotion:

- the proposed source is reviewed and tied to a commit SHA;
- unit/integration tests pass;
- aggregate coverage is not below the agreed baseline;
- PostgreSQL empty-database upgrade and `alembic check` pass;
- dependency audit and Bandit pass;
- the release container builds and its liveness endpoint passes;
- migration SQL and production data volume impact are reviewed;
- backup and rollback digest are recorded;
- staging starts and `/health/ready` succeeds;
- login, participant portal, and evidence smoke tests pass;
- expected telemetry is visible;
- the change window and operator are recorded.

## Deployment verification

Check:

```bash
curl --fail --silent --show-error https://<app-host>/health
curl --fail --silent --show-error https://<app-host>/health/ready
```

Then verify manually with non-sensitive test records:

1. staff login and logout;
2. dashboard and permitted researcher scope;
3. create/edit validation for a disposable study or staging fixture;
4. participant invitation and re-entry behavior;
5. activity draft/submit inside its schedule;
6. evidence upload, pending/clean status, and clean-only download;
7. outbox delivery status;
8. audit event creation;
9. request, exception, dependency, and trace telemetry.

## First privileged account recovery

Use the normal **Researchers** invitation flow whenever an active owner or
administrator exists. The bootstrap command is only for an organisation with
no active privileged membership. It creates no password; the new owner must
use the existing password-reset flow or Microsoft Entra sign-in.

Run a dry-run first:

```bash
python -m scripts.bootstrap_admin \
  --organisation-name "Example Council" \
  --organisation-slug example-council \
  --name "Named Owner" \
  --email owner@example.gov.uk \
  --role owner \
  --create-organisation \
  --dry-run
```

After reviewing the dry-run, repeat it with
`--confirm-production-bootstrap` instead of `--dry-run`. The command refuses
duplicate identities, mismatched organisation names, incomplete migrations,
and any organisation that already has an active owner or administrator. Run it
from an approved operator environment with `DATABASE_URL` supplied securely;
never place the database URL or a password on the command line or in logs.

## Normal startup

Expected sequence:

1. App Service pulls the configured ACR image.
2. Entrypoint runs Alembic when enabled.
3. Uvicorn imports `app.main`.
4. Lifespan startup validates configuration, database revision, and storage.
5. The app reports ready.

Startup should fail rather than become ready if critical hosted configuration is
unsafe, PostgreSQL is unavailable/behind Alembic head, or Blob initialization
fails.

## Routine checks

Daily or per operating period:

- production `/health/ready` is successful;
- no restart loop or unexpected instance replacement is present;
- failed requests, latency, dependency failures, and availability remain within
  target;
- database connections, CPU, storage, and backup jobs are healthy;
- Blob/Defender scan failures and pending evidence age are within target;
- outbox unsent/error counts are within target;
- authentication lockouts, rate-limit audits, and webhook rejections have no
  unexplained spike;
- certificate/domain and secret-expiry warnings are clear.

Weekly:

- review audit/security events and privileged-user changes;
- verify the last backup and scheduled restore exercise;
- review dependency/security workflow status;
- reconcile orphaned evidence metadata/blobs once a reconciliation job exists;
- review data-retention candidates without executing deletion automatically.

## Incident response

### Application not ready

1. Stop further deployment actions.
2. Record the current image reference and recent deployment ID.
3. Inspect container startup logs for configuration validation, migration,
   database, Key Vault, storage, or import failures.
4. Test PostgreSQL connectivity and confirm `alembic_version`.
5. Check Key Vault references and managed-identity role assignments.
6. Check Blob container access.
7. If the failure is release-specific and schema-compatible, restore the last
   known good image digest.
8. Verify readiness and critical smoke tests; preserve logs and timeline.

### Database unavailable or migration failure

1. Do not repeatedly restart containers if each restart attempts migrations.
2. Record the failing revision and exact database state.
3. Check server health, network/firewall, credentials/Key Vault reference, locks,
   and connection exhaustion.
4. Use the migration's reviewed forward-fix/downgrade plan; do not improvise
   destructive SQL.
5. Restore only under the approved RPO/RTO plan.

### Authentication incident

1. Preserve audit and application logs.
2. Disable affected users or revoke invitations as appropriate.
3. Resetting a staff password increments `session_version` and invalidates
   existing staff sessions.
4. Rotate `SECRET_KEY` only as an organisation-wide session invalidation event;
   it logs out all signed sessions.
5. For suspected Entra compromise, coordinate tenant-side token/user controls
   and PCIP user disablement.

### Evidence or malware incident

1. Keep downloads fail-closed unless scan status is explicitly `clean`.
2. Revoke access to affected evidence and preserve metadata/audit evidence.
3. Confirm Defender tags/webhook delivery and managed-identity access.
4. Do not mark an object clean manually without the approved security process.
5. Escalate infected content according to the data/security incident procedure.

### Email failure

1. Inspect `outbox_emails` for unsent rows and errors.
2. Verify SMTP network access, credentials, TLS, sender authorization, and
   provider status.
3. Avoid repeated manual invitation generation; resending revokes the previous
   participant link.
4. Until a worker exists, replay requires an approved, audited procedure.

## Rollback

The preferred rollback target is an immutable, previously verified image digest,
not a mutable tag. The current workflow does not yet automate this.

For a schema-compatible application rollback, use the current Azure CLI
container-setting command with the explicitly recorded app/resource group and
digest:

```bash
az webapp config container set \
  --resource-group <resource-group> \
  --name <app-name> \
  --container-image-name <registry>.azurecr.io/pcip@sha256:<digest> \
  --container-registry-url https://<registry>.azurecr.io
az webapp restart \
  --resource-group <resource-group> \
  --name <app-name>
```

Then verify readiness, critical smoke tests, and telemetry. If a migration is not
backwards-compatible, the image must not be rolled back until the database
recovery plan is executed. Record the incident, digest, revision, timestamps,
and operator.

## Backup and restore

The repository Bicep requests 14-day PostgreSQL backup retention, disables
geo-redundant backup, and enables 14-day Blob/container soft delete. Live state
is unknown.

A production readiness exercise must prove:

- point-in-time PostgreSQL restore into an isolated server;
- application validation against the restored copy;
- evidence recovery within the approved retention period;
- Key Vault recovery/rotation procedure;
- measured RTO and data-loss interval compared with approved RPO;
- named owner and exercise cadence.

## Database and privacy operations

The admin retention endpoint can anonymise or delete configured participant
statuses after a configured age. Do not run it in production until the approved
privacy policy defines eligibility, legal holds, evidence and message handling,
audit retention, and verification. Take a backup, preview affected counts through
an approved report, execute with named authorization, and retain the audit record.

### Controlled production Alembic baseline

Read-only verification on 2026-07-28 and 2026-07-29 established that production
matches revision `0005` across tables, columns, foreign keys, primary/unique
indexes, and application indexes. There is one organisation and one user, with
no duplicate normalised email or Entra identity. The database lacks only
Alembic's version table.

The baseline is a production metadata operation and must be performed separately
from application deployment:

1. create an Azure PostgreSQL on-demand backup and verify it completed; where
   the live Burstable tier rejects on-demand backups, identify and record the
   latest completed automatic backup instead;
2. confirm the Web App remains on the recorded `0.6.0` image;
3. in one database transaction, create Alembic's version table and insert
   `0005`; if the table already exists, stop and investigate instead;
4. query the marker and application liveness/readiness;
5. record backup name, UTC time, operator, previous image tag/digest, and result.

Do not run `alembic upgrade` as the baseline operation. Revision `0006` is a
separate additive release migration and must remain unapplied until its
candidate application build is staged and rollback has been tested.

For the planned production baseline, Azure rejected an on-demand backup with
`CustomerOnDemandBackupCannotBePerformedOnBurstableServer`. The recorded
recovery point is automatic backup `backup_639208424185897431`, completed
2026-07-28 at 13:33:39 UTC. This limitation is another reason to review the
production database tier and recovery design before wider use.

The controlled baseline transaction then completed successfully and returned
`alembic_revision=0005`. It created only `alembic_version` and did not execute
revision `0006` or alter an application table.

Post-baseline verification returned HTTP `200` from live `/health`. Live
`/health/ready` returned HTTP `404`; therefore App Service must not be pointed
at that path until a staged hardened image proves the endpoint. The live
liveness payload also exposed environment and storage-backend values, which the
hardened candidate removes.

## Current verification baseline

Repository and read-only production verification on 2026-07-28:

- 80 tests passed;
- application coverage: 81%;
- Ruff undefined/unused-name checks passed; the broader default profile has 170
  recorded legacy findings and is not represented as clean;
- clean empty PostgreSQL migration verified in CI design and clean empty SQLite
  migration verified locally;
- dependency set locked and application dependencies audited;
- Bandit medium/high findings: none in the prior clean run;
- local Docker smoke test: unavailable because this workspace has no Docker
  daemon;
- the Web App was in Azure `Running` state, but had no configured health path
  and Always On was disabled;
- the configured image tag was `pcip:0.6.0`, resolving in ACR to
  `sha256:6cd7e60983190f70143e2e64dfb34588858f743a142c5ebb7f47bd727af346dc`;
- `RUN_MIGRATIONS=false`;
- `SEED_DEMO_DATA` was absent and therefore inherited the unsafe application
  default of `true`; hardened code now rejects that in production;
- PostgreSQL 16 was Ready on `Standard_B1ms`, with 14-day backups, public
  network access, HA disabled, and geo-redundant backup disabled;
- the 9,399 kB database is schema-verified as equivalent to revision `0005`
  and now records `0005` in `alembic_version`;
- exact running digest/source commit, logs/telemetry, plan SKU/scale, alerts,
  and restore evidence remain outstanding.
