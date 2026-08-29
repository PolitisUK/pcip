# Existing-user platform administration

`scripts/bootstrap_admin.py` is only for creating a first administrator. It
will not alter an existing account. To change global platform-administrator
access for exactly one existing account, use `scripts.set_platform_admin` only
through an authorised production execution path.

First, record approval for the read-only lookup and resolve the exact internal
user ID. This command is operational only: do not expose it through an API or
run it outside an authorised production execution path.

## Approved non-interactive production path

Do not enable App Service SSH, use Kudu, retrieve a publishing profile, or copy
database credentials to a workstation or GitHub runner. The approved execution
path is the protected **Run approved PCIP production operation** GitHub Actions
workflow. It submits a validated request to a dedicated Azure Service Bus queue
after the `production` environment approval. The event-driven Container Apps
job has its own managed identity, can read only the existing `database-url` Key
Vault secret, and runs its separately approved digest-pinned worker image. The workflow must use
the dedicated `AZURE_PRODUCTION_OPERATIONS_CLIENT_ID` OIDC identity; it must
never fall back to the broader release-promotion identity.

The workflow accepts one enumerated operation only: `lookup-user-identity`.
It does not accept an arbitrary shell command, Python module, CLI flags, or SQL.
It verifies the supplied release SHA against three consecutive production
readiness responses, the supplied immutable application digest on App Service,
and the separately approved immutable worker digest and source provenance on
the Container Apps job. The supplied email is masked, is not written to
the step summary, and is carried only in the short-lived queue message; the
worker does not log it or persist it in application data.

Before first use, an infrastructure owner must separately approve and deploy
`infra/production-operations.bicep` with the digest of a release that contains
`scripts.production_operation_worker`. `imageDigest` is the independently
approved worker artifact, not the App Service image. Publish that exact digest
with the dedicated `operations-worker-sha-<revision>` tag; do not reuse the
application release's `sha-<revision>` tag. Supply
`workerProvenanceRevision` as the full commit SHA that built it, and record the
two Bicep outputs as protected environment variables
`PCIP_PRODUCTION_OPERATIONS_WORKER_DIGEST` and
`PCIP_PRODUCTION_OPERATIONS_WORKER_REVISION`. This is a one-time provisioning change:
it requires the `Microsoft.App` and `Microsoft.ServiceBus` providers, creates
an event-driven job with no ingress, a dedicated queue with local/SAS
authentication disabled, and creates a dedicated user-assigned worker identity
before the job. It grants that identity `AcrPull`, Service Bus
**Data Receiver only on that queue**, plus **Key Vault Secrets User only at the
existing `database-url` secret scope**, then attaches the same identity to the
job for ACR, Key Vault and the event trigger. This ordering prevents the job's
first revision from attempting an ACR pull before it has its required identity
access. The module also creates a dedicated operation-log workspace. The GitHub OIDC principal has Service Bus **Data Sender
only on that queue**, read-only access to the worker/App Service/ACR metadata,
and read-only access to the dedicated operation logs. It receives no Key Vault,
PostgreSQL, App Service write, SSH, or job-start permission. It must not change
PostgreSQL networking or grant GitHub database, Key Vault-secret, or
interactive-shell access.

The infrastructure owner must create the dedicated Entra workload identity and
federated credential separately. Its GitHub OIDC subject must be the exact
repository-and-`production`-environment subject issued by GitHub (normally
`repo:PolitisUK/pcip:environment:production`, unless the repository is using
GitHub's immutable-subject format). Store its application client ID only as the
protected-environment variable `AZURE_PRODUCTION_OPERATIONS_CLIENT_ID`. Do not
reuse `AZURE_CLIENT_ID`, and do not give the operations identity the existing
resource-group Contributor role. Configure the protected-environment variables
for the queue namespace, queue name, worker job name, dedicated worker identity
resource ID (`PCIP_PRODUCTION_OPERATIONS_WORKER_IDENTITY`), and dedicated Log
Analytics workspace ID from the Bicep outputs; none is a secret.

Set the protected-environment variable `PCIP_PRODUCTION_OPERATIONS_ENABLED` to
`true` only after that infrastructure and its variables are fully provisioned.
Until then, leave it unset or set it to `false`: promotion and rollback log an
explicit skip so existing releases remain unaffected. When it is `true`, a
missing worker, failed worker-artifact/provenance check, or read-back mismatch
fails the release or rollback as incomplete; it is never silently ignored.
Promotion and rollback deliberately retain the approved worker artifact rather
than replacing it with an application digest that may predate the worker. They
validate its ACR digest, its dedicated
`operations-worker-sha-<revision>` provenance tag, and the fixed event-driven
template. The dedicated tag namespace prevents an application release built
from the same revision from moving the worker provenance tag to a different
digest. The operations workflow uses the same checks.

Production promotion, rollback, and the operations workflow share the GitHub
Actions `pcip-production-control` concurrency group with cancellation disabled.
The promotion job acquires it only after staging has completed, so staging work
does not block a lookup. A lookup queued while a release or rollback is running
does not validate or enqueue until it acquires that slot, then rechecks the live
application and worker evidence. Conversely, a release or rollback waits for a
running lookup to finish. A failed release leaves the control group available
only after its cleanup has completed; any subsequent lookup performs fresh
validation. There is no Azure-side lock and the operations identity still has
no permission to alter or start the worker.

The execution sequence is:

1. Record approval for the read-only lookup and select the workflow from `main`.
2. Select `lookup-user-identity`; provide the exact email, deployed release SHA,
   immutable deployed image digest, and named operator.
3. Approve the protected GitHub `production` environment.
4. Review the returned JSON only: internal user ID, active state,
   platform-admin state, and membership IDs/roles/states.
5. Record the exact internal user ID, then run the separately authorised
   `set_platform_admin --dry-run` process below.

The workflow records its GitHub run, actor, named operator, target release,
operation, execution ID, and success/failure in the protected run summary. It
does not print the supplied email or any credential.

```bash
python -m scripts.lookup_user_identity \
  --email <email>
```

It outputs only the internal user ID, active state, current platform-admin
state, and organisation membership roles. It performs an exact normalized-email
lookup, fails closed for zero or multiple matches, starts a PostgreSQL read-only
transaction, and always rolls back rather than committing.

Then use both the verified email and internal user ID for the separately
controlled dry run:

```bash
python -m scripts.set_platform_admin \
  --email <email> \
  --expected-user-id <id> \
  --enable \
  --reason "<approved non-sensitive reason>" \
  --dry-run
```

Review the machine-readable output: it reports only the internal user ID,
active status, requested before/after state, and membership IDs/roles. It never
prints password hashes, authentication tokens, sessions, or database
credentials. Do not retrieve or log database credentials manually.

After reviewing the dry-run result, obtain separate explicit approval for the
write. Then, using an authorised production execution path, perform it:

```bash
python -m scripts.set_platform_admin \
  --email <email> \
  --expected-user-id <id> \
  --enable \
  --reason "<approved non-sensitive reason>" \
  --confirm-production-change
```

The command locks the exact user row on PostgreSQL, requires one active user,
preserves password/authentication fields and memberships, and creates an audit
event in the same transaction. It refuses ambiguous identities, missing or
mismatched IDs, inactive users, and writes without confirmation.

After a successful approved write, sign out and sign back in before verifying
the Platform administration UI. To roll back a previously approved grant,
repeat the verified lookup and dry-run steps followed by the approved command
with `--disable`. This restores only `User.is_platform_admin`; it is not a
broad database restore. Retain the approval and command output with the audit
reference.
