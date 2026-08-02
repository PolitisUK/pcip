# Citizen Centric Participant App — Mobile Security

## Status

This document records the reviewed security direction for the participant mobile application. It does not authorise production deployment or permanent application identifiers.

## Security principles

- The FastAPI backend remains authoritative for authentication, consent, enrolment, activity availability, response state, messaging and evidence security.
- Participant identity must be derived from a revocable server-side session, never from a client-supplied participant identifier.
- TLS is mandatory for all application traffic.
- Invitation tokens must be exchanged promptly, removed from visible navigation and never persisted in ordinary local storage.
- Passwords, invitation tokens, session credentials, signing materials and API keys must never be committed to Git.
- Where native credentials must be retained, use operating-system secure storage backed by Keychain or Android Keystore.
- Server-side session invalidation must be preserved.
- CSRF and origin protections must remain in force for cookie-authenticated flows.

## Current PWA controls

The service worker uses network-only navigation and caches only an explicit public-static allow-list. It must not cache:

- participant portal pages;
- invitation or authentication pages;
- participant responses or drafts;
- messages;
- evidence;
- API responses;
- authenticated HTML;
- pages containing personal data.

The offline page contains no participant data and does not claim that participant content is available offline.

## Deep links

Universal Links and Android App Links must be verified against a domain controlled by Politis Ltd. A deep-link handler must:

1. validate the expected host and route;
2. hold the invitation token only in memory;
3. exchange it immediately over TLS;
4. remove it from application state and navigation;
5. avoid analytics, logs, crash reports and referrer leakage;
6. reject unknown schemes, hosts and parameters.

## Participant sessions

The preferred mobile session is an opaque random credential with only a hash stored on the server. Each request must revalidate:

- session expiry and revocation;
- participant status;
- consent status;
- study enrolment;
- activity availability;
- resource ownership.

Participant API invitation exchange policy:

- a valid invitation may have at most one active participant API session at a time;
- replay exchange while an active session exists returns generic conflict and does not return existing bearer material;
- if that session is revoked or expired, the same still-valid invitation may exchange again for a replacement session;
- invitation revocation or invitation expiry invalidates an existing API session on the next authenticated request.

Long-lived self-contained participant JWTs are not currently recommended.

## Device permissions

Camera, microphone, photo-library, file and location permissions must be requested only when an associated activity requires them. Permission requests must include clear purpose text and denial must not crash or expose data.

The application must not collect location, audio, video or images in the background.

## Evidence

Existing upload size and extension validation remains server-side. Evidence must remain unavailable until Microsoft Defender for Storage records an explicitly clean result. A native client may display pending, clean, infected or failed states but must not bypass the backend gate.

## Telemetry and logging

- Do not log real participant content, contact details, invitation tokens or session credentials.
- Minimise telemetry and document every mobile analytics or crash-reporting SDK.
- Do not add advertising SDKs.
- Ensure screenshots, demonstrations and store assets use synthetic data only.

## Unresolved decisions

- Session lifetime and inactivity timeout.
- Device binding and multi-device access.
- Biometric re-entry design.
- Recovery when a participant loses the invitation email.
- Resumable upload design and maximum media sizes.
- Push notification provider and device-token retention.
