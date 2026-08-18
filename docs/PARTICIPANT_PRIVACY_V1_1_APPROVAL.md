# Participant privacy v1.1 approval pack

**Status: APPROVED — Politis Ltd owner legal/privacy approval recorded for PR #77 on 18 August 2026.**

This pack is a plain-English adoption record for the controlled Privacy Notice
v1.1, Data Processing Agreement v1.1 and Data Retention and Deletion Policy
v1.0. It records implemented behaviour and known limits; it does not replace a
controller's study-specific legal, ethics or retention decision.

## What a participant can choose

- **Withdraw only:** immediately ends access to the current study and prevents
  further collection. It does not itself delete material already collected.
- **Withdraw and delete study data:** ends access and deletes identifiable,
  active-system data for the current study when no documented controller
  retention exception applies.
- **Delete account:** ends all Citizen Centric study access for the
  organisation attached to the authenticated participant record and deletes
  identifiable, active-system account and study data in that organisation.

All three actions require a separate unchecked confirmation. The app does not
offer a participant-selectable anonymisation option. A participant never
supplies an identifier to select another person's request.

## What is actively erased

For a completed deletion, the platform removes in-scope participant profile
data, enrolments, invitations, sessions, responses and drafts, messages,
evidence records and live media objects, prospectively scoped outbox emails,
and directly linked research-analysis derivatives. Storage deletion happens
before the evidence row is removed. A storage or database failure remains
`FAILED_RETRYING`; the participant is not told deletion is complete.

## What may remain

- Irreversibly anonymised or aggregated information that cannot reasonably be
  linked back to the participant may remain for the approved research purpose.
  Pseudonymised information remains personal data and is not treated as
  anonymous by this policy.
- A minimised privacy lifecycle record may remain for accountability. It has no
  participant content or free-text reason; account deletion clears its live
  participant link.
- Protected production backup copies can remain for up to **14 days**. Current
  evidence is Azure PostgreSQL PITR retention of 14 days and Azure Blob and
  container soft-delete retention of 14 days. Blob versioning and App Service
  backup are not enabled. Backup systems are not ordinary research-access
  systems. If disaster recovery restores a copy containing deleted data, the
  deletion controls must be reapplied before normal processing resumes.
- Historic `outbox_emails` rows are not reliably participant-scoped. Code
  evidence shows they may contain a recipient address, invitation link/token,
  study context and message body. They are not deleted by email matching. New
  participant invitation rows carry verified participant/study links and a
  30-day technical retention expiry; those linked rows are deleted with the
  participant lifecycle. Existing unlinked rows receive a 30-day forward
  expiry on adoption, rather than a bulk deletion.

## Controller retention mechanism

Before study launch, the controller must explicitly record either `None` or a
specific deletion/retention exception. A documented exception causes deletion
to stop in `requires_controller_review`; it cannot be bypassed by the retry
path. The controller must record the lawful/research/security basis, minimum
data retained, restricted use and retention period outside this generic pack.

## Apple account deletion position

The mobile app provides a clear in-app initiation and confirmation path for
organisation-scoped account deletion. Apple’s current guidance says apps with
account creation must allow users to initiate account deletion in the app and
keep users informed where completion takes time. This implementation satisfies
the initiation requirement; legal review must confirm the statements and
exceptions for the planned distribution context. Source: [Apple account
deletion guidance](https://developer.apple.com/support/offering-account-deletion-in-your-app/).

## Approval statement

**Politis Ltd approval recorded:**

> I approve adoption of the Citizen Centric Privacy Notice v1.1 (effective 18
> August 2026), Data Processing Agreement v1.1 (effective 18 August 2026) and
> Data Retention and Deletion Policy v1.0 (effective 18 August 2026), subject
> to the documented controller-specific study governance and retention
> exceptions.

| Approval role | Name | Signature / approval reference | Date |
| --- | --- | --- | --- |
| Politis Ltd authorised approver | Owner-supplied Politis Ltd approval | PR #77 owner legal/privacy approval | 18 August 2026 |
| Legal reviewer | No separate identity supplied | The owner approval records the legal/privacy position; no separate reviewer is asserted | 18 August 2026 |
| Data protection / controller representative | _Required where applicable_ | _Required_ | _Required_ |
