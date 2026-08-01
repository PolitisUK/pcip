# Citizen Centric Participant App — Mobile Privacy

## Status

This document records the reviewed privacy direction for the participant application. It does not replace project-specific legal advice, research ethics approval or controller instructions.

## Data categories

The participant application may process:

- names and contact details;
- demographic information;
- consent records;
- study enrolment and activity status;
- free-text responses;
- participant and researcher messages;
- photographs, audio, video and documents;
- location information where a study explicitly requires it;
- technical security and diagnostic data kept to the minimum necessary.

## Principles

- Collect only the information required for the relevant study activity.
- Present clear purpose information before collecting device data.
- Avoid background collection.
- Avoid advertising and cross-app tracking SDKs.
- Minimise analytics and document any telemetry.
- Use synthetic data for screenshots, demonstrations, testing and store review.
- Do not place participant content in logs or crash reports.
- Keep retention and deletion decisions on the server, under the applicable study and organisation policy.

## Consent

The backend remains authoritative for consent status. The mobile application must support a clear consent journey and must not infer consent from app installation, notification permission or use of another study.

The product still requires a defined participant-facing decline and withdrawal workflow. Before implementation, confirm:

- whether a decline is retained as a record;
- whether withdrawal applies to one study or all studies;
- what happens to previously submitted responses and evidence;
- what contact or support follows a withdrawal request.

## Participant rights

The platform already contains staff-side export, deletion and anonymisation capabilities. The mobile application requires participant-facing routes to:

- request access to participant data;
- request correction where appropriate;
- request deletion or anonymisation;
- withdraw consent;
- contact the relevant privacy or research contact;
- understand the consequences and expected handling time.

A mobile request must not directly perform irreversible deletion without the required server-side checks, policy and confirmation.

## Evidence and media

Media permissions must be requested only when the current activity requires them. The application must explain the purpose before opening the camera, microphone, photo library, file selector or location permission.

Evidence remains subject to the existing file validation and Microsoft Defender for Storage malware-scan gate.

## Local storage and offline behaviour

Sensitive participant pages, responses, messages and evidence must not be cached by the service worker. Invitation tokens and session credentials must not be stored in ordinary local storage.

The current offline page contains no participant content and does not imply that submissions are stored offline.

## Store disclosures

Apple privacy disclosures and Google Play Data Safety declarations must be based on the final implemented data flows, SDKs, retention and sharing. They must not be completed from planned functionality alone.

## Required public information

Before store submission, provide:

- privacy-policy URL;
- support URL and contact route;
- account or data-deletion request URL;
- consent-withdrawal route;
- current controller and contact information for the service;
- explanations of any project-specific data-controller differences.

## Unknowns

- Final privacy-policy wording and ownership.
- Per-study retention rules.
- Whether location is precise or approximate.
- Whether participants may be pseudonymous or anonymous.
- Whether one participant identity spans organisations.
- Final crash-reporting and analytics tools, if any.
