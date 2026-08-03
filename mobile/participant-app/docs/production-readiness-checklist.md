# Participant App Production Readiness Checklist

## Security And Privacy
- Confirm participant API base URL points to approved production endpoint.
- Verify HTTPS-only networking and certificate trust requirements.
- Confirm privacy and terms URLs are correct for production.
- Confirm secure storage keys are scoped to production app package identifiers.
- Validate incident contacts for security triage and breach escalation.

## Notifications
- Set `EXPO_PUBLIC_EAS_PROJECT_ID` for production builds.
- Validate push permission copy and user support guidance.
- Verify notification handler behavior in foreground and background states.
- Confirm token rotation and revocation process is documented for support teams.

## Reliability
- Run `npm run lint`, `npm run typecheck`, `npm test -- --runInBand`.
- Run backend suite from repository root: `PYTHONPATH=. pytest`.
- Validate offline behavior for message send and privacy requests.
- Validate session-expiry behavior for account and messaging actions.

## Operational Controls
- Configure EAS build channels and rollout sequencing.
- Verify app versioning and auto-increment strategy.
- Verify monitoring dashboards and on-call alert routes.
- Confirm support runbook links are embedded in release documentation.
