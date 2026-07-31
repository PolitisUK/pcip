# PCIP Technical Debt and Engineering Roadmap

Last verified from the repository: 2026-07-28

## Classification

- **Fact** means directly verified in the repository or test output.
- **Unknown** means the repository cannot answer it.
- **Recommendation** is a proposed change, not a statement about live state.

The repository contains no current literal `TODO`, `FIXME`, `HACK`, or `XXX`
markers. Technical debt is behavioral and architectural rather than being
reliably marked in source comments.

## Completed in the current hardening increment

- Added the missing secure participant/public-session cookie setting to Bicep.
- Upgraded known-vulnerable direct dependencies and separated runtime from
  development tooling.
- Added an exact tested runtime dependency lock.
- Added dependency audit, Bandit, PostgreSQL migration, and container smoke
  checks to CI.
- Added undefined/unused-name linting and an 80% aggregate coverage floor to CI.
- Made migrations `0004` and `0005` tolerate the schema created by the legacy
  initial migration; an empty database now reaches head without drift.
- Restricted researcher project, dashboard, study, participant, and audit views
  to permitted scope.
- Made duplicate cross-organisation staff email login and password reset fail
  closed.
- Required Entra tenant claims to match the configured tenant.
- Enforced activity release/due windows in both the portal UI and submission
  endpoint.
- Added bounded CSV import and consistent create/edit validation.
- Made hosted startup reject demo-data seeding after live inventory found the
  production setting absent and therefore defaulting to `true`.
- Made container and Bicep migration defaults fail safe; only local Docker
  Compose opts into automatic migration.
- Made participant magic links reusable and revocable for their full 30-day
  invitation lifetime while continuing to exchange them for short browser
  sessions.
- Added the approved global staff identity model, role-bearing organisation
  memberships, secure organisation switching, existing-account invitation
  acceptance, and an additive `0006` backfill migration.
- Added database-backed readiness and removed environment/storage disclosure
  from liveness.
- Activated Azure Monitor OpenTelemetry explicitly.
- Moved storage initialization into lifespan startup.
- Added compensating evidence deletion when scanning or database persistence
  fails during the request.
- Replaced the deprecated FastAPI startup event with lifespan.
- Made the local in-process rate limiter thread-safe and bounded.
- Removed tracked databases, generated ARM output, Bicep backup, template
  backups, and a dead template.
- Added `.dockerignore` and expanded generated/local artifact exclusions.

Verification at this point: 80 tests pass and measured application coverage is
81%. CI-equivalent container execution remains unverified locally because no
Docker daemon is available. Ruff's enforced undefined/unused-name profile is
clean. Running its broader default profile reports 170 legacy findings, mainly
import ordering, framework dependency signatures, and broad exception
handling; these should be reduced incrementally rather than through a
format-and-rewrite change mixed into production hardening.

## Temporary workarounds and legacy compatibility

