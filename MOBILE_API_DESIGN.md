# Participant Mobile API Design Review

## 1. Executive summary

This review proposes the smallest safe participant JSON API surface for a future native mobile app while preserving current web behavior.

Recommendation summary:

- Keep current server-rendered participant web flows unchanged.
- Add a separate versioned participant API under /api/v1/participant.
- Use opaque mobile bearer credentials backed by server-side session rows (hashed at rest) instead of cookie-authenticated mobile API calls.
- Reuse existing participant service helpers for invitation resolution, consent grant, activity availability, response persistence, evidence metadata, and messaging semantics.
- Introduce only the minimum new service helpers needed for mobile session lifecycle, multi-study participant scope, and privacy request intake.

Proposed API count in this review: 15 endpoints.

## 2. Verified current state

### 2.1 Participant-facing HTML routes that exist today

Verified in app/main.py:

- GET /join-study
- POST /join-study
- GET /participant-portal
- POST /participant-portal/activity/{activity_id}
- POST /participant-portal/message

Related verified routes:

- GET /evidence/{evidence_id} (staff-authenticated route using current_user; not participant-public)
- POST /participants/{participant_id}/message (staff-authenticated route)
- GET /participants/{participant_id}/export (owner/admin)
- POST /participants/{participant_id}/privacy/delete-request (owner/admin)
- POST /participants/{participant_id}/privacy/delete-execute (owner/admin)
- POST /privacy/retention/apply (owner/admin)

### 2.2 Current participant auth/session flow

Verified behavior:

- Invitation links include token query parameter on /join-study.
- Token is hashed and looked up through participant invitation records.
- On valid token, server creates PublicAuthSession with scope participant_portal, 12-hour expiry, and stores only session hash.
- Response sets cookie public_auth_session with HttpOnly, SameSite strict, secure based on COOKIE_SECURE.
- Participant portal and participant writes are authorized from this public auth cookie.
- CSRF is required for POST forms through csrf_session + hidden field csrf_token.
- Participant portal writes are rate-limited by IP and invitation/account key.

### 2.3 Current consent, activity, response, evidence, messaging behavior

Verified in routes and participant services:

- Consent acceptance sets invitation accepted_at (if absent), participant status active, consent_status granted.
- Activity availability is server-authoritative via activity_window using study start and per-activity offsets.
- Draft and submit share one route; status is set by action field (draft or submit).
- Response payload shape currently stores answer and choices JSON.
- Upload path currently accepts multipart file in the same activity POST and validates extension and size server-side.
- Evidence scan gating blocks download until clean (except explicit development override).
- Defender webhook updates evidence scan status by blob URI.
- Participant-visible portal messages exclude internal_note true and are ordered by created_at.
- Staff participant-detail view includes internal notes.

### 2.4 Existing mobile design/security/privacy documentation state

Verified in current docs:

- MOBILE_ARCHITECTURE.md mandates incremental API introduction, server-side enforcement, and no sensitive service worker caching.
- MOBILE_SECURITY.md recommends opaque revocable server-side sessions and preserving invalidation.
- MOBILE_PRIVACY.md identifies participant-facing withdrawal/deletion/correction/support as required product capabilities still needing explicit participant flows.

### 2.5 Existing tests relevant to this review

Verified test coverage includes:

- Participant portal invite, consent, activity draft/submit and message flows.
- Activity availability conflict response before release window.
- Rate limiting for participant invitation accept and portal writes.
- Messaging semantics including participant and researcher sender/internal_note behavior.
- Privacy export/deletion workflows for staff roles and role restrictions.

## 3. Recommended authentication model

Recommended model: hybrid by channel, not hybrid per endpoint.

- Web participant pages keep existing cookie + CSRF model unchanged.
- New mobile participant API uses Authorization bearer credentials only.
- Bearer credential must be opaque random value; store only token hash in server database.
- Backing record should remain server-revocable and expirable (reuse PublicAuthSession table with new scope participant_api, or equivalent dedicated table).

Why this is safest for mobile:

- Avoids WKWebView/Android WebView cross-origin cookie inconsistencies and SameSite strict interoperability risk.
- Removes CSRF burden from API writes by not using browser cookies for API auth.
- Preserves immediate server-side invalidation and session expiry checks.
- Aligns with existing platform preference for revocable server-side auth state.

