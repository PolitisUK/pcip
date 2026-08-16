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
