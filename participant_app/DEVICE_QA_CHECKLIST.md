# Participant mobile device QA

Run these checks with a synthetic participant on one recent iPhone and one
recent Android device. Do not use real participant material.

| Check | Expected result |
| --- | --- |
| A. Install and launch | The debug app installs, launches, and presents the secure invitation screen. |
| B. Invitation and session | A valid invitation creates a session; invalid or expired invitations show a clear error without exposing credentials. |
| C. Consent | Required consent is explained, needs explicit confirmation, and gates the participant home until accepted. |
| D. Activities and text | Activities load; a text draft survives navigation; a submitted response is confirmed and appears in history. |
| E. Offline and reconnect | An unsent text response remains visible, retries after reconnect, and creates exactly one confirmed submission. |
| F. Messages and reply | Messages load, detail is readable, and a reply is confirmed or shows a recoverable error. |
| G. Photo capture and library | Camera and library permissions are requested only on use; a selected photo can be previewed, removed, uploaded, and shows a clear processing state. |
| H. Document picker | A supported document can be selected, its name and size are shown, and upload processing is understandable. |
| I. Voice diary | Microphone permission is requested only on use; a recording can be stopped, played, deleted, or uploaded with a clear status. |
| J. Withdrawal | The consequences and confirmation are clear; a confirmed request updates access only as authorised by the server. |
| K. Deletion request | The request is described as a request, requires confirmation, and shows server acknowledgement without promising immediate deletion. |
| L. Logout and recovery | Logout returns to the invitation screen and a new session cannot access the previous participant's cached material. A valid session restores after restart. |
| M. Accessibility spot check | VoiceOver/TalkBack reads controls and status changes meaningfully; enlarged text remains usable; status is not colour-only. |
| N. Permission-denied flows | Camera, photo-library, microphone, and picker denial leave the app usable with a clear retry or alternative action. |
| O. Background and resume | Returning from the background retains unsent text/media state and performs only safe queue replay after a confirmed session. |

## Device QA evidence

Run date: 2026-08-15. Authenticated QA used an isolated local SQLite backend,
ephemeral local storage, and synthetic `MOBILE-QA-*` participants only. No
production endpoint, credentials, or participant material was used.

| Target | Model and OS | Result |
| --- | --- | --- |
| iOS simulator | iPhone 17 Pro, iOS 26.5 | PARTIAL: unsigned debug app built, installed, and launched. Authenticated interaction was blocked when the local CoreSimulator service became unavailable. |
| Android emulator | Google APIs ARM64 emulator, Android 16 / API 36 | PASS: debug app installed and authenticated against the isolated backend. Session recovery, consent, activities, profile, preferences, messages, withdrawal, and deletion acknowledgement were exercised. |

| Journey | iOS simulator | Android emulator |
| --- | --- | --- |
| A. Invitation, consent and text activity | BLOCKED: CoreSimulator service became unavailable before authenticated interaction | PASS: real invitation exchange, consent gating, activity load, local draft, submit, and history confirmation. |
| B. Session recovery, profile and preferences | BLOCKED: CoreSimulator service became unavailable before authenticated interaction | PASS: a stored session restored after force-stop/relaunch; profile and communication preference update confirmed by the backend. |
| C. Offline text/reconnect | BLOCKED: authenticated interaction automation could not complete the consent-selection gesture in CoreSimulator. | PASS: an isolated, temporary HTTPS tunnel was used; the service was stopped for submission, then restored. The app retained the text locally, replayed on resume, and the isolated service recorded exactly one submission. |
| D. Messaging | BLOCKED: CoreSimulator service became unavailable before authenticated interaction | PASS: synthetic research-team message opened successfully and a participant reply was accepted. Read/unread is NOT SUPPORTED by the backend. |
| E. Photo capture and library | PHYSICAL DEVICE REQUIRED | PARTIAL: Android Photo Picker, preview/remove UI, backend upload, and processing copy passed using a synthetic image. Camera capture and production permission recovery require a physical device. |
| F. Document picker | BLOCKED: requires authenticated simulator interaction | PASS: Android system document picker selected a synthetic PDF, displayed filename/size, and received backend upload acknowledgement. |
| G. Voice diary | PHYSICAL DEVICE REQUIRED | PHYSICAL DEVICE REQUIRED: Android microphone permission denial and retry were verified. The emulator did not provide reliable recording/playback evidence. Participant-facing transcription is NOT SUPPORTED by the backend. |
| H. Withdrawal | BLOCKED: CoreSimulator service became unavailable before authenticated interaction | PASS: cancellation and explicit confirmation were exercised using an isolated synthetic study; server acknowledgement was shown. |
| I. Deletion request | BLOCKED: CoreSimulator service became unavailable before authenticated interaction | PASS: cancellation and explicit confirmation were exercised using an isolated synthetic participant; server acknowledgement was shown. Status lookup is NOT SUPPORTED by the backend. |
| Accessibility, permission and background/resume checks | PARTIAL: session restoration and scaled layout were visible; screen-reader and hardware permission tests require a physical device. | PARTIAL: semantic labels and scaled layout were visible; background/resume replay passed with queued text, while TalkBack, OS permission prompts, and media controls require device QA. |

Only disposable synthetic QA data was created. No production endpoint was used.

## Authenticated QA notes

- The Android run used a compile-time debug-only local transport allowance for
  `localhost`/`10.0.2.2`; release and profile builds still reject HTTP.
