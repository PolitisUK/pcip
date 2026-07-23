# Citizen Centric Azure Deployment Guide

This guide covers production deployment of Citizen Centric on Microsoft Azure App Service with Azure SQL-compatible database connectivity, Azure Blob Storage, Microsoft Entra ID, and Azure Key Vault.

## 1. Production Architecture

- Runtime: Azure App Service (Linux container)
- Database: Azure Database service exposed through `DATABASE_URL` (recommended PostgreSQL Flexible Server URL used by this repository)
- File storage: Azure Blob Storage (`STORAGE_BACKEND=azure_blob`)
- Identity: Microsoft Entra ID (OIDC)
- Secrets: Azure Key Vault (App Service Key Vault references and optional runtime Key Vault loading)
- Telemetry: Application Insights + structured application logs

## 2. Pre-Deployment Checklist

1. Build and push the container image used by App Service.
2. Provision Azure resources using Bicep in [infra/main.bicep](infra/main.bicep).
3. Configure App Service managed identity permissions:
- Storage Blob Data Contributor on Storage Account
- AcrPull on Container Registry
- Key Vault Secrets User on Key Vault
4. Confirm required secrets exist in Key Vault:
- `database-url`
- `session-secret`
- `defender-webhook-secret`
- `entra-client-secret` (if Entra local secret is used)
5. Set `SEED_DEMO_DATA=false` in production.

## 3. Deploy Infrastructure

```bash
az group create --name cc-prod-rg --location uksouth
az deployment group create \
  --resource-group cc-prod-rg \
  --template-file infra/main.bicep \
  --parameters prefix=cc environmentName=prod \
  --parameters postgresAdminPassword='<secure value>' \
  --parameters secretKey='<secure value>' \
  --parameters defenderWebhookSecret='<secure value>'
```

## 4. Container Startup and Migrations

The container entrypoint runs migrations before application startup:

```sh
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi
```

This ensures schema upgrades are applied automatically during deployment.

## 5. Startup Validation Behavior

On startup, the application now performs:

1. Runtime configuration safety validation for hosted environments.
2. Database connectivity check (`SELECT 1`).
3. Migration head validation in hosted environments (checks `alembic_version` against Alembic heads).
4. Structured logging initialization with `LOG_LEVEL`.

If a required production condition is missing, startup fails fast.

## 6. Health Monitoring

Health endpoint:

- `GET /health`

Response includes:

- `status`
- `version`
- `environment`
- `storage_backend`

Configure Azure App Service health check path as `/health`.

## 7. Post-Deployment Validation

1. Browse `/health` and verify status is `ok`.
2. Confirm sign-in page loads and CSP headers are present.
3. Execute a login and logout cycle.
4. Upload a test evidence file and confirm malware scan gating behavior.
5. Validate Entra sign-in callback URL:
- `https://<app-host>/auth/entra/callback`
6. Confirm logs appear in Application Insights.

## 8. Rollback Guidance

1. Redeploy the previous container image tag.
2. Keep `RUN_MIGRATIONS=true` (migrations are forward-only; rollback scripts require explicit planning).
3. Validate `/health` and critical workflows.

## 9. Security Notes

- Do not use SQLite in production.
- Keep `COOKIE_SECURE=true` and HTTPS-only base URL.
- Keep `DEFENDER_REQUIRE_CLEAN_DOWNLOAD=true`.
- Restrict `TRUSTED_HOSTS` and `ALLOWED_ORIGINS` to production domains only.
