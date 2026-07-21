# PCIP v0.3.0 — Participant Portal and Evidence Collection

This cumulative release includes the v0.1 foundation, v0.2 research management, the v0.2.1 quality fixes, and the first complete participant evidence workflow.

## Added

- Participant activity portal using secure study links
- Consent-to-portal handoff
- Draft and submitted activity responses
- Text, rating, slider, GPS and file/media response handling
- Photo, audio, video and general file evidence storage
- Researcher/participant two-way messaging
- Internal researcher notes hidden from participants
- Participant response summaries
- Study activity submission counts
- Participant invitation resend and revoke controls
- Full project, study and activity editing
- CSV participant import
- Study demographic-question configuration and participant demographic JSON storage
- Pagination for participants, audit events and email outbox
- Password-reset request and completion flow
- Additive SQLite migration for the new study configuration field

## Quality and security notes

- All researcher data remains organisation-scoped.
- Evidence downloads require an authenticated researcher in the same organisation.
- Participant links remain revocable and time-limited.
- Uploads are stored outside the static web directory with randomised filenames.
- The automated suite contains 11 passing workflow tests.

## Still required before commercial release

- Malware scanning and cloud object storage for uploads
- Participant account authentication or passwordless session hardening
- MFA and Microsoft Entra SSO
- Fine-grained study-level permissions
- Formal WCAG audit, penetration test, load test and data-protection review
- Background jobs for email and media processing
- Database migrations using Alembic