Why not keep cookie-only for mobile API:

- Native app network stack and WebView cookie jars can diverge.
- SameSite strict on public_auth_session is strong for browser web but awkward for deep-link initiated app API exchange patterns.
- CSRF-origin assumptions are browser-centric and increase integration complexity for API-first native clients.

Why not long-lived self-contained JWT as primary session:

- Harder immediate revocation/invalidation guarantees.
- Introduces key-rotation and token misuse blast-radius concerns not needed for smallest safe increment.

## 4. Deep-link and invitation exchange flow

Recommended Universal Link and Android App Link flow:

1. Email link points to verified HTTPS route under service domain, e.g. /join-study?token=... .
2. OS resolves to app link handler when app is installed.
3. App validates host/path allow-list and keeps token in memory only.
4. App immediately calls invitation exchange API over TLS.
5. Server validates invitation hash, expiry, revocation, and participant eligibility.
6. Server returns mobile session credential plus sanitized participant/study/session summary.
7. App clears token from in-memory state and navigates to a clean internal route with no token.
8. App never persists invitation token in local storage, logs, analytics, or crash traces.

Replay/leakage controls recommended for mobile exchange:

- Add participant-scope token redemption tracking (same pattern already used for password reset and researcher invitation) to limit replay of raw invitation token exchange.
- Keep invitation record itself authoritative for revoked_at, expires_at, accepted_at rules.
- Return generic invalid/expired responses to avoid token probing signals.
- Rate-limit exchange by IP and token hash key.

## 5. Proposed API surface

Base path: /api/v1/participant

Endpoint list (minimum viable and safety-scoped):

1. POST /invitation/exchange
2. GET /session
3. POST /session/logout
4. GET /studies
5. GET /portal
6. GET /activities
7. GET /activities/{activity_id}
8. PUT /activities/{activity_id}/draft
9. POST /activities/{activity_id}/submit
10. POST /activities/{activity_id}/evidence-uploads
11. GET /evidence/{evidence_id}/status
12. GET /messages
13. POST /messages
14. POST /privacy/withdrawal-requests
15. POST /privacy/deletion-requests

Routes that should remain HTML-only for now:

- Staff dashboard and all /participants/{id} staff pages.
- Researcher invitation/admin flows.
- Staff privacy execution and retention apply actions.

Routes that should not be exposed directly to mobile participant API:

- GET /evidence/{evidence_id} direct file download route (staff-authenticated and study-access bound to staff model).
- POST /participants/{participant_id}/message staff route with internal_note control.
- Any endpoint that accepts client-supplied participant_id for participant self-actions.

## 6. Endpoint-by-endpoint contracts

### 6.1 POST /api/v1/participant/invitation/exchange

- Purpose: exchange invitation token for mobile participant session.
- Auth: none (public with strict validation and rate limit).
- Request schema:
  - token: string, required
  - device_hint: optional object (platform, app_version) for audit/ops only
- Response schema:
  - session: access_token, expires_at, token_type Bearer
  - participant: id (opaque external reference preferred), display_name
  - invitation: study_id, accepted_at, expires_at, revoked boolean
  - next_action: consent_required or portal
- Status codes: 200, 400 invalid_or_expired, 409 revoked_or_ineligible, 429, 500.
- Idempotency: yes for valid live invitation; returns current live session or rotates by policy.
- Rate limit: strict per IP and token hash account key.
- Existing service reuse: resolve_invitation_by_token, resolve_participant_invitation concepts.
- New service needed: participant mobile token redemption/issue helper.

### 6.2 GET /api/v1/participant/session

- Purpose: return current authenticated participant and invitation/study context.
- Auth: bearer required.
- Request schema: none.
- Response schema:
  - participant summary
  - session expiry
  - active invitation/study linkage
  - consent status
- Status codes: 200, 401, 403, 500.
- Idempotency: yes.
- Rate limit: moderate per token and IP.
- Existing reuse: PublicAuthSession lookup pattern.
- New service: bearer auth dependency for participant API.

### 6.3 POST /api/v1/participant/session/logout

- Purpose: revoke current mobile session.
- Auth: bearer required.
- Request schema: none.
- Response schema: { revoked: true }.
- Status codes: 200, 401.
- Idempotency: yes.
- Rate limit: low-to-moderate.
- Existing reuse: revoke_public_auth_session logic shape.
- New service: participant API session revocation helper.

