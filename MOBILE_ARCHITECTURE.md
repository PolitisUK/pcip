# Citizen Centric Participant App — Mobile Architecture

## Status

This document records the reviewed architecture for the participant-focused
Citizen Centric mobile application.

It does not authorise:

- deployment to production;
- creation of permanent application identifiers;
- submission to Apple App Store or Google Play;
- introduction of native iOS or Android projects.

Production remains in its post-release soak period. Mobile development and
testing must use the dedicated staging application and synthetic participant
data.

## Product scope

The mobile application is intended for invited research participants.

Researchers, administrators, observers and organisation owners will continue
to use the existing web dashboard.

The participant application is expected to support:

- opening study invitation links;
- accepting or declining consent;
- viewing enrolled studies;
- viewing available, upcoming and completed activities;
- saving draft responses;
- submitting responses;
- capturing or selecting photographs, audio, video and documents;
- uploading evidence securely;
- viewing malware-scan status;
- sending and receiving participant messages;
- receiving relevant notifications;
- withdrawing consent;
- requesting access to, deletion of or anonymisation of participant data;
- secure device re-entry where appropriate.

## Existing architecture

Citizen Centric currently uses:

- Python 3.12;
- FastAPI;
- Jinja2 server-rendered templates;
- SQLAlchemy and Alembic;
- PostgreSQL;
- Azure App Service;
- Azure Container Registry;
- Azure Blob Storage;
- Microsoft Defender for Storage;
- Azure Key Vault;
- Application Insights and OpenTelemetry support.

The current participant portal is server-rendered and uses invitation-token
exchange followed by a server-side public authentication session.

The participant session is currently associated with one participant
invitation and therefore one study.

## Architectural principles

### Preserve the existing backend

FastAPI and PostgreSQL remain authoritative for:

- participant authentication;
- invitation validity and revocation;
- consent state;
- study enrolment;
- activity availability;
- response state;
- evidence metadata;
- malware-scan state;
- messaging;
- privacy administration;
- audit logging.

The mobile client must not independently reproduce or override these business
rules.

### Incremental delivery

The recommended sequence is:

1. Improve the participant portal as a safe PWA foundation.
2. Correct participant mobile accessibility and usability issues.
3. Extract shared participant-domain services from route handlers.
4. Introduce a narrowly scoped participant JSON API.
5. Validate authentication, deep links and uploads through a staging-only
   Capacitor proof of concept.
6. Add native iOS and Android projects only after that proof is reviewed.
7. Introduce push notifications as a later increment.

### Participant-only native application

The native application must not contain the research administration
interface.

Staff administration remains web-based.

### Server-side enforcement

The backend must continue to enforce:

- consent;
- invitation expiry and revocation;
- participant status;
- study enrolment;
- activity release and due dates;
- required responses;
- file type and size restrictions;
- evidence malware scanning;
- evidence download restrictions;
- participant privacy permissions.

## PWA foundation

The PWA foundation must include:

- a web-app manifest;
- application metadata;
- mobile icon requirements;
- an explicit offline or network-failure page;
- safe service-worker behaviour;
- tests covering cache exclusions;
- participant mobile usability corrections.

The service worker must never cache:

- participant portal pages;
- authentication pages;
- invitation URLs;
- invitation tokens;
- messages;
- activity responses;
- evidence;
- participant API responses;
- authenticated HTML responses;
- pages containing personal data.

Only explicitly listed public static assets may be cached.

## Target mobile architecture

```text
iOS / Android application
        |
        | TLS
        | verified application links
        | native camera, microphone and file selection
        | operating-system secure storage
        v
FastAPI participant API boundary
        |
        | shared participant-domain services
        | server-side consent and availability rules
        | revocable participant sessions
        v
PostgreSQL
        |
        +-- participants
        +-- enrolments
        +-- invitations
        +-- activities
        +-- responses
        +-- messages
        +-- evidence metadata
        |
        v
Azure Blob Storage
        |
        v
Microsoft Defender for Storage

## Required participant API areas

A future participant API is expected to cover:

- invitation exchange;
- session status and revocation;
- consent acceptance, decline and withdrawal;
- study and enrolment listing;
- activity listing;
- draft saving;
- response submission;
- evidence upload;
- evidence scan status;
- participant messaging;
- message read state;
- privacy and data requests;
- device registration for later push notifications.

The API must derive participant identity from the authenticated session and
must never trust a participant ID supplied by the client.

## Privacy and security boundaries

The application must:

- use TLS exclusively;
- preserve server-side session invalidation;
- preserve CSRF and origin protections where cookies remain in use;
- avoid ordinary local storage for credentials and invitation tokens;
- avoid sensitive data in logs, screenshots and crash reports;
- request device permissions only when required by a specific activity;
- avoid background data collection;
- avoid advertising SDKs;
- minimise analytics;
- preserve the malware-scan gate;
- provide privacy, support, withdrawal and data-request routes.

## Decisions not yet made

The following remain deliberately unresolved:

- final application name;
- Apple bundle identifier;
- Android package name;
- minimum supported operating-system versions;
- participant identity across multiple organisations;
- multi-device session policy;
- biometric re-entry design;
- consent-decline consequences;
- withdrawal consequences for previously submitted data;
- maximum media sizes;
- interrupted and resumable upload strategy;
- final privacy and support URLs.

These decisions must not be guessed or made permanent without review.
