# Privacy Management Features (Technical Scope)

This document describes technical privacy controls implemented in the platform. It intentionally separates product capabilities from organisational/legal policy obligations.

## Supported GDPR-Aligned Technical Functionality

### 1. Participant data export
- Admin-only export endpoint: `GET /participants/{participant_id}/export`
- Produces structured JSON containing:
  - participant profile fields
  - study enrolments
  - activity responses
  - participant messages
  - participant invitations
  - evidence metadata
- Export actions are audit logged with action `privacy.participant_exported`.

### 2. Participant deletion workflow
- Admin-only two-step workflow:
  - `POST /participants/{participant_id}/privacy/delete-request`
  - `POST /participants/{participant_id}/privacy/delete-execute`
- Workflow confirmation token is server-side and short-lived per browser session.
- Execution is audit logged.

### 3. Anonymisation fallback
- If a participant has related records needed for research integrity/history,
  hard delete is blocked and anonymisation is used.
- Auto mode selects:
  - hard delete when safe (no related records)
  - anonymise when related records exist
- Anonymisation actions are audit logged with action `privacy.participant_anonymised`.

### 4. Configurable retention controls
- Settings:
  - `PRIVACY_RETENTION_DAYS`
  - `PRIVACY_RETENTION_STATUSES`
  - `PRIVACY_RETENTION_ACTION` (`delete` or `anonymise`)
- Admin-only retention execution endpoint:
  - `POST /privacy/retention/apply`
- Retention execution and participant-level outcomes are audit logged.

### 5. Administrator-only privacy functions
- Export, deletion workflow, and retention application are restricted to `owner` and `admin` roles.

## Unsupported Organisational/Policy Requirements

The platform does **not** implement organisational policy decisions. Examples include:
- legal basis determination and documentation
- data-processing agreement management
- DPIA completion and governance approvals
- records of processing activity (ROPA) policy ownership
- jurisdiction-specific legal interpretation and counsel sign-off
- incident response policy, regulator notifications, and legal communications
- staff training policy and access governance process design

These must be addressed by organisational policy, legal counsel, and operational governance outside the application code.