| Priority | Location | Why it exists | Still required? | Permanent solution | Implementation risk |
|---|---|---|---|---|---|
| High | `migrations/0001`, `0004`, `0005`; `app/main.py:startup` | `0001` creates current metadata instead of a deterministic historical schema, so later revisions can encounter already-present objects | Production is schema-verified and now records the controlled `0005` baseline; legacy compatibility remains for new/local installs | Replace `0001` with deterministic operations for new installs, then remove hosted `create_all` after the rollback window | High if contracted without clean-install and legacy tests |
| Critical | `.github/workflows/deploy-azure.yml` | Extended Azure debugging left mutable tags, resource-group “first resource” discovery, build-after-infrastructure ordering, and restart-based release | No as a permanent design; changing it before live inventory could remove the only known recovery path | Explicit resource IDs, build-once SHA tag, digest deployment, staging promotion, recorded rollback digest | High: deployment-path changes can interrupt service |
| High | `app/main.py` SQLite `PRAGMA` alterations | Supports databases created by early local versions | Yes for unknown local demo databases; no for hosted PostgreSQL | Time-box local compatibility, migrate supported data, then remove the shim | Low for production; medium for local users |
| High | `app/main.py` `Base.metadata.create_all` on startup | Compensates for incomplete/legacy migration history and makes local setup easy | Not required after migration authority is repaired | Alembic-only schema management and explicit local bootstrap | High until live schema is known |
| Medium | `users.organisation_id` and `users.role` retained beside `organisation_memberships` | Keeps the `0006` expansion backwards-compatible with the running application and provides a safe rollback window | Yes during the staged rollout | After all releases read memberships and rollback is no longer required, remove the legacy columns in a separately reviewed contract migration | High if contracted prematurely |
| High | No dedicated hosted migration job | Automatic startup migration was disabled to prevent concurrent or unplanned schema changes | A manual release operation is required until a job exists | Once-per-release migration job with locking, logs, and backwards-compatible rollout | High if a release omits or repeats a migration |
| High | `app/services.py` immediate SMTP inside `queue_email` | Provides delivery without a worker platform | Functionally required if SMTP is configured; operationally unsuitable | Transactional outbox worker with retry, idempotency, backoff, and monitoring | Medium: delivery behavior changes |
| High | `app/main.py` in-memory rate limiter | Provides basic abuse controls without shared infrastructure | Useful for one process, incomplete across instances | Shared atomic limiter, normally Redis/Azure Cache, with proxy-aware client IP handling | Medium |
| Medium | `LOCAL_LOGIN_ENABLED=true` in Bicep | Avoids administrative lockout while Entra rollout is incomplete | Unknown in live operations | Break-glass local account procedure and Entra-first policy, then disable routine local login | High if changed without tested admin recovery |
| Medium | Broad exception translation around unique inserts | Simplifies user errors but can mask unrelated database failures | No | Catch `IntegrityError`, inspect the violated constraint where portable, log unexpected failures | Low |
| Medium | Import-time settings, engine, OAuth, storage, and telemetry construction | Simple monolith composition | Yes for current tests/runtime | Incremental application factory and explicit dependency construction | Medium; avoid framework-wide rewrite |
| Medium | Broad Ruff profile is not clean | Existing style, broad exception, and FastAPI-signature patterns predate the enforced lint profile | Yes as a bounded backlog; undefined and unused names are already enforced | Ratchet focused rule groups in CI and fix touched modules without a repository-wide behavioral rewrite | Low per focused change; medium if applied mechanically across `app/main.py` |
| Low | Optional demo seeding and known demo credentials | Makes local onboarding easy | Local only; Bicep disables it | Keep isolated to an explicit development command/fixture | Low |
| Low | Numerous historical increment/release documents | Records prior work but duplicates current operational truth | Not for runtime | Archive historical documents and link to the four maintained documents | Low |

## Production risks

| Rank | Risk | Likelihood | Impact | Recommended mitigation |
|---:|---|---|---|---|
| 1 | The live tag/digest is inventoried, but source commit and exact pulled digest remain unknown; the database now has a controlled `0005` baseline | High until completed | Critical: unsafe deployment or incompatible rollback | Correlate ACR build provenance and test rollback before deploy |
| 2 | Non-deterministic migration baseline plus startup `create_all` | Medium | Critical: failed startup or schema divergence | Reconcile live schema/revision, test a production clone, move to Alembic-only |
| 3 | Mutable/operator-provided image tags and ambiguous resource selection | Medium | Critical: wrong resource or untraceable image deployed | Explicit resource IDs and digest-based promotion |
| 3a | Live `0.6.0` has liveness but no readiness endpoint and discloses environment/storage details in health output | High until hardened release | High: Azure cannot remove a database-unready instance and operational metadata is unnecessarily public | Stage the hardened image, verify `/health/ready`, then configure the App Service health path |
| 4 | Live PostgreSQL has public access, no HA or geo-redundant backup, and its Burstable tier rejects on-demand backups | Medium | Critical: exposure or extended data/service loss | Private networking, resilient tier/HA design, suitable on-demand recovery points, and a restore exercise |
| 5 | SMTP executes synchronously and failures do not have a worker retry path | High when email is enabled | High: slow requests and missed invitations/resets | Transactional outbox worker, retry policy, alerts |
| 6 | Participant re-entry semantics do not match a 30-day invitation expectation | High after 12 hours | High: participants lose access and research completion falls | Choose and implement an explicit re-entry model |
| 7 | Evidence blob and database metadata are not transactionally coordinated; request-time cleanup now covers handled failures but not process termination | Low-to-medium | High: orphaned blobs or metadata after partial failure | Reconciliation job and idempotent upload workflow |
| 8 | Rate limits are per process and trust the direct request address | Medium | High for public auth endpoints under scale/proxy | Shared limiter and verified forwarded-client-IP configuration |
| 9 | Tenant isolation is application-enforced without database RLS | Low-to-medium | Critical if any query omits scope | Continue authorization tests, scoped query helpers, consider PostgreSQL RLS after model stabilizes |
| 10 | Privacy deletion/anonymisation semantics lack confirmed legal policy | Medium | High: excessive deletion or retention | Approve policy, legal basis, audit retention, hold/export process |
| 11 | One Uvicorn process and low default Azure SKUs limit availability/capacity | Medium | High under failure or load | Measure traffic, define SLO, load test, right-size and scale safely |
| 12 | Evidence type validation relies largely on filename/declared content type | Medium | High: unsafe/unexpected content processing | Signature/type detection, quarantine, size/stream controls, scan-state tests |
| 13 | Core application is concentrated in `app/main.py` | High | Medium: slower review and higher regression risk | Extract cohesive workflow modules incrementally with tests |
| 14 | Password stack emits a Python 3.13 `crypt` deprecation warning | Certain on current test runtime warning path | Medium during future runtime upgrade | Select maintained password library/algorithm and plan transparent rehash |
| 15 | New FastAPI TestClient emits an `httpx` compatibility deprecation warning | Certain in tests | Low today; future test break | Adopt the supported test client package after compatibility verification |

