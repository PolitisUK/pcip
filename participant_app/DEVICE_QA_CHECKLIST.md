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

Run date: 2026-08-15. App commit: `0345640`.

| Target | Model and OS | Result |
| --- | --- | --- |
| iOS simulator | iPhone 17 Pro, iOS 26.5 | PASS: unsigned debug app built, installed, launched to the invitation screen, and relaunch/back navigation did not crash. |
| Android emulator | Google APIs ARM64 emulator, Android 16 / API 36 | PASS: debug APK installed, launched to the invitation screen, and relaunch/back navigation did not crash. |

| Journey | iOS simulator | Android emulator |
| --- | --- | --- |
| A. Install, launch and invitation screen | PASS | PASS |
| B. Invitation/session | BLOCKED: no non-production service address and synthetic invitation were supplied | BLOCKED: no non-production service address and synthetic invitation were supplied |
| C. Consent, home and text activity | BLOCKED: requires a synthetic authenticated participant | BLOCKED: requires a synthetic authenticated participant |
| D. Profile, preferences and history | BLOCKED: requires a synthetic authenticated participant | BLOCKED: requires a synthetic authenticated participant |
| E. Photo capture and library | PHYSICAL DEVICE REQUIRED after an authenticated QA session | PHYSICAL DEVICE REQUIRED after an authenticated QA session |
| F. Document picker | BLOCKED: requires a synthetic authenticated participant/activity | BLOCKED: requires a synthetic authenticated participant/activity |
| G. Voice diary | PHYSICAL DEVICE REQUIRED after an authenticated QA session | PHYSICAL DEVICE REQUIRED after an authenticated QA session |
| H. Withdrawal | BLOCKED: requires an isolated synthetic study state | BLOCKED: requires an isolated synthetic study state |
| I. Deletion request | BLOCKED: requires an isolated synthetic participant | BLOCKED: requires an isolated synthetic participant |
| Accessibility, permission and background/resume checks | PARTIAL: initial invitation layout is usable; full assistive-technology, permission, and authenticated background/resume checks require device QA | PARTIAL: initial invitation layout is usable; full TalkBack, permission, and authenticated background/resume checks require device QA |

No participant data was created. No production endpoint was used.

Device QA defect fixed: Android's application label still exposed the scaffold
name. It now uses the established `Citizen Centric` display name in `0345640`.
