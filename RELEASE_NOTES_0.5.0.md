# PCIP v0.5.0 — Azure Storage and Defender Integration

This cumulative release establishes the first Azure-native runtime path.

## Delivered

- Azure Blob Storage provider using `DefaultAzureCredential` and App Service managed identity.
- Local storage retained for development and automated testing.
- Private evidence objects with non-identifying generated paths.
- SHA-256 calculated before cloud upload and persisted with each evidence record.
- Microsoft Defender for Storage pending, clean, malicious and failed scan states.
- Downloads blocked until Defender reports `No threats found` by default.
- Blob-index-tag status refresh before download.
- Event Grid-compatible Defender scan-result webhook and subscription validation response.
- Five-minute user-delegation SAS downloads rather than application proxying of cloud files.
- New Alembic migration for storage-provider and scan-completion data.
- Bicep infrastructure for App Service, managed identity, Blob Storage, Defender, Key Vault, Application Insights and Log Analytics.
- GitHub Actions test and container-build workflow.

## Deployment boundary

The Bicep template is a deployment foundation, not a production approval. Before live personal data is used, configure an approved PostgreSQL design, private networking, DNS, backup and recovery requirements, alerting, custom domain, Entra authentication, and independent assurance.
