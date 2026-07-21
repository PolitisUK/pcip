# PCIP v0.6.0 — Microsoft Identity and Automated Azure Delivery

This cumulative release advances the Azure foundation into a repeatable deployment model.

## Microsoft Entra ID

- OpenID Connect sign-in for researcher accounts
- Single-tenant Microsoft Entra configuration
- Existing PCIP users can be linked by verified email address
- Optional, controlled auto-provisioning into one configured organisation
- Optional email-domain allow-list
- Local password login can remain enabled during transition or be disabled later
- External identity and last-login fields added to the user model

## Azure infrastructure

The Bicep template now provisions:

- Azure Container Registry
- Azure App Service with managed identity
- Azure Database for PostgreSQL Flexible Server
- Azure Blob Storage and private evidence container
- Microsoft Defender for Storage on-upload scanning
- Azure Key Vault
- Key Vault references for database, session, Defender and Entra secrets
- Application Insights and Log Analytics
- managed-identity role assignments for Blob Storage, ACR and Key Vault

## Delivery automation

- GitHub Actions Azure deployment workflow using workload identity federation
- Azure Container Registry cloud build
- automatic App Service restart after deployment
- deployment helper for GitHub OIDC configuration
- Microsoft Entra application-registration helper
- automatic Alembic migration execution at container startup

## Production safeguards

- demonstration data seeding is disabled by the Azure template
- hosted configuration is explicit through `ENVIRONMENT`
- passwords and service secrets are no longer passed directly as ordinary application values in the Azure template
- Defender clean-file controls from v0.5.0 remain enforced

## Database

Migration `0003` adds:

- `users.external_provider`
- `users.external_subject`
- `users.last_login_at`

## Verification

- 18 automated tests pass
- clean database migration chain verified through revision `0003`
