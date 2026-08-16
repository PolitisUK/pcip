# Participant API minimum-access inventory

This inventory is a deny-by-default review of the bearer-authenticated
participant API. A bearer resolves to one `PublicAuthSession`, one invitation,
one participant and one active study scope. Callers cannot provide a
participant or organisation identifier to widen that scope.

| Route family | Participant purpose | Scope / disclosure controls |
| --- | --- | --- |
| `POST /api/v1/participant/session/exchange` | Exchange a valid invitation for a bearer session | Invitation-token lookup only; invalid/revoked/expired invitations return a generic error; token is not logged or returned after failure. |
| `GET`/`DELETE /api/v1/participant/session` | Recover or revoke the current participant session | Current bearer only; no customer/researcher cookie is created. |
| `GET`/`PUT /api/v1/participant/profile` | Read/update the caller's permitted profile preference | Current invitation participant only; no participant ID is accepted as input. |
| `GET /api/v1/participant/legal-documents` and `POST /consent` | Study-specific legal references and consent | Current invitation study only; consent evidence is captured server-side. |
| `GET /studies`, `GET /activities`, `GET /activities/{id}` | Study and activity access | Consent plus enrolment required; study query cannot differ from invitation scope; object lookups include organisation/study constraints. |
| Draft/submit/evidence routes under `/activities/{id}` | Participant response and media evidence | Current participant, invitation study, organisation, availability and consent required; idempotency is invitation-scoped. |
| `GET /evidence/{id}/status` | Participant-facing upload status | Evidence is constrained by organisation, study and participant; raw storage keys, blob URIs, hashes and scanner diagnostics are excluded. |
| `GET`/`POST /messages` | Participant-visible study messages and replies | Current participant/study only; internal notes are excluded server-side. |
| Privacy request routes | Withdrawal/deletion request | Current participant and invitation study only; supplied out-of-scope study IDs are rejected. |

## Explicitly excluded access

Participant bearers are not customer or researcher sessions. They cannot use
customer portal pages or APIs, participant directory/detail routes, audit,
outbox, organisation/team administration, platform administration, research
analysis, AI/code/theme/contradiction workflows, exports for other people, or
global/tenant administration. Those route families require separate
server-side authentication and role checks; a participant bearer alone is not
accepted as a substitute.

## Test coverage

`test_participant_api_access_matrix_is_invitation_scoped_and_denies_customer_routes`
uses two participants in one study and inaccessible same-organisation and
cross-tenant studies. It verifies own-activity/message visibility, scope
rejection for identifier manipulation, and denial of customer/platform pages.
Existing API tests additionally cover evidence status object scope, internal
message exclusion, consent/enrolment gating, idempotency and expired/revoked
bearer sessions.
