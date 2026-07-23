# Pilot Operator Guide

## Purpose

This guide is for pilot operators running day-to-day workflows safely in production-like environments.

## Daily startup checks

1. Open `/health` and confirm status is ok.
2. Verify latest deployment revision and migration level.
3. Confirm no critical errors in app logs during startup.

## User and access operations

1. Use owner/admin accounts for privileged actions.
2. Invite researchers from the Researchers section.
3. Use study-level access controls for least privilege.
4. Disable accounts when needed; session invalidation is immediate.

## Participant operations

1. Create/import participants.
2. Enrol to studies and send invitations.
3. Monitor invitation acceptance and portal activity.
4. Use participant detail page to manage messages and status.

## Evidence and malware handling

1. Verify scan status before evidence access.
2. Treat non-CLEAN evidence as blocked by design.
3. Investigate failed scans and webhook issues through logs.

## Privacy operations (admin only)

1. Export participant data when requested.
2. Run deletion workflow:
   - start deletion request
   - execute delete/anonymise
3. Use retention apply action only after verifying configured values.
4. Confirm corresponding audit events are present.

## Security incident triage basics

1. Repeated failed logins: check lockout and rate-limit audit events.
2. Webhook auth failures: verify shared secret and request signature.
3. Session issues: verify session invalidation events and user status.

## Safe change process during pilot

1. Prefer config-only changes where possible.
2. Run full test suite before applying code changes.
3. Use staged rollout and verify smoke tests after deployment.
4. Record all operator actions affecting access/privacy.
