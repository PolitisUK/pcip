# Recommended Roadmap After Pilot

## Phase 1: Stabilisation (0-4 weeks)

1. Replace in-memory throttling with shared store (Redis or equivalent).
2. Implement FastAPI lifespan startup/shutdown migration.
3. Add deployment rollback automation and migration preflight checks.
4. Tighten observability dashboards for auth, privacy, and evidence flows.

## Phase 2: Hardening (1-2 months)

1. Expand security testing:
   - negative-path authz tests
   - header and CSP regression matrix
2. Add SBOM generation and signed release artifacts.
3. Add periodic dependency update automation with controlled PR workflow.
4. Expand privacy automation reporting (action outcomes and audit analytics).

## Phase 3: Scale readiness (2-4 months)

1. Introduce background task processing for heavy workflows (email/retention jobs).
2. Optimise data access patterns and pagination coverage for larger datasets.
3. Add role-appropriate UI telemetry for operator workflows.
4. Formalise SLOs and error-budget policies for service reliability.

## Exit criteria for broader rollout

1. Pilot reliability targets met.
2. No unresolved high-severity security findings.
3. Operational runbooks exercised successfully.
4. Stakeholder sign-off on privacy and support workflows.
