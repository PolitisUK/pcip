# PCIP v0.2.1 Quality Review

This maintenance release rechecks the v0.1.0 foundation and v0.2.0 research-management increment.

## Corrected

- Added an active state to the left navigation.
- Improved small-screen navigation and horizontal table handling.
- Hid editing forms and destructive controls from observer accounts.
- Added a visible observer-mode notice.
- Removed pre-filled passwords from the login form.
- Corrected researcher invitation activation wording.
- Added confirmation prompts to destructive actions.
- Prevented expired or revoked participant links from being recorded as opened.
- Added server-side validation for roles, statuses, methodologies, communication preferences and activity types.
- Prevented due dates from preceding release dates.
- Required at least two options for choice and ranking activities.
- Prevented duplicate live researcher invitations.
- Added clearer empty states and keyboard-focus styling.

## Confirmed limitations / planned increments

The following are not defects in v0.2.1; they remain planned product work:

- Participant activity completion and draft saving.
- Evidence and media upload storage.
- Two-way participant messaging.
- Project, study and activity editing beyond lifecycle status changes.
- Bulk participant import.
- Demographic field builder.
- Invitation resend/revoke controls for participant invitations.
- Pagination for large datasets.
- Password reset, MFA and SSO.
- Full accessibility audit and independent security testing.