### 6.4 GET /api/v1/participant/studies

- Purpose: list studies visible to current participant identity.
- Auth: bearer required.
- Request schema: optional pagination cursor/limit.
- Response schema: array of study cards with enrolment and invitation status.
- Status codes: 200, 401.
- Idempotency: yes.
- Rate limit: moderate.
- Existing reuse: enrolment/invitation queries in participant_detail and portal.
- New service: participant-scope study listing helper (currently route-local SQL).

### 6.5 GET /api/v1/participant/portal

- Purpose: return portal summary payload equivalent to current participant_portal HTML data model.
- Auth: bearer required.
- Request schema: optional study_id only if multi-study session is allowed.
- Response schema:
  - study
  - participant
  - activities with availability window
  - responses (draft/submitted states)
  - participant-visible messages
- Status codes: 200, 401, 403.
- Idempotency: yes.
- Rate limit: moderate.
- Existing reuse: activity_window, list_participant_visible_messages, response resolution reads.
- New service: optional composite portal projection helper.

### 6.6 GET /api/v1/participant/activities

- Purpose: list activities with server-evaluated availability and response summary.
- Auth: bearer required.
- Request schema: optional study filter if policy allows multiple studies.
- Response schema: activity list including availability status open/upcoming/closed and existing response state.
- Status codes: 200, 401, 403.
- Idempotency: yes.
- Rate limit: moderate.
- Existing reuse: activity_window.
- New service: activity list projection helper.

### 6.7 GET /api/v1/participant/activities/{activity_id}

- Purpose: get one activity detail and current participant response value.
- Auth: bearer required.
- Request schema: path activity_id.
- Response schema: activity metadata, availability window, response payload, evidence metadata references.
- Status codes: 200, 401, 403, 404.
- Idempotency: yes.
- Rate limit: moderate.
- Existing reuse: resolve_activity_response, activity_window.
- New service: participant ownership + study linkage validation helper.

### 6.8 PUT /api/v1/participant/activities/{activity_id}/draft

- Purpose: save draft response without final submission.
- Auth: bearer required.
- Request schema:
  - answer: string optional by type
  - choices: array string optional
  - evidence_id optional when already uploaded
- Response schema: response id, status draft, updated_at.
- Status codes: 200, 400, 401, 403, 404, 409, 429.
- Idempotency: should be idempotent by full replacement semantics for latest draft state.
- Rate limit: participant_portal_write equivalent.
- Existing reuse: resolve_or_create_activity_response, serialise_response_payload, apply_response_action with action draft.
- New service: input validation adapter for JSON body rather than form fields.

### 6.9 POST /api/v1/participant/activities/{activity_id}/submit

- Purpose: submit final response.
- Auth: bearer required.
- Request schema: same shape as draft, with optional evidence_id.
- Response schema: response id, status submitted, submitted_at.
- Status codes: 200, 400 required response missing, 401, 403, 404, 409 availability closed/upcoming, 429.
- Idempotency: effectively idempotent for identical payload; repeated submit updates submitted_at by policy decision.
- Rate limit: participant_portal_write equivalent.
- Existing reuse: same helpers as draft path with submit action.
- New service: optional explicit submit validator for required fields by activity type.

### 6.10 POST /api/v1/participant/activities/{activity_id}/evidence-uploads

- Purpose: upload evidence associated with activity and response.
- Auth: bearer required.
- Request schema (phase 1): multipart file + optional caption text.
- Response schema: evidence id, scan_status, scan_detail, storage_provider.
- Status codes: 201, 400 invalid type, 401, 403, 404, 409 availability constraints, 413 too large, 429.
- Idempotency: no.
- Rate limit: participant_portal_write equivalent plus upload-specific cap recommended.
- Existing reuse: build_evidence_file, existing extension/size gate, scan logic.
- New service: dedicated upload orchestration helper to isolate storage and scan workflow.

### 6.11 GET /api/v1/participant/evidence/{evidence_id}/status

- Purpose: return evidence metadata and current scan status without raw storage path exposure.
- Auth: bearer required.
- Request schema: path evidence_id.
- Response schema: evidence id, original_name, content_type, size_bytes, scan_status, scan_detail, downloadable boolean.
- Status codes: 200, 401, 403, 404.
- Idempotency: yes.
- Rate limit: moderate.
- Existing reuse: resolve_org_scoped_evidence, is_evidence_downloadable.
- New service: participant ownership check by invitation/session context.

