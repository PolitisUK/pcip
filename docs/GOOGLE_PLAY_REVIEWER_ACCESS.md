# Google Play and Apple App Review access

Citizen Centric normally uses invitation-based participant access. The
invitation, consent and one-time app-code journey remains the default for all
ordinary participants.

For a separately authorised fictional review participant, an organisation
owner or administrator can provision one reusable app credential from that
participant's dossier. The participant must first be explicitly marked as a
fictional store-review participant; names, email addresses, references and
numeric IDs never confer this status. For that designated participant only,
the credential can be bound to one active, unexpired invitation before consent.
It stores only a salted password hash and can be rotated or disabled;
rotation, disablement or removal of the reviewer designation revokes
password-authenticated sessions.

Pre-consent password authentication is not consent and does not accept the
invitation. It creates a session limited to the invitation's study identity,
the exact bound study information/privacy/consent documents, consent submission
and logout. Activities, responses, evidence, messages, history and study
switching remain unavailable until that invitation's normal consent flow has
completed. Each additional study requires its own accepted invitation and
study-bound consent. The ordinary invitation and one-time-code flow is
unchanged, and no one-time app code is issued before consent.

Use the following wording in Google Play Console, supplying the actual
credentials only in Play Console's protected reviewer-access fields:

> Citizen Centric normally uses invitation-based participant access. For Google
> Play review, select **Username & password** on the app sign-in screen and use
> the dedicated reusable review credentials supplied here. On first sign-in,
> review the fictional study's information and privacy documents and complete
> its consent screen. The same credentials then provide access only to that
> fictional demonstration study and do not require email access, an invitation
> link, OTP, or one-time access code.

Do not place a reviewer password, invitation link, access code, session token,
or customer participant data in source control, documentation, issue trackers,
or test fixtures. Provisioning a live review credential is a separate,
authorised production operation and is not part of a software release.
