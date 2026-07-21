# PCIP v0.4.0 - Enterprise Foundation

This cumulative release adds the first enterprise and assurance controls to the participant research platform.

## Added

- Study-level team access with view and edit permissions.
- Tenant-aware permission enforcement on study workspaces, activity management, participant recruitment, messaging and evidence downloads.
- Security header middleware, trusted-host validation and same-site session hardening.
- Upload extension allow-listing and configurable file-size limits.
- SHA-256 evidence integrity hashes.
- Malware-screening integration with optional ClamAV support and EICAR test-signature rejection.
- Storage abstraction for protected local evidence storage, ready for a future cloud adapter.
- Alembic migration infrastructure and an enterprise-foundation migration.
- Accessibility improvements including a skip link, improved labels, visible keyboard focus and reduced-motion support.
- Correct display of saved participant draft text rather than raw JSON.
- Expanded automated assurance tests.

## Verification

- 14 automated tests passed.
- A fresh database was successfully created through `alembic upgrade head`.

## Still required before production

- Azure Blob or S3 storage adapter and production credentials.
- Production antivirus service and an operational quarantine workflow.
- Microsoft Entra ID SSO and MFA.
- Independent accessibility and penetration testing.
- Production monitoring, backups, disaster recovery and support procedures.
- Data protection and legal approval.
