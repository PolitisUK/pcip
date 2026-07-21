# Increment 6 Report

## Objective

Make PCIP materially easier to deploy and administer in Microsoft Azure, while adding Microsoft Entra ID researcher sign-in.

## Delivered

1. Microsoft Entra ID OpenID Connect authentication.
2. Account linking and controlled optional provisioning.
3. ACR and PostgreSQL resources in Bicep.
4. Key Vault-backed App Service settings.
5. GitHub workload-identity deployment workflow.
6. Automatic database migration at application startup.
7. Hosted-environment controls that prevent demonstration data seeding.
8. Migration and regression tests.

## Deliberate limitations

- Entra auto-provisioning is off by default.
- Local login remains enabled in the deployment template to avoid administrative lockout during the first deployment.
- PostgreSQL public networking is retained for this development-oriented release. Private endpoints and VNet integration remain a production-hardening task.
- The Entra application secret uses a conventional client secret. A certificate or federated application credential should be considered later.
- Microsoft-native transactional email is not yet included.

## Recommended next increment

Version 0.7.0 should focus on private networking, Microsoft-native email, richer Application Insights telemetry, deployment slots, backups and operational administration.
