# Citizen Centric Participant App — private TestFlight preparation

Prepared: 16 August 2026  
Repository release candidate: participant mobile stack through PR #64

This file records evidence for a private, internal TestFlight beta. It is not
an App Store submission and does not authorise public distribution.

## Release identity and build input

| Item | Current repository value | Status |
| --- | --- | --- |
| Display name | Citizen Centric | Verified |
| Bundle identifier | `uk.co.politisltd.participantApp` | Existing project value; confirm it is registered to the approved Apple team |
| iOS deployment target | 15.0 | Verified |
| Current app version/build | 1.0.0 (1) | Confirm the next unused App Store Connect build number before archive |
| Release API base | `https://citizencentric.co.uk` | Repository/deployment source of truth; pass it explicitly as `PCIP_API_BASE_URL` for the signed build |

For the archive, use the already-approved HTTPS base and an App Store Connect
build number that has not previously been uploaded. Do not use debug-only
`PCIP_QA_API_BASE_URL` values in a release build.

## Signing and App Store Connect prerequisites

The repository uses automatic signing and names an existing development team
in the Xcode project. This Mac must have an Apple Developer account, signing
certificate and provisioning profile that match both that team and the bundle
identifier before a TestFlight archive can be produced.

Required owner actions before signing/upload:

1. Sign in to Xcode with the approved Apple Developer account and confirm the
   team that owns `uk.co.politisltd.participantApp`.
2. Confirm the existing App ID, or register it under that approved team.
3. Confirm/create the private App Store Connect app record and provide the
   organisation-approved SKU if one is required.
4. Confirm the next unused build number for version 1.0.0.
5. Accept any App Store Connect agreement and answer export-compliance prompts
   from the organisation's actual legal/security position.

No certificate, profile, Apple credential, SKU or App Store Connect record is
created by this repository.

## Permissions and tracking

The iOS app declares only the participant-facing permissions used by the app:

- Camera — optional photo evidence capture.
- Photo Library — optional photo evidence selection.
- Microphone — optional voice diary recording.
- Document selection uses the system document provider and requests no broad
  filesystem permission.

No location, contacts, Bluetooth, advertising identifier or App Tracking
Transparency permission is declared. The mobile dependency and source audit
found no advertising, marketing, analytics or cross-app tracking SDK. ATT is
therefore **not required** unless a future dependency changes that conclusion.

## Recommended App Privacy answers (owner confirmation required)

Use these as the starting point for the App Store Connect questionnaire. They
describe data that can be sent to Citizen Centric servers for the participant's
study; they are not a declaration that the data is used for tracking.

| Apple data category | Collected | Linked to participant | Used for tracking | Purpose |
| --- | --- | --- | --- | --- |
| Contact information (name, email, phone where provided) | Yes | Yes | No | Account/invitation and participant support |
| Identifiers (participant/session identifiers) | Yes | Yes | No | Authentication, security and study access |
| User content (text responses, messages, documents) | Yes | Yes | No | Research participation and participant communications |
| Photos or videos | Yes, when selected | Yes | No | Participant-provided evidence |
| Audio data | Yes, when recorded | Yes | No | Participant-provided voice diary |
| Sensitive information | Study-dependent; confirm | Yes when collected | No | Only where an approved study permits it |
| Diagnostics/security data | Confirm production telemetry | Potentially | No | Service operation and security only |

The app does not send participant material directly to OpenAI, Azure OpenAI,
Azure Speech, Document Intelligence or Search. Any server-side processing is
outside the mobile tracking boundary and must remain described accurately in
the privacy notice and controller study material.

## Required public metadata URLs

The release API host is reachable over HTTPS, but on 16 August 2026 these
paths returned 404 and cannot yet be used as App Store metadata:

- `https://citizencentric.co.uk/privacy`
- `https://citizencentric.co.uk/support`

Publish and verify an approved public Privacy Policy URL before TestFlight
upload. Confirm an approved Support URL and any Marketing URL before entering
App Store Connect metadata. Do not substitute private repository documents or
invent another domain.

## Private beta notes

**Citizen Centric Participant App beta**

Please use synthetic/test participant invitations only. Test invitation
onboarding, consent, activities, drafts/offline sync, messaging, photo and
document evidence, voice diary, profile/preferences, withdrawal/deletion and
accessibility. Do not use real participant or research data.

For physical iPhone checks, follow
[`DEVICE_QA_CHECKLIST.md`](DEVICE_QA_CHECKLIST.md), particularly first launch,
permission denial/retry, camera, photo library, document picker, microphone,
recording/playback, background/resume, network reconnection, logout, VoiceOver
and Dynamic Type.
