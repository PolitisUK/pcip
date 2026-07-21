#!/usr/bin/env bash
set -euo pipefail
GITHUB_ORG=${1:?Usage: configure_github_oidc.sh GITHUB_ORG REPOSITORY RESOURCE_GROUP}
REPOSITORY=${2:?Usage: configure_github_oidc.sh GITHUB_ORG REPOSITORY RESOURCE_GROUP}
RESOURCE_GROUP=${3:?Usage: configure_github_oidc.sh GITHUB_ORG REPOSITORY RESOURCE_GROUP}
APP_NAME="pcip-github-${REPOSITORY}"
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
OBJECT_ID=$(az ad app show --id "$APP_ID" --query id -o tsv)
az ad sp create --id "$APP_ID" >/dev/null
SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}"
az role assignment create --assignee "$APP_ID" --role Contributor --scope "$SCOPE" >/dev/null
cat > /tmp/pcip-federated.json <<EOF
{"name":"github-main","issuer":"https://token.actions.githubusercontent.com","subject":"repo:${GITHUB_ORG}/${REPOSITORY}:ref:refs/heads/main","description":"PCIP GitHub Actions main branch","audiences":["api://AzureADTokenExchange"]}
EOF
az ad app federated-credential create --id "$OBJECT_ID" --parameters /tmp/pcip-federated.json >/dev/null
printf 'AZURE_CLIENT_ID=%s\nAZURE_TENANT_ID=%s\nAZURE_SUBSCRIPTION_ID=%s\nAZURE_RESOURCE_GROUP=%s\n' "$APP_ID" "$TENANT_ID" "$SUBSCRIPTION_ID" "$RESOURCE_GROUP"
