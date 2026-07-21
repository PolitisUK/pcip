# Increment 1 delivery report

## Objective
Create a dependable commercial foundation before adding research-specific complexity.

## Acceptance checks
- Clean database initialisation
- Valid and invalid login handling
- Organisation-scoped dashboard
- Project creation
- Unique project codes within an organisation
- Researcher invitation creation
- Email outbox capture
- Role-protected researcher and audit pages
- Audit event persistence
- Health endpoint
- Docker/PostgreSQL configuration
- Automated tests

## Security decisions
- Passwords are hashed with bcrypt
- Sessions are signed and HTTP-only
- Role checks are enforced server-side
- All principal records carry an organisation identifier
- Tenant-scoped queries are used throughout this increment
- Invitation tokens are stored only as SHA-256 hashes
- Activation links expire after 48 hours

## Remaining assurance work
Independent penetration testing, MFA/SSO, CSRF protection, rate limiting, secure headers, secrets management, dependency scanning, database migrations, backup/restore testing and formal DPIA support remain necessary before launch.