## Unknowns that require external evidence or a decision

- Whether Bicep owns every live resource; the most recent observed
  infrastructure deployments failed and live configuration has drifted.
- Source commit and exact running-container correlation for the inventoried
  `0.6.0` manifest digest; whether it is a proven last known good rollback.
- Uninspected app-setting presence, Key Vault reference resolution, and managed
  identity role health.
- Live PostgreSQL revision, schema drift, size, active connections, backup
  configuration, and restore-test history.
- Live App Service SKU/scale and slots, plus availability requirements, SLOs,
  RTO, and RPO.
- Application/HTTP/container log collection, alerts, dashboards, and paging
  ownership.
- SMTP provider, delivery volumes, bounce handling, and data-processing terms.
- The staging and release window required before running the additive
  organisation-membership migration.
- Approved privacy deletion, legal hold, audit retention, and evidence retention
  semantics.
- Whether public endpoints sit behind a trusted reverse proxy/WAF and which
  forwarded-IP headers can be trusted.
- Real participant, study, evidence volume and performance profile.

## Prioritised roadmap

### Critical

1. Complete the live inventory with database revision, image-build provenance,
   logs/telemetry, plan/scale, and restore evidence; write and test rollback.
2. Create a protected canonical integration/release branch from the newest
   approved code and deploy an immutable candidate to staging.
3. Reconcile migration history against a production clone; make Alembic the sole
   hosted schema authority.
4. Replace ambiguous/mutable production deployment with explicit digest-based
   promotion and post-deployment verification.
5. Validate database network exposure, backup restoration, HA, RTO, and RPO.

### High

1. Move SMTP delivery to a monitored transactional outbox worker.
2. Add evidence reconciliation and stronger content validation.
3. Adopt a shared rate limiter before scale-out.
4. Approve and test privacy deletion/retention behavior.
5. Add release telemetry, alerts, and operational dashboards.

### Medium

1. Split cohesive routes/workflows out of `app/main.py`.
2. Replace broad database exception handling with typed failures.
3. Add PostgreSQL authorization/integration tests for key tenant boundaries.
4. Add Azure Blob, Defender webhook, SMTP, Entra, and observability adapter
   contract tests.
5. Remove import-time side effects through a small application factory.
6. Plan password-library migration before Python 3.13.

### Low

1. Archive superseded increment and release-candidate documents.
2. Move demo data generation to an explicit development-only command.
3. Improve template ergonomics for demographics schema editing.
4. Add static typing after the module boundaries are clearer.

### Quick wins

1. Configure branch protection and require all CI jobs.
2. Add explicit ACR and Web App names to deployment environment variables.
3. Record commit SHA, image digest, and Alembic revision in each release record.
4. Add a post-deploy smoke checklist for login, portal, evidence, and telemetry.
5. Raise coverage floors selectively for security, storage, configuration, and
   integration modules while preserving meaningful tests over line chasing.

### Long-term improvements

1. Private endpoints/VNet integration for data services.
2. Tested zone/region recovery design based on approved RTO/RPO.
3. PostgreSQL row-level security as defence in depth.
4. Background job platform for email, retention, reconciliation, and heavy
   evidence work.
5. Capacity testing and SLO-driven autoscaling.
