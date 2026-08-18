# Participant-data relationship inventory

This engineering inventory describes the current active-system deletion path. It is not a legal retention decision: controller-specific exceptions must be documented before study launch.

| Relationship | Classification | Lifecycle action | Notes |
| --- | --- | --- |
| `participants` | Identifiable participant profile | DELETE for organisation-scoped account deletion | The dedicated privacy-request record clears its live participant link before the profile is removed. |
| `study_enrolments` | Study participation | DELETE for deletion; WITHDRAW for withdrawal only | Withdrawal is effective for access control immediately. |
| `participant_invitations` | Invitation/session link | REVOKE on withdrawal; DELETE on deletion | Active participant sessions are revoked first and removed with deletion. |
| `public_auth_sessions` | Participant API/portal session | REVOKE on withdrawal; DELETE on deletion | No future participant write can use a revoked session. |
| `activity_responses` | Draft/submitted Study Data | DELETE | Includes drafts and submitted responses in the requested scope. |
| `evidence_files` and live storage objects | Participant-uploaded media | DELETE | Storage is removed before the row; failure leaves the request `FAILED_RETRYING`. |
| `participant_messages` | Participant/research-team correspondence | DELETE | Includes participant-scoped visible and internal message rows in the requested scope. |
| `research_analysis_suggestions` | Participant-linked AI/research derivative | DELETE | Direct source-response derivatives are deleted. |
| `evidence_confidence_assessments`, `research_themes` linked to source | Participant-linked research derivative | DELETE | Removed where they reference deleted response/suggestion IDs rather than being re-labelled anonymous. |
| `audit_events` that identify the participant | Identifiable operational metadata | DELETE | A dedicated minimised privacy lifecycle record replaces content-bearing/general participant audit entries. |
| `participant_privacy_requests` | Minimal accountability evidence | RETAIN WITH REASON | Stores status, timestamps and deletion categories only; no content or free-text reason. |
| `outbox_emails` | Operational mail queue | DELETE only where a verified participant/study link exists | Historic rows have no participant foreign key and may contain a recipient address, invitation link/token, study title or other message body. They are never deleted by recipient matching. Existing unlinked rows receive a 30-day forward expiry on adoption, rather than bulk deletion. New participant invitation rows are prospectively linked to participant/study and expire after 30 days; linked rows are deleted with the participant lifecycle. |
| Backups | Protected historical copies | RETAIN UNTIL EXPIRY | Current production evidence: PostgreSQL PITR 14 days; Blob soft-delete and container soft-delete 14 days; blob versioning and App Service backups disabled. Not active-system research access. Deletion controls are reapplied after disaster recovery where technically feasible. |

The current data model has organisation-scoped `Participant` records rather than a cross-organisation participant identity. An account-deletion request therefore applies to all studies attached to that participant record in the authenticated organisation; it does not correlate email addresses across organisations.
