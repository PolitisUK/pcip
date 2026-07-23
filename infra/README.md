# Azure deployment foundation

This folder provisions the first Azure-native PCIP environment using Bicep:

- Linux Azure App Service with a system-assigned managed identity;
- private evidence container in Azure Blob Storage;
- Microsoft Defender for Storage with on-upload malware scanning and blob-index scan results;
- Storage Blob Data Contributor access for the web application's managed identity;
- Application Insights and Log Analytics;
- Azure Key Vault foundation;
- HTTPS-only App Service configuration.

The database URL is supplied as a secure deployment parameter so Azure Database for PostgreSQL Flexible Server can be created separately with an approved networking and resilience design. The container image placeholder must be replaced with the selected Azure Container Registry or GitHub Container Registry image.

## Deploy

```bash
az group create --name pcip-dev-rg --location uksouth
az deployment group create \
  --resource-group pcip-dev-rg \
  --template-file infra/main.bicep \
  --parameters prefix=pcip environmentName=dev \
  --parameters databaseUrl='<postgresql URL>' secretKey='<long random value>' defenderWebhookSecret='<long random value>'
```

After deployment, configure an Event Grid delivery of Defender scan results to:

```text
https://<app-host>/webhooks/defender-storage?secret=<the configured secret>
```

Blob tags are also checked directly before each download. A participant upload remains unavailable until the result is `No threats found` when `DEFENDER_REQUIRE_CLEAN_DOWNLOAD=true`.

Additional deployment and configuration references:

- `DEPLOYMENT_GUIDE_AZURE.md`
- `AZURE_CONFIGURATION_GUIDE.md`
- `ENVIRONMENT_VARIABLES.md`
