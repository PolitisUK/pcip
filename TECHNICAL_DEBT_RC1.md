# Remaining Technical Debt (RC1)

## High priority

1. Replace in-memory rate limiter with shared backend for multi-instance correctness.
2. Migrate startup hooks from deprecated `@app.on_event("startup")` to lifespan handlers.
3. Replace wildcard model imports in main app module with explicit imports for static-analysis clarity.

## Medium priority

1. Add structured logging fields consistently across auth/privacy/security events.
2. Add CI gate for style/lint consistency (without major runtime increase).
3. Add migration health check command in release workflow before app boot.
4. Expand accessibility testing automation beyond existing baseline assertions.

## Lower priority

1. Improve CSS architecture (split monolithic stylesheet, maintain responsive tokens).
2. Introduce typed DTOs for export payloads to tighten schema guarantees.
3. Add operational runbooks for backup restore and disaster recovery drills.

## Risk notes

- Current pilot posture is acceptable with controls in place, but scaling and operability risk increases without shared rate-limit state and lifecycle refactor.
