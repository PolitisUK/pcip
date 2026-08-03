# Participant Mobile Foundation

Expo + React Native + TypeScript mobile foundation for participant-only experiences.

## Included in this increment

- TypeScript strict-mode scaffold
- Environment configuration baseline
- Typed API client foundation for participant session endpoints
- Secure participant-session storage via `expo-secure-store`
- Deep-link routing foundation for invitation links
- Navigation shell with accessibility-oriented baseline controls
- Participant activity response entry and evidence attachment workflow
- Participant messaging inbox and secure message send flow
- Participant account and privacy actions (withdrawal and deletion requests)
- Device push-notification permission and local preference foundation
- EAS build profile starter configuration in `eas.json`
- Production and store readiness checklists under `docs/`
- Lint, type-check and unit-test scripts

## Out of scope in this increment

- Researcher/admin interfaces
- Production push provider backend integration
- Store submission execution

## Environment

Copy `.env.example` to `.env` and set staging values.

Required variables include:

- `EXPO_PUBLIC_API_BASE_URL`
- `EXPO_PUBLIC_DEEP_LINK_HOST`
- `EXPO_PUBLIC_DEEP_LINK_SCHEME`
- `EXPO_PUBLIC_PRIVACY_URL`
- `EXPO_PUBLIC_TERMS_URL`
- `EXPO_PUBLIC_SUPPORT_URL`
- `EXPO_PUBLIC_EAS_PROJECT_ID`

## Scripts

- `npm run start`
- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run generate:api-types`
