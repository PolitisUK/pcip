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
| C. Offline text/reconnect | BLOCKED: requires authenticated simulator interaction | BLOCKED: the emulator's local HTTP QA fallback was intentionally development-only; transport-loss replay remains covered by automated tests and requires a trusted HTTPS QA environment for device confirmation. |
| D. Messaging | BLOCKED: CoreSimulator service became unavailable before authenticated interaction | PASS: synthetic research-team message opened successfully and a participant reply was accepted. Read/unread is NOT SUPPORTED by the backend. |
| E. Photo capture and library | PHYSICAL DEVICE REQUIRED | PARTIAL: Android Photo Picker, preview/remove UI, backend upload, and processing copy passed using a synthetic image. Camera capture and production permission recovery require a physical device. |
| F. Document picker | BLOCKED: requires authenticated simulator interaction | PASS: Android system document picker selected a synthetic PDF, displayed filename/size, and received backend upload acknowledgement. |
| G. Voice diary | PHYSICAL DEVICE REQUIRED | PHYSICAL DEVICE REQUIRED: Android microphone permission denial and retry were verified. The emulator did not provide reliable recording/playback evidence. Participant-facing transcription is NOT SUPPORTED by the backend. |
| H. Withdrawal | BLOCKED: CoreSimulator service became unavailable before authenticated interaction | PASS: cancellation and explicit confirmation were exercised using an isolated synthetic study; server acknowledgement was shown. |
| I. Deletion request | BLOCKED: CoreSimulator service became unavailable before authenticated interaction | PASS: cancellation and explicit confirmation were exercised using an isolated synthetic participant; server acknowledgement was shown. Status lookup is NOT SUPPORTED by the backend. |
| Accessibility, permission and background/resume checks | PARTIAL: authenticated simulator interaction was blocked by the local simulator service | PARTIAL: semantic labels and scaled layout were visible in the emulator; TalkBack, OS permission prompts, media controls, and full background/reconnect behaviour require device QA. |

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

Device QA defect fixed: Android's application label still exposed the scaffold
name. It now uses the established `Citizen Centric` display name in `0345640`.
