# Environment Variables

This document lists runtime environment variables used by Citizen Centric.

## Core

- `APP_NAME` (default: `Citizen Centric`)
- `ENVIRONMENT` (default: `development`)
- `SECRET_KEY` (required outside development; strong and non-default)
- `BASE_URL` (HTTPS required outside development)
- `LOG_LEVEL` (default: `INFO`)

## Session and Cookies

- `COOKIE_SECURE` (default: `false`, must be `true` outside development)
- `SESSION_COOKIE_SECURE` (default: `false`, must be `true` outside development)
- `SESSION_MAX_AGE_SECONDS` (default: `43200`)

## Database

- `DATABASE_URL` (default local sqlite; must be non-sqlite outside development)
- `STARTUP_VALIDATE_MIGRATIONS` (default: `true`)

## Host and Origin Protection

- `TRUSTED_HOSTS`
- `ALLOWED_ORIGINS`

## Login and Lockout

- `LOCAL_LOGIN_ENABLED` (default: `true`)
- `LOGIN_MAX_FAILED_ATTEMPTS` (default: `5`)
- `LOGIN_LOCKOUT_SECONDS` (default: `900`)

## Rate Limiting

- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_LOGIN_IP`
- `RATE_LIMIT_LOGIN_ACCOUNT`
- `RATE_LIMIT_FORGOT_PASSWORD_IP`
- `RATE_LIMIT_FORGOT_PASSWORD_ACCOUNT`
- `RATE_LIMIT_PASSWORD_RESET_IP`
- `RATE_LIMIT_PASSWORD_RESET_TOKEN`
- `RATE_LIMIT_INVITATION_ACCEPT_IP`
- `RATE_LIMIT_INVITATION_ACCEPT_TOKEN`
- `RATE_LIMIT_PORTAL_WRITE_IP`
- `RATE_LIMIT_PORTAL_WRITE_TOKEN`

## Upload and Evidence

- `MAX_UPLOAD_MB`
- `ALLOWED_UPLOAD_EXTENSIONS`
- `STORAGE_BACKEND` (`local` or `azure_blob`)
- `LOCAL_STORAGE_PATH`
- `AZURE_STORAGE_ACCOUNT_URL`
- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_STORAGE_CONTAINER`
- `AZURE_SAS_MINUTES`

## Malware Controls

- `AZURE_DEFENDER_WEBHOOK_SECRET` (required outside development)
- `DEFENDER_REQUIRE_CLEAN_DOWNLOAD`
- `DEVELOPMENT_ALLOW_UNSCANNED_DOWNLOADS`
- `CLAMAV_HOST`
- `CLAMAV_PORT`

## Microsoft Entra ID

- `ENTRA_ENABLED`
- `ENTRA_TENANT_ID`
- `ENTRA_CLIENT_ID`
- `ENTRA_CLIENT_SECRET`
- `ENTRA_DEFAULT_ORGANISATION_SLUG`
- `ENTRA_ALLOWED_DOMAINS`
- `ENTRA_AUTO_PROVISION`
- `ENTRA_DEFAULT_ROLE`

## Email

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_USE_TLS`

## Privacy

- `PRIVACY_RETENTION_DAYS`
- `PRIVACY_RETENTION_STATUSES`
- `PRIVACY_RETENTION_ACTION`

## Telemetry

- `APPLICATIONINSIGHTS_CONNECTION_STRING`

## Seed Data

- `SEED_DEMO_DATA` (set to `false` in production)

## Azure Key Vault Integration

- `KEY_VAULT_URL`
- `KEY_VAULT_SECRET_DATABASE_URL`
- `KEY_VAULT_SECRET_SECRET_KEY`
- `KEY_VAULT_SECRET_DEFENDER_WEBHOOK`
- `KEY_VAULT_SECRET_ENTRA_CLIENT_SECRET`

When `KEY_VAULT_URL` is configured, runtime attempts to load secrets for any of the above secret-backed values that are not already provided through direct environment variables.
