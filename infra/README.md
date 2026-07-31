# Azure deployment foundation

`main.bicep` represents a complete PCIP environment: Linux App Service and
plan, ACR, PostgreSQL Flexible Server, Blob Storage and Defender scanning, Key
Vault, Log Analytics, Application Insights, identities, and role assignments.

The defaults are a deployment foundation, not an approved production
resilience or network design. In particular, the default PostgreSQL tier has no
high availability or geo-redundant backup, and several services permit public
network access.

Hosted migration execution defaults to `runMigrations=false`. A reviewed
database migration must run once as a release operation; restarting or scaling
the Web App must not implicitly change the schema. The development parameter
example opts into automatic migration.

Do not deploy this template to production until the current database revision,
rollback artifact, resource names, and secure parameters have been verified.
The canonical deployment procedure and operating controls are maintained in:

- `../DEPLOYMENT.md`
- `../OPERATIONS.md`
- `../AZURE_CONFIGURATION_GUIDE.md`
- `../ENVIRONMENT_VARIABLES.md`
