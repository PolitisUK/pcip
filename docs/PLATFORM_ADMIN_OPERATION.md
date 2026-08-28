# Existing-user platform administration

`scripts/bootstrap_admin.py` is only for creating a first administrator. It
will not alter an existing account. To change global platform-administrator
access for exactly one existing account, use `scripts.set_platform_admin` only
through an authorised production execution path.

First, record approval for the read-only lookup and resolve the exact internal
user ID. This command is operational only: do not expose it through an API or
run it outside an authorised production execution path.

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
