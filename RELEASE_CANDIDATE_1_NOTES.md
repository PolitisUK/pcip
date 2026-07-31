# Release Candidate 1 Notes

Date: 2026-07-23

## Scope

This release candidate consolidates Milestones 1 through 10 and focuses on production-pilot readiness for:
- authentication hardening
- authorization controls
- hosted configuration safety
- malware and webhook security
- abuse rate limiting
- session invalidation
- strict CSP
- public token exposure reduction
- privacy management tooling
- CI security checks

## Verification summary

- Full regression suite: `65 passed, 3 warnings`.
- Security middleware present:
  - trusted hosts
  - strict security headers
  - CSP with nonce-based script policy
- Authentication controls verified in tests:
  - CSRF
  - lockout
  - session invalidation
  - token exchange + replay prevention
- Authorization boundaries verified in tests:
  - role boundaries
  - organisation isolation
  - scoped researcher access
- CI now includes:
  - dependency integrity check (`pip check`)
  - vulnerability scan (`pip-audit`)
  - security lint (`bandit`)
  - release image smoke check (`/health`)

## Code hygiene updates for RC1

- Removed dead helper no longer used after token-session exchange flow.
- Removed unused imports in core modules.
- Updated stale README version/test references.

## Known warnings

- FastAPI startup lifecycle warning:
  - `@app.on_event("startup")` deprecation warning remains.
- Python 3.13 deprecation warning from transitive dependency (`crypt` via passlib internals).

These do not block pilot but should be addressed post-pilot.

## Production pilot readiness confidence

Estimated confidence: **0.84 / 1.00**

Confidence rationale:
- strong: test coverage and cumulative hardening controls
- moderate risk: in-memory rate limiter statefulness across multi-instance deployments, startup lifecycle deprecation, and operational maturity tasks listed in technical debt
