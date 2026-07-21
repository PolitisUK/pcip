#!/usr/bin/env bash
set -euo pipefail
APP_NAME=${1:?Usage: configure_entra.sh APP_DISPLAY_NAME REDIRECT_URI}
REDIRECT_URI=${2:?Usage: configure_entra.sh APP_DISPLAY_NAME REDIRECT_URI}
TENANT_ID=$(az account show --query tenantId -o tsv)
APP_ID=$(az ad app create --display-name "$APP_NAME" --sign-in-audience AzureADMyOrg --web-redirect-uris "$REDIRECT_URI" --enable-id-token-issuance true --query appId -o tsv)
az ad sp create --id "$APP_ID" >/dev/null
SECRET=$(az ad app credential reset --id "$APP_ID" --display-name pcip-app-service --years 1 --query password -o tsv)
printf 'ENTRA_TENANT_ID=%s\nENTRA_CLIENT_ID=%s\nENTRA_CLIENT_SECRET=%s\nREDIRECT_URI=%s\n' "$TENANT_ID" "$APP_ID" "$SECRET" "$REDIRECT_URI"
