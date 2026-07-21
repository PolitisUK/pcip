# Changelog

## 0.5.0
- Added Azure Blob Storage managed-identity provider.
- Integrated Microsoft Defender for Storage scan states, Event Grid webhook and clean-only downloads.
- Added user-delegation SAS downloads, Azure Bicep infrastructure and CI workflow.
- Added migration 0002 for Azure evidence metadata.


## 0.2.0 — Research Management

### Added
- Study records within projects, with methodology and lifecycle status.
- Participant directory with references, contact details, tags, consent and recruitment state.
- Participant search and filters.
- Study enrolment and recruitment tracking.
- Secure participant invitation links with 14-day expiry.
- Invitation delivery through the existing SMTP/outbox service.
- Invitation open and acceptance timestamps.
- Consent capture when a participant accepts an invitation.
- Activity builder supporting text, choice, rating, slider, media, GPS, ranking and file response types.
- Relative activity release and due-day scheduling.
- Research-management dashboard metrics.
- Project, study and participant detail workspaces.
- Expanded tenant-scoped audit events and automated tests.

### Retained from 0.1.0
- Multi-tenant organisation foundation.
- Researcher authentication and role controls.
- Researcher invitations and account activation.
- Project management, audit log, SMTP outbox, Docker support and PostgreSQL-ready configuration.

## 0.2.1 - Quality and interface review
- Improved navigation, responsive tables and observer-mode presentation.
- Added stricter form and lifecycle validation.
- Corrected participant invitation-open tracking.
- Improved login and invitation activation UX.
- Added destructive-action confirmation and quality review documentation.

## 0.3.0

- Added participant portal, draft and submitted responses.
- Added evidence uploads and protected researcher downloads.
- Added two-way messaging and internal notes.
- Added invitation resend/revoke controls.
- Added project, study and activity editing.
- Added CSV participant import and pagination.
- Added password reset workflow.
- Expanded automated test suite to 11 passing tests.

## 0.4.0

- Added study-level access assignments and enforcement.
- Added secure evidence validation, hashing and malware-screening integration.
- Added trusted-host and security-header middleware.
- Changed session cookies to SameSite Strict.
- Added Alembic migration infrastructure.
- Improved keyboard, screen-reader and reduced-motion support.
- Fixed participant draft responses displaying as raw JSON.
- Expanded the test suite to 14 tests.

## 0.6.0

- Added Microsoft Entra ID researcher sign-in.
- Added external identity linkage and login audit information.
- Added Azure Container Registry and PostgreSQL Flexible Server to Bicep.
- Added Key Vault references and managed-identity role assignments.
- Added GitHub OIDC deployment automation.
- Added automatic Alembic migration execution.
- Disabled demonstration data seeding in Azure deployments.
