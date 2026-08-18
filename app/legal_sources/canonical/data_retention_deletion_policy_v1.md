# Citizen Centric Data Retention and Deletion Policy

| Version | Effective date | Classification |
| --- | --- | --- |
| 1.0 | 18 August 2026 | Internal governance / customer evidence |

## Active-system erasure

On a confirmed participant withdrawal plus deletion request, Citizen Centric first revokes access, invitations and participant sessions. The deletion lifecycle then removes participant-scoped active-system responses, drafts, messages, evidence records, live media objects, enrolments and participant-linked research derivatives within the requested scope. A request is not marked complete while a required live media deletion has failed.

## Retry and verification

Storage or database failures are retained as `FAILED_RETRYING` with a retriable flag and minimised error metadata. A controlled retry is idempotent. Completion records only deletion categories and timestamps; they do not preserve participant content or free-text reasons.

## Retention exceptions

An exception requires a documented controller lawful basis or a specific legal/security/accountability purpose, the minimum necessary data, restricted access, a defined retention period, and removal from ordinary research use. Submitted research content is not retained merely “for audit”.

## Anonymisation and pseudonymisation

Irreversibly anonymised aggregate information that cannot reasonably be linked back to a participant is no longer personal data. Pseudonymised information remains personal data and remains in scope for deletion controls.

## Backups and disaster recovery

Deletion applies to active systems. Protected backups expire through the approved backup-retention cycle and are not used for ordinary research access. If a backup containing deleted data is restored for genuine disaster recovery, outstanding and completed deletion controls must be reapplied before normal service resumes where technically feasible. The deployment-specific maximum backup retention period must be recorded in the production operations register; this policy does not invent one.

## Controller instructions

For Study Data, the controller documents any lawful retention/research exemption before study launch. Politis Ltd implements controller instructions as processor and records only minimised deletion-lifecycle evidence.