### 6.12 GET /api/v1/participant/messages

- Purpose: list participant-visible messages for active context.
- Auth: bearer required.
- Request schema: optional study filter when multi-study policy exists.
- Response schema: ordered messages with sender_type, body, created_at.
- Status codes: 200, 401, 403.
- Idempotency: yes.
- Rate limit: moderate.
- Existing reuse: list_participant_visible_messages.
- New service: optional pagination helper.

### 6.13 POST /api/v1/participant/messages

- Purpose: send participant message to research team.
- Auth: bearer required.
- Request schema: body string required.
- Response schema: created message summary.
- Status codes: 201, 400 empty body, 401, 403, 429.
- Idempotency: no.
- Rate limit: participant_portal_write equivalent.
- Existing reuse: create_participant_message.
- New service: none required beyond API auth dependency.

### 6.14 POST /api/v1/participant/privacy/withdrawal-requests

- Purpose: create consent withdrawal request for participant and study scope.
- Auth: bearer required.
- Request schema:
  - scope: study or all
  - reason optional
  - contact_preference optional
- Response schema: request_id, status received, next_steps summary.
- Status codes: 202, 400, 401, 403, 429.
- Idempotency: should be idempotent over short window to avoid duplicate submissions.
- Rate limit: strict low-volume.
- Existing reuse: none direct for participant-side withdrawal requests.
- New service: new withdrawal-request persistence and workflow audit helper.

### 6.15 POST /api/v1/participant/privacy/deletion-requests

- Purpose: create participant-initiated deletion/anonymisation request, not execute irreversible deletion directly.
- Auth: bearer required.
- Request schema:
  - mode_preference: delete or anonymise or auto
  - reason optional
- Response schema: request_id, status received, policy notice.
- Status codes: 202, 400, 401, 403, 429.
- Idempotency: should be idempotent over short window.
- Rate limit: strict low-volume.
- Existing reuse: staff-side deletion execution exists; no participant request intake endpoint exists.
- New service: new privacy request intake + triage workflow service.

## 7. Evidence upload architecture

Options assessed:

- Multipart through FastAPI (current behavior pattern)
- Direct-to-Blob SAS upload
- Staged resumable upload sessions

Assessment:

- Multipart through FastAPI is smallest implementation delta and fully reuses existing validation and audit shape.
- Multipart has weaker resilience for large mobile uploads, intermittent networks, and resume behavior.
- Direct SAS improves throughput and app reliability but raises token leakage and completion-coordination complexity.
- Staged upload sessions provide the strongest auditability and retry control by binding upload intent, size/type constraints, expiry, and finalize step to server policy.

Recommendation:

- Phase 1 (smallest safe): multipart evidence upload endpoint to preserve current behavior and reduce migration risk.
- Phase 2 (recommended strategic target): staged upload sessions with short-lived constrained SAS URLs and explicit finalize call.

Required safeguards for SAS/session model:

- per-upload short TTL
- scope-limited blob path and method
- expected content-type and max-size constraints
- one-time finalize state transition
- scan-status polling endpoint remains server authoritative
- no SAS tokens in logs or crash telemetry

## 8. Offline and local storage model

Safe to cache locally:

- static app shell assets
- non-sensitive UI configuration
- activity metadata that does not include personal narrative content (time-limited cache)

Sensitive content that should not be broadly cached:

- invitation tokens
- bearer session credentials
- participant identifiers linked to contact data
- message bodies
- free-text responses
- evidence files

Draft response handling:

- Draft text may be queued offline only if encrypted at rest and bound to app lock/OS secure boundary.
- Flush queue must revalidate activity availability at submit time; server remains authoritative.

Evidence handling:

- Avoid persistent cleartext media cache.
- Prefer temporary app-private storage with explicit lifecycle cleanup.

Storage boundary recommendation:

- OS secure storage: session credentials and cryptographic secrets only.
- Local database (app sandbox): minimal operational metadata and optional encrypted drafts.
- No ordinary localStorage or equivalent for secrets/tokens.

## 9. Privacy, withdrawal and deletion gaps

Implemented today:

