# Citizen Centric Android / Google Play release evidence

This document covers the Android build of the canonical Flutter participant application. It is not a separate product or a source of participant data.

## Release configuration

| Setting | Value |
| --- | --- |
| Application ID / namespace | `uk.co.politisltd.citizencentric.participant` |
| App name | Citizen Centric |
| Version | `1.0.0+8` (version name `1.0.0`, version code `8`) |
| Minimum SDK | 24 (Android 7.0) |
| Compile / target SDK | 36 (Android 16) |
| Android Gradle Plugin / Gradle | 9.1.0 / 9.3.1 |
| Kotlin / Java | 2.4.0 / 17 |
| Production API default | `https://citizencentric.co.uk` |

The build pins compile and target SDK 36 directly rather than relying on a Flutter default. The deployed API base URL is protected in Dart: a release build rejects an insecure HTTP endpoint.

## Signing and Google Play App Signing

Release packaging is deliberately fail-closed. `bundleRelease` and other release packaging tasks require all four upload-key values; a missing value stops the build before an unsigned or debug-signed release artifact is made. The project never falls back to the debug key.

Thomas should create the Google Play upload key only when separately approved, store the resulting `.jks` file in the organisation's approved secret store, and enrol the app in Google Play App Signing. A suitable local command is:

```sh
keytool -genkeypair -v -keystore /approved/secure/path/citizen-centric-play-upload.jks \
  -alias citizencentric-upload -keyalg RSA -keysize 4096 -validity 10000
```

Do not commit the keystore, passwords, or this command's answers. Configure one of these mutually equivalent local-only mechanisms:

```properties
# participant_app/android/key.properties (ignored by Git)
storeFile=/approved/secure/path/citizen-centric-play-upload.jks
storePassword=...
keyAlias=citizencentric-upload
keyPassword=...
```

or the four environment variables `PCIP_ANDROID_KEYSTORE_PATH`, `PCIP_ANDROID_KEYSTORE_PASSWORD`, `PCIP_ANDROID_KEY_ALIAS`, and `PCIP_ANDROID_KEY_PASSWORD` in an approved local/CI secret mechanism. Do not echo these variables. The Android subproject ignores `key.properties`, `.jks`, and `.keystore` files.

Once signing is configured, make the upload artifact with:

```sh
flutter build appbundle --release --dart-define=PCIP_API_BASE_URL=https://citizencentric.co.uk
```

The expected artifact is `build/app/outputs/bundle/release/app-release.aab`. Review it before any manual Google Play internal-test upload; this repository does not upload artifacts.

## Android permissions and privacy behaviour

The merged release manifest declares only:

| Permission | Why / when it is used |
| --- | --- |
| `INTERNET` | HTTPS requests to the Citizen Centric service. |
| `CAMERA` | A participant deliberately captures photo evidence. |
| `RECORD_AUDIO` | A participant deliberately records a voice note. |
| `ACCESS_COARSE_LOCATION`, `ACCESS_FINE_LOCATION` | A participant deliberately chooses **Use my current location** for an activity that a researcher configured to allow it. |

There is no `ACCESS_BACKGROUND_LOCATION`, foreground-location-service permission, continuous tracking, notification permission, `READ_MEDIA_*`, `READ/WRITE_EXTERNAL_STORAGE`, or `MANAGE_EXTERNAL_STORAGE` declaration. Image Picker uses the system camera/photo picker and File Picker uses the system document picker. The app does not harvest EXIF location. Location capture uses a one-off foreground device reading; a denied, permanently denied, or failed reading is non-blocking, and the participant can remove a captured location before submission.

`geolocator_android` packages an optional background-stream service that can post a foreground notification. The application never calls its stream/background API and deliberately does not declare notification or background-location permissions. Its static Android lint notification warning is disabled only for that unused dependency path; source-level regression coverage requires `getCurrentPosition` and forbids `getPositionStream`.

## Android 16 compatibility evidence

The app targets Android 16 / API 36. It uses runtime permissions, the system photo/document pickers, a transparent Citizen Centric mark in adaptive launcher resources, Citizen Centric light/dark Flutter launch colours, and Android's predictive-back opt-in. It has no background work, location tracking, notification, analytics, advertising, or Firebase SDK behaviour to adapt. The local debug APK contains arm64-v8a, armeabi-v7a, and x86_64 native libraries and passed the Android 16 KB alignment check. Repeat that check against the signed release AAB before a Play upload.

## Google Play Data Safety evidence

This is evidence for a Play Console review, not a substitute for Thomas's controller, processor, retention, and legal-policy confirmation.

| Data category | Collected by the app | Shared with third parties | Purpose / optionality | Protection and controls |
| --- | --- | --- | --- | --- |
| Account and session identifiers | Invitation/access-code/session data needed to join and recover a study | No advertising or analytics SDK receives it; sent to Citizen Centric over HTTPS | Account/study access; required once a participant joins | TLS in transit; session material uses Android secure storage; withdrawal/account-deletion flows apply. |
| Research text, structured answers and messages | Yes, when the participant submits them | No SDK telemetry recipients identified; sent to Citizen Centric over HTTPS | Research participation and participant/researcher communication; participant initiated | TLS; durable retry preserves participant-selected content locally until delivery. |
| Photos, documents and other files | Yes, only after participant capture/selection | No SDK telemetry recipients identified; sent to Citizen Centric over HTTPS | Participant evidence; optional where the activity permits it | System camera/photo/document pickers; TLS; no broad media-library permission. |
| Voice recordings | Yes, only after participant records and submits one | No SDK telemetry recipients identified; sent to Citizen Centric over HTTPS | Participant evidence; optional where the activity permits it | Runtime microphone permission; TLS; participant-initiated recording/replay. |
| Precise/approximate location | Only when an activity permits it and the participant deliberately requests current location | No SDK telemetry recipients identified; sent to Citizen Centric over HTTPS | Optional research evidence | One-off foreground capture with accuracy; no background access/tracking; removal available before submission. |

The app's dependencies do not contain advertising, analytics, crash-reporting, or social SDKs that independently transmit participant data. The production service may use contracted infrastructure processors; confirm the current Citizen Centric privacy notice, processor schedule, retention policy, and Play Console definitions before declaring a final “shared” answer.

## Android real-device release checklist

Use an Android 16 device and at least one supported older device/API level.

1. Fresh installation and the Citizen Centric launcher/splash presentation.
2. Valid invitation/access code.
3. Invalid or already-used code.
4. Study information and consent.
5. Text submission.
6. Two distinct repeatable entries.
7. Camera capture.
8. System photo picker.
9. Voice recording, replay, and submission.
10. Allow foreground location, capture current location, and verify accuracy.
11. Remove location before submission.
12. Deny location permission and continue the entry normally.
13. Permanently deny/restrict location and verify clear non-blocking guidance.
14. Offline draft, reconnect, and durable retry.
15. Double-submit/idempotency behaviour.
16. Force-close/reopen and session recovery.
17. Logout, fresh login, and session recovery.
18. Submission history.
19. Participant/researcher messages in both directions.
20. Withdrawal/account-deletion flow.
21. Android system back navigation from every participant screen.
22. Permission behaviour after app restart.
23. Document picker selection and upload where the activity supports it.
24. Verify no background location prompt, storage prompt, or placeholder/white-box branding.

## Remaining manual release prerequisites

Before Google Play internal testing, Thomas must provide the upload key through an approved secret mechanism, create/configure the Play Console application under the production package ID, review the signed AAB, complete Data Safety and content/privacy declarations from current legal evidence, and perform the real-device checklist. No key, signing credential, Play Console configuration, or AAB has been created or uploaded by this work.
