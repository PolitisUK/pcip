# Mobile Foundation Decision (PR Seed)

Status: Approved for implementation on a staging-only, non-production basis.

## Decision summary

- Framework: Expo + React Native + TypeScript (strict mode)
- Repository model: Keep in the existing repository as a monorepo-style subproject
- Mobile project path: mobile/participant-app
- Package manager: npm (repository has no existing Node lockfile convention)
- Minimum OS targets (provisional for staging): iOS 15.0+, Android API 26+
- App identifiers (provisional, non-production):
  - iOS bundle identifier: uk.politis.pcip.participant.staging
  - Android applicationId: uk.politis.pcip.participant.staging
  - Display name: Citizen Centric Participant (Staging)
- Deep-link scheme: pcip-participant
- Universal/App Link domains (staging placeholders to be confirmed by platform ops):
  - participant.staging.politis.co.uk
- Environment configuration baseline:
  - EXPO_PUBLIC_API_BASE_URL
  - EXPO_PUBLIC_DEEP_LINK_HOST
- API client strategy: generate and check in typed OpenAPI TypeScript definitions from docs/participant-api-v1.yaml using openapi-typescript, then consume via thin fetch wrapper modules.
- Secure token storage: expo-secure-store (Keychain/Android Keystore backed)
- Testing and CI conventions:
  - Scripts: lint, typecheck, test
  - CI: dedicated mobile workflow running npm ci + lint + typecheck + test on mobile/participant-app

## Rationale

Expo/React Native with TypeScript provides a single codebase for iOS/Android, practical deep-link support, mature secure storage support, and straightforward CI for the first participant-mobile increment.

## Out of scope for this foundation increment

- Evidence upload implementation
- Messaging implementation
- Notifications implementation
- Researcher/admin interfaces
- Production app registration or store submission