- Staff-side participant export.
- Staff-side participant delete/anonymise workflow with confirmation token.
- Staff-side retention apply action.

Staff-only today:

- All privacy execution endpoints in current backend are owner/admin restricted.

Missing participant-facing capabilities:

- Participant self-service withdrawal request endpoint.
- Participant self-service deletion/anonymisation request endpoint.
- Participant-facing correction request path.
- Participant-facing privacy/support contact route contract in API.

Largest privacy gap:

- No participant-facing authenticated request intake flow for withdrawal and deletion/anonymisation requests.

## 10. Accessibility considerations

API design should not block accessibility, but implementation must support:

- field-level structured validation errors for assistive technology mapping
- stable machine-readable error codes and human-readable messages
- support for dynamic text by avoiding hard-coded truncation assumptions in payloads
- explicit media metadata and alternatives where required by study design
- keyboard/switch workflows in client UI for all API-driven forms

No blocking API-level constraints were found for screen readers, dynamic text, or keyboard access, provided error contracts are structured and consistent.

## 11. Security and operational risks

Auth risks:

- Invitation token replay/leakage during deep-link handling if not exchanged immediately and cleared.
- Cookie-based mobile API auth fragility across WebView/network stacks.

Authorization risks:

- Any participant API accepting client participant_id would be unsafe.
- Evidence/message access must always derive participant scope from server-side session.

Duplication risks:

- Re-implementing route-local SQL logic outside participant services may diverge from web behavior.

Migration risks:

- Moving too quickly to SAS uploads without finalize workflow may weaken auditability and error recovery.

Mobile-store risks:

- Missing privacy/support/deletion URLs and unresolved data handling statements can block review.

Operational risks:

- Scan status race windows for newly uploaded evidence require clear pending state handling.
- Rate-limiting and abuse controls must be tuned for mobile retry patterns.

Logging/privacy risks:

- Token, message body, and evidence metadata leakage in client logs or backend request logs.

Largest unresolved technical risk:

- Robust resumable evidence upload and finalize design that preserves malware-scan gating and audit integrity under unreliable mobile networks.

## 12. Implementation sequence

1. Add participant API auth dependency and mobile session issuance/revocation using opaque hashed tokens.
2. Add invitation exchange endpoint with replay protections and strict rate limiting.
3. Add read endpoints: session, studies, portal, activities, activity detail, messages.
4. Add write endpoints: draft, submit, participant message.
5. Add evidence upload endpoint using multipart parity with current route behavior.
6. Add evidence status endpoint and consistent polling semantics.
7. Add privacy request intake endpoints for withdrawal and deletion requests.
8. Extend tests for API contracts, authz boundaries, rate limits, and parity with existing web behavior.
9. Review staging telemetry and privacy leakage controls before broader rollout.

## 13. Facts

- Participant web auth today uses public_auth_session cookie with server-side hashed session lookup.
- Participant portal currently depends on a single participant invitation context.
- CSRF enforcement exists for form-based POST routes.
- Participant portal write routes already apply rate limits.
- Messaging service now supports participant-visible filtering and sender semantics.
- Staff privacy export/delete/anonymise exists; participant-facing privacy request API does not.
- Evidence download is blocked unless scan is clean (except explicit development override).

## 14. Assumptions

- Mobile app requires API-first integration beyond current HTML rendering.
- Participant may need to see more than one enrolled study in future, despite current invitation-scoped portal.
- Mobile app will operate over TLS-only production endpoints and verified app links.

## 15. Unknowns

- Final participant identity model across multiple studies/organisations.
- Final session lifetime, inactivity timeout, and multi-device concurrency policy.
- Final upload max sizes and resumable upload product policy.
- Final participant-facing legal/privacy wording and controller-specific disclosures.
- Final support and privacy contact URLs.

## 16. Recommendations requiring approval

- Approval to introduce bearer-token participant API auth while keeping existing web cookie flows unchanged.
- Approval for 15-endpoint API scope as the smallest useful mobile surface.
- Approval for phased evidence strategy: multipart first, staged resumable SAS session model second.
- Approval to add participant-facing withdrawal and deletion request intake workflows.
- Approval of token replay controls for participant invitation exchange.

## OpenAPI contract reference

The proposed OpenAPI 3.1 contract for this design is documented in
docs/participant-api-v1.yaml.

This specification is proposed only and not yet implemented in application routes.
