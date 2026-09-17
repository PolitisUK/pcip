# Google Play reviewer access

Citizen Centric normally uses invitation-based participant access. The
invitation, consent and one-time app-code journey remains the default for all
ordinary participants.

For a separately authorised fictional review participant, an organisation
owner or administrator can provision one reusable app credential from that
participant's dossier. The workflow requires an accepted invitation and active
consent in the intended study. It stores only a salted password hash and can be
rotated or disabled; rotation/disable revokes password-authenticated sessions.

Use the following wording in Google Play Console, supplying the actual
credentials only in Play Console's protected reviewer-access fields:

> Citizen Centric normally uses invitation-based participant access. For Google
> Play review, select **Username & password** on the app sign-in screen and use
> the dedicated reusable review credentials supplied here. These credentials
> provide access only to a fictional demonstration study and do not require
> email access, an invitation link, OTP, or one-time access code.

Do not place a reviewer password, invitation link, access code, session token,
or customer participant data in source control, documentation, issue trackers,
or test fixtures. Provisioning a live review credential is a separate,
authorised production operation and is not part of a software release.
