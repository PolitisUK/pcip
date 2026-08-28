# Existing-user platform administration

`scripts/bootstrap_admin.py` is only for creating a first administrator. It
will not alter an existing account. To change global platform-administrator
access for exactly one existing account, use `scripts.set_platform_admin` only
through an authorised production execution path.

First record the approval and run a read-only identity check:

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

After verifying the exact ID, recording the approval, and using an authorised
production execution path, perform the approved write:

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

To roll back a previously approved grant, repeat the verified two-step process
with `--disable`. This restores only `User.is_platform_admin`; it is not a
broad database restore. Retain the approval and command output with the audit
reference.
