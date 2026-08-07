targetScope = 'resourceGroup'

param prefix string = 'pcip'
param location string = resourceGroup().location
param environmentName string = 'dev'
param containerImageTag string = '0.6.0'
param appServiceSku string = 'B1'
param postgresSku string = 'Standard_B1ms'
param postgresTier string = 'Burstable'
param postgresVersion string = '16'
param postgresAdminUser string = 'pcipadmin'
@secure()
param postgresAdminPassword string
@secure()
param secretKey string
@secure()
param defenderWebhookSecret string
@secure()
param entraClientSecret string = ''
param entraTenantId string = ''
param entraClientId string = ''
param entraAllowedDomains string = ''
param entraDefaultOrganisationSlug string = ''
param defenderMonthlyScanCapGB int = 10
param runMigrations bool = false

var suffix = uniqueString(subscription().subscriptionId, resourceGroup().id, prefix, environmentName)
var compact = toLower(replace('${prefix}${environmentName}${take(suffix, 8)}', '-', ''))
var storageName = take('${compact}st', 24)
var registryName = take('${compact}acr', 50)
var appName = '${prefix}-${environmentName}-${take(suffix, 6)}'
var appHostName = '${appName}.azurewebsites.net'
var isProduction = toLower(environmentName) == 'production'
var publicHostName = isProduction ? 'citizencentric.co.uk' : appHostName
var trustedHostNames = isProduction ? '${appHostName},citizencentric.co.uk,www.citizencentric.co.uk' : appHostName
var allowedOriginList = isProduction ? 'https://${appHostName},https://citizencentric.co.uk,https://www.citizencentric.co.uk' : 'https://${appHostName}'
var planName = '${appName}-plan'
var insightsName = '${appName}-appi'
var logName = '${appName}-log'
var vaultName = take('${prefix}-${environmentName}-${take(suffix, 6)}-kv', 24)
var postgresName = take('${prefix}-${environmentName}-${take(suffix, 8)}-pg', 63)
var databaseName = 'pcip'
var databaseUrl = 'postgresql+psycopg://${postgresAdminUser}:${uriComponent(postgresAdminPassword)}@${postgresName}.postgres.database.azure.com:5432/${databaseName}?sslmode=require'
var imageName = '${registryName}.azurecr.io/pcip:${containerImageTag}'

resource log 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logName
  location: location
  properties: {
    retentionInDays: 30
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: insightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: log.id
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: registryName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_ZRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
    networkAcls: { defaultAction: 'Allow' }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 14 }
    containerDeleteRetentionPolicy: { enabled: true, days: 14 }
  }
}

resource evidenceContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'evidence'
  properties: { publicAccess: 'None' }
}

resource defender 'Microsoft.Security/defenderForStorageSettings@2025-06-01' = {
  scope: storage
  name: 'current'
  properties: {
    isEnabled: true
    overrideSubscriptionLevelSettings: true
    malwareScanning: {
      blobScanResultsOptions: 'blobIndexTags'
      onUpload: { isEnabled: true, capGBPerMonth: defenderMonthlyScanCapGB }
    }
    sensitiveDataDiscovery: { isEnabled: false }
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresName
  location: location
  sku: { name: postgresSku, tier: postgresTier }
  properties: {
    version: postgresVersion
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 14, geoRedundantBackup: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
    highAvailability: { mode: 'Disabled' }
  }
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: databaseName
  properties: {}
}

resource azureServicesFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: vaultName
  location: location
  properties: {
    tenantId: tenant().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 30
    sku: { family: 'A', name: 'standard' }
    publicNetworkAccess: 'Enabled'
  }
}

resource dbSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'database-url'
  properties: { value: databaseUrl }
}
resource sessionSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'session-secret'
  properties: { value: secretKey }
}
resource webhookSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'defender-webhook-secret'
  properties: { value: defenderWebhookSecret }
}
resource entraSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(entraClientSecret)) {
  parent: vault
  name: 'entra-client-secret'
  properties: { value: entraClientSecret }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  sku: { name: appServiceSku }
  kind: 'linux'
  properties: { reserved: true }
}

resource app 'Microsoft.Web/sites@2023-12-01' = {
  name: appName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    clientAffinityEnabled: false
    siteConfig: {
      linuxFxVersion: 'DOCKER|${imageName}'
      acrUseManagedIdentityCreds: true
      alwaysOn: true
      healthCheckPath: '/health/ready'
      minimumElasticInstanceCount: 1
      appSettings: [
        { name: 'APP_NAME', value: 'Citizen Centric' }
        { name: 'ENVIRONMENT', value: environmentName }
        { name: 'SEED_DEMO_DATA', value: 'false' }
        { name: 'DATABASE_URL', value: '@Microsoft.KeyVault(SecretUri=${dbSecret.properties.secretUriWithVersion})' }
        { name: 'SECRET_KEY', value: '@Microsoft.KeyVault(SecretUri=${sessionSecret.properties.secretUriWithVersion})' }
        { name: 'BASE_URL', value: 'https://${publicHostName}' }
        { name: 'COOKIE_SECURE', value: 'true' }
        { name: 'SESSION_COOKIE_SECURE', value: 'true' }
        { name: 'TRUSTED_HOSTS', value: trustedHostNames }
        { name: 'ALLOWED_ORIGINS', value: allowedOriginList }
        { name: 'STORAGE_BACKEND', value: 'azure_blob' }
        { name: 'AZURE_STORAGE_ACCOUNT_URL', value: storage.properties.primaryEndpoints.blob }
        { name: 'AZURE_STORAGE_CONTAINER', value: evidenceContainer.name }
        { name: 'AZURE_DEFENDER_WEBHOOK_SECRET', value: '@Microsoft.KeyVault(SecretUri=${webhookSecret.properties.secretUriWithVersion})' }
        { name: 'DEFENDER_REQUIRE_CLEAN_DOWNLOAD', value: 'true' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'RUN_MIGRATIONS', value: string(runMigrations) }
        { name: 'ENTRA_ENABLED', value: string(!empty(entraClientId)) }
        { name: 'ENTRA_TENANT_ID', value: entraTenantId }
        { name: 'ENTRA_CLIENT_ID', value: entraClientId }
        { name: 'ENTRA_CLIENT_SECRET', value: empty(entraClientSecret) ? '' : '@Microsoft.KeyVault(SecretUri=${entraSecret.properties.secretUriWithVersion})' }
        { name: 'ENTRA_ALLOWED_DOMAINS', value: entraAllowedDomains }
        { name: 'ENTRA_DEFAULT_ORGANISATION_SLUG', value: entraDefaultOrganisationSlug }
        { name: 'ENTRA_AUTO_PROVISION', value: 'false' }
        { name: 'LOCAL_LOGIN_ENABLED', value: 'true' }
      ]
    }
  }
  dependsOn: [postgresDatabase, azureServicesFirewall]
}

resource blobOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(evidenceContainer.id, app.id, 'blob-owner')
  scope: evidenceContainer
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b')
  }
}

resource blobDelegator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, app.id, 'blob-delegator')
  scope: storage
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a')
  }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, app.id, 'acr-pull')
  scope: registry
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource keyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, app.id, 'secrets-user')
  scope: vault
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

output appUrl string = 'https://${appHostName}'
output appName string = app.name
output storageAccountName string = storage.name
output registryName string = registry.name
output registryLoginServer string = registry.properties.loginServer
output postgresServerName string = postgres.name
output keyVaultName string = vault.name
output managedIdentityPrincipalId string = app.identity.principalId
output entraRedirectUri string = 'https://${appHostName}/auth/entra/callback'
