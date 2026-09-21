# Citizen Centric participant app — store release preparation

This is preparation evidence only. It does not authorise an upload or store
submission.

## Shared release candidate

| Item | Value |
| --- | --- |
| Flutter version/build | `1.0.0+9` |
| Android version name/code | `1.0.0` / `9` |
| iOS version/build | `1.0.0` / `9` |
| Android application ID | `uk.co.politisltd.citizencentric.participant` |
| iOS bundle ID | `uk.co.politisltd.citizencentric.participant` |
| iOS deployment target | `15.0` |
| Production API | `https://citizencentric.co.uk` |

Android and iOS candidates must be built from the same recorded Git commit.
Do not use `PCIP_QA_API_BASE_URL`, `PCIP_LOCAL_QA`, test credentials, or a
participant-selectable service endpoint in release builds.

## Google Play App Access

Enter the dedicated Google review username and password only in Google Play
Console's protected App Access fields. Never add the password to this file,
source control, logs, tickets, or build configuration.

> Citizen Centric normally uses invitation-based participant access. For
> Google Play review, select **Username & password** on the app sign-in screen
> and use the dedicated reusable review credentials supplied here. These
> credentials provide access only to a fictional demonstration study and do
> not require email access, an invitation link, OTP, or one-time access code.

Before entry, an authorised operator must confirm that the dedicated Google
review participant has an accepted invitation and current consent only for the
fictional Google/App Review study. Do not alter the Apple reviewer participant.

## Apple review notes

Citizen Centric is an invitation-based research participation app. Ordinary
participants review study information and privacy material, provide explicit
consent, then use the one-time app code supplied by the authorised web portal.
The sign-in screen deliberately keeps **One-time code** as its default. For
review, Apple may use a separately supplied reusable username/password account
that is restricted to fictional demonstration material and requires no email
access, OTP or invitation link.

The candidate includes text, choice, rating, ranking and location activities;
participant messaging; photo, video, voice and document evidence; submission
history; consent; logout; withdrawal and deletion-request journeys. The app
contains no advertising or cross-app tracking SDK and does not enable
provider-backed AI generation.

## Final human gates

1. Confirm Android upload-key access and build the signed AAB without printing
   or committing credentials.
2. Confirm build 9 is unused in both Play Console and App Store Connect.
3. Run the consolidated physical-device checks in `DEVICE_QA_CHECKLIST.md`.
4. Enter reviewer credentials only in each store's protected fields.
5. Review current privacy/data-safety answers and screenshots in the consoles.
6. Upload and submit only after explicit release-owner approval.
