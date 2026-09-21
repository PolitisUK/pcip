# PCIP release promotion runbook

This is the production release procedure for Citizen Centric. It supersedes
using `deploy-azure.yml` for production; that legacy workflow remains available
for non-production infrastructure only.

## Mandatory controls

Before a release, a named release operator records the approved window, the
rollback decision owner, the current production Alembic revision, a verified
Azure PostgreSQL recovery point, the current production image digest and
rollback digest, and the candidate commit SHA. The candidate commit must
already be merged into `main` and its required CI must be green.

Record the window as separate `release_window_start`, `release_window_end` and
`release_window_timezone` inputs. Start and end use the strict local format
`YYYY-MM-DDTHH:MM:SS`; the timezone is an IANA name such as `Europe/London`.
The start is inclusive and the end is exclusive. Ambiguous or nonexistent
local times around daylight-saving transitions are rejected, so the approver
must choose unambiguous timestamps.

Configure protected GitHub environments before first use:

- `release-controls` protects release evidence validation;
- `staging` protects deployment of the isolated staging app;
- `production` has a required reviewer and protects promotion and rollback.

Configure these non-secret repository variables with the inventory-verified
resource names: `PCIP_STAGING_APP`, `PCIP_STAGING_ACR`,
`PCIP_PRODUCTION_APP`, `PCIP_PRODUCTION_ACR`, and
`PCIP_PRODUCTION_DATABASE_SERVER`. Keep credentials in Key Vault or GitHub
environment secrets; never place them in workflow inputs or repository files.

## Migration decision

The release operator obtains the current revision through the protected,
fixed `get-alembic-revision` production operation and records it in the
promotion request. This operation performs only the approved read-only
Alembic-version lookup; it is not a general database-query facility. Do not
substitute a historical revision. Any legacy migration-specific precondition
evidence remains applicable only where the candidate contains that migration.

```sql
SELECT version_num FROM alembic_version;

SELECT lower(trim(email)) AS normalised_email, count(*) AS duplicate_count
FROM users
GROUP BY lower(trim(email))
HAVING count(*) > 1;
```

- `0006`: data-transforming. It backfills organisation memberships and creates
  a unique normalised-email index; duplicate normalised email addresses block
  the migration and require manual review.
- `0007`: non-destructive partial unique index.
- `0008`–`0011`: additive tables and indexes.
- `0012`: additive columns with safe defaults.
- `0013`: additive user flag with a safe default.
- `0014`: additive methodology-configuration table and provenance columns.

The schema changes are backward-compatible for the prior application because
they add data only. They are not treated as database-downgrade-safe: an
application rollback keeps the schema at its upgraded revision. A database
restore uses the verified Azure recovery point only when an approved recovery
decision requires it.

## Stage and promote

Run **Promote PCIP release candidate** from `main` with a full merged commit
SHA and all release evidence. The workflow:

1. validates the source is an ancestor of `main`;
2. builds one candidate in the staging registry with OCI source labels;
3. resolves and records its immutable digest;
4. deploys that digest to the isolated staging app, applies migrations
   fail-closed, and verifies health, readiness, and public legal routes;
5. when explicitly requested and approved by the protected `production`
   environment, re-checks the approved window against the current UTC clock,
   imports the same digest into the production registry and promotes it; and
6. verifies sustained readiness and the public production legal routes.

No workflow uses a mutable image tag as the deployed image reference.

Staging may complete before the approved production window. Production fails
closed before its first configuration mutation and re-checks the window at the
artifact-import and application-mutation boundaries. A queued or late
environment approval cannot bypass the check. If the end has passed, the run
reports `Production release window has expired. Obtain a new approved release
window.` Safety cleanup that restores `RUN_MIGRATIONS=false` is deliberately
not blocked by window expiry.

The supplied recovery-point name and rollback digest are verified against Azure
before production promotion. Listing a recovery point is not a restore test:
before the first release under this runbook, the rollback decision owner must
authorise a point-in-time restore into an isolated temporary server and record
that the restored database accepts a read-only schema and readiness check. Do
not restore over the production server.

## Rollback

Roll back the application with **Roll back PCIP production release**, supplying
the previously verified immutable production digest, named operator, rollback
decision owner, and incident/change reference. The workflow disables automatic
migrations, points the app at that digest, restarts it, and verifies readiness.

Application rollback does not roll back the database. If the incident requires
database recovery, the rollback decision owner authorises a point-in-time
restore to the recorded Azure recovery point. Assess uploads created during the
release window before restoring; storage evidence is not silently deleted by an
application rollback.
