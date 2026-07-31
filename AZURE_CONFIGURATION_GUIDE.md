# Azure Configuration Guide

This guide maps Citizen Centric configuration to Azure App Service, Azure Storage, Azure Key Vault, and Microsoft Entra ID.

## 1. Azure App Service

Required App Service settings:

- `ENVIRONMENT=production`
- `BASE_URL=https://<your-app-host>`
- `COOKIE_SECURE=true`
- `SESSION_COOKIE_SECURE=true`
- `TRUSTED_HOSTS=<your-app-host>`
- `ALLOWED_ORIGINS=https://<your-app-host>`
- `RUN_MIGRATIONS=false` for the web application; run migrations once through
  the approved release migration operation
- `LOG_LEVEL=INFO`

Health check:

- `siteConfig.healthCheckPath=/health`

## 2. Azure SQL-Compatible Database URL

Set `DATABASE_URL` to your Azure-hosted database connection string.

Repository default production template uses PostgreSQL syntax:

```text
postgresql+psycopg://<user>:<password>@<server>.postgres.database.azure.com:5432/<db>?sslmode=require
```

Production startup validation rejects SQLite URLs.

## 3. Azure Blob Storage

Set:

- `STORAGE_BACKEND=azure_blob`
- `AZURE_STORAGE_ACCOUNT_URL=https://<storage-account>.blob.core.windows.net/`
- `AZURE_STORAGE_CONTAINER=evidence`

Optional alternative:

- `AZURE_STORAGE_CONNECTION_STRING=<connection-string>`

Managed identity is recommended over shared keys.

## 4. Microsoft Entra ID

Enable Entra auth:

- `ENTRA_ENABLED=true`
- `ENTRA_TENANT_ID=<tenant-guid>`
- `ENTRA_CLIENT_ID=<app-registration-client-id>`
- `ENTRA_CLIENT_SECRET=<secret value or Key Vault reference>`

Optional controls:

- `ENTRA_ALLOWED_DOMAINS=example.gov.uk`
- `ENTRA_DEFAULT_ORGANISATION_SLUG=<slug>`
- `ENTRA_AUTO_PROVISION=false`

Callback URL:

- `https://<your-app-host>/auth/entra/callback`

## 5. Azure Key Vault

Two supported patterns:

1. App Service Key Vault references in app settings (recommended).
2. Runtime Key Vault loading by setting:
- `KEY_VAULT_URL=https://<vault-name>.vault.azure.net/`

Runtime loader attempts these secret names when corresponding env vars are not directly set:

- `database-url` -> `DATABASE_URL`
- `session-secret` -> `SECRET_KEY`
- `defender-webhook-secret` -> `AZURE_DEFENDER_WEBHOOK_SECRET`
- `entra-client-secret` -> `ENTRA_CLIENT_SECRET`

Custom secret names can be configured with:

- `KEY_VAULT_SECRET_DATABASE_URL`
- `KEY_VAULT_SECRET_SECRET_KEY`
- `KEY_VAULT_SECRET_DEFENDER_WEBHOOK`
- `KEY_VAULT_SECRET_ENTRA_CLIENT_SECRET`

## 6. Application Insights and Logging

Set:

- `APPLICATIONINSIGHTS_CONNECTION_STRING=<value>`
- `LOG_LEVEL=INFO` (or `WARNING`/`ERROR`)

Logging initializes at startup and emits timestamped structured log lines.

## 7. Startup Validation Controls

- `STARTUP_VALIDATE_MIGRATIONS=true`

In hosted environments, startup checks Alembic head alignment and fails fast if migration state is behind.