- Timestamps returned by the service are now rendered as participant-readable
  local date/time values rather than raw ISO strings.
- A real device remains required for camera, photo-library, microphone,
  recording/playback, permission denial/recovery, and assistive-technology
  checks. Device offline/reconnect confirmation also requires a trusted HTTPS
  QA endpoint.

## Branding verification

Run date: 2026-08-15. The approved web-product assets
`app/static/citizen-centric-logo.png` and
`app/static/citizen-centric-logo-compact.png` are the source for the Flutter
onboarding logo and native application mark.

| Check | iOS simulator | Android emulator |
| --- | --- | --- |
| In-app approved logo | PASS: full approved logo shown on the invitation screen; no plain-text product title remains. | PASS: full approved logo shown on the invitation screen; no plain-text product title remains. |
| Launcher icon | PASS: approved compact Citizen Centric mark shown with the `Citizen Centric` display name. | PASS: approved compact Citizen Centric mark shown with the `Citizen Centric` display name. |
| Branded launch treatment | PASS: launch asset compiled from the approved compact mark. | PASS: launch asset compiled from the approved compact mark. |

Device QA defect fixed: Android's application label still exposed the scaffold
name. It now uses the established `Citizen Centric` display name in `0345640`.

## Invitation sign-in correction

Run date: 2026-08-15. The PCIP participant API accepts only an invitation
token at `POST /api/v1/participant/session/exchange`; the invitation is already
bound to the participant email on the server. The mobile onboarding screen now
shows only **Invitation code** and does not expose a service-address, email, or
password field. Invalid and expired tokens use the same participant-safe error.

| Check | Result |
| --- | --- |
| Participant invitation flow | PASS: invitation code only; session remains server-authorised. |
| Participant email sign-in | NOT SUPPORTED: email is not part of the participant API contract. |
| Participant forgot password | NOT APPLICABLE: the existing password-reset route is for staff accounts. |
| Mobile invitation deep link | NOT SUPPORTED: PCIP web invitations use `/join-study?token=…`; no approved iOS Universal Link or Android App Link association is configured. Manual invitation-code entry remains available. |
| Service endpoint control | PASS: production accepts only a build-configured HTTPS PCIP API base. Debug QA overrides are build-time only and cannot be selected by a release build. |

| Platform | Onboarding visual QA | Result |
| --- | --- | --- |
| iOS simulator | iPhone 17 Pro, iOS 26.5 | PASS: rebuilt, installed, and launched; approved logo and one invitation-code field shown with no participant-facing endpoint field. |
| Android emulator | Google APIs ARM64, Android 16 / API 36 | PASS: rebuilt, installed, and launched; approved logo and one invitation-code field shown with no participant-facing endpoint field. |

The release default is the approved production `BASE_URL` defined by the Azure
deployment workflow (`https://citizencentric.co.uk`). A signed-build pipeline
may set the identical `PCIP_API_BASE_URL` explicitly; no endpoint is shown to,
or accepted from, a participant.

## Final trusted-HTTPS and hardware QA boundaries

Run date: 2026-08-15. The documented legacy staging host did not resolve and
production was not used. An isolated local PCIP instance with a disposable
SQLite database, ephemeral storage, and synthetic participants was exposed only
for this QA run through a temporary HTTPS tunnel. It was removed after testing.
The tunnel confirmed the release HTTPS transport path without using production
data or credentials.

No physical iOS or Android device was connected. The available iPhone 17 Pro
(iOS 26.5) and Android API 36 targets are simulators/emulator only.

| Final QA item | iOS simulator | Android emulator |
| --- | --- | --- |
| Trusted HTTPS Journey C: offline → reconnect → one submission | BLOCKED: CoreSimulator automation could not complete the consent-selection gesture. | PASS: text remained saved on-device while the isolated service was unavailable; after service recovery and app resume, exactly one server submission was recorded. |
| Network failure: offline, timeout, expired session and retry | BLOCKED: only the authenticated session and home were exercised. | PASS: temporary service unavailability showed the saved-on-device state and retained the queued operation; successful recovery was confirmed on resume. |
| Background/resume with queued material | BLOCKED: requires a completed authenticated simulator activity interaction. | PASS: the queued text operation replayed safely after the app returned from background. |
| Camera / permission recovery | PHYSICAL DEVICE REQUIRED | PHYSICAL DEVICE REQUIRED |
| Microphone / recording / permission recovery | PHYSICAL DEVICE REQUIRED | PHYSICAL DEVICE REQUIRED |
| Screen-reader spot check | PHYSICAL DEVICE REQUIRED | PHYSICAL DEVICE REQUIRED |

### Release association requirements

- **iOS Universal Links:** an approved HTTPS host must serve an Apple App Site
  Association file at `/.well-known/apple-app-site-association`, naming the
  signed app's Team ID and bundle identifier; the app must have the matching
  `applinks:<approved-host>` entitlement.
- **Android App Links:** the same approved HTTPS host must serve
  `/.well-known/assetlinks.json`, binding
  `uk.co.politisltd.citizencentric.participant` to the release signing-certificate SHA-256
  fingerprint; the manifest must declare the matching verified HTTPS intent
  filter.
- **Flutter:** the app must validate that host and `/join-study` path before
  consuming the token. No association host, Team ID, or signing fingerprint is
  currently approved for this Flutter app, so deep links remain unsupported.
