targetScope = 'resourceGroup'

@allowed([
  'staging'
  'production'
])
param environmentName string

@description('Existing Citizen Centric App Service that will call the provider.')
param appServiceName string

@description('Existing Log Analytics workspace used for metadata-only diagnostics.')
param logAnalyticsWorkspaceName string

@allowed([
  'swedencentral'
])
@description('Sweden Central is in the EU data zone and supports the governed deployment below.')
param aiLocation string = 'swedencentral'

param deploymentName string = 'research-assistant-gpt41mini'
param deploymentCapacity int = 10
param virtualNetworkAddressPrefix string = '10.24.0.0/16'
param appIntegrationSubnetPrefix string = '10.24.1.0/24'
param privateEndpointSubnetPrefix string = '10.24.2.0/24'

var compactEnvironment = replace(toLower(environmentName), '-', '')
var suffix = take(uniqueString(subscription().subscriptionId, resourceGroup().id, environmentName), 6)
var aiAccountName = take('pcip-${compactEnvironment}-research-ai-${suffix}', 64)
var virtualNetworkName = 'pcip-${environmentName}-research-ai-vnet'
var privateEndpointName = 'pcip-${environmentName}-research-ai-pe'
var privateDnsZoneName = 'privatelink.openai.azure.com'

resource app 'Microsoft.Web/sites@2023-12-01' existing = {
  name: appServiceName
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: virtualNetworkName
  location: resourceGroup().location
  properties: {
    addressSpace: {
      addressPrefixes: [virtualNetworkAddressPrefix]
    }
  }
}

resource appIntegrationSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: network
  name: 'app-integration'
  properties: {
    addressPrefix: appIntegrationSubnetPrefix
    delegations: [
      {
        name: 'app-service-delegation'
        properties: {
          serviceName: 'Microsoft.Web/serverFarms'
        }
      }
    ]
  }
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: network
  name: 'private-endpoints'
  properties: {
    addressPrefix: privateEndpointSubnetPrefix
    privateEndpointNetworkPolicies: 'Disabled'
  }
}

resource appVnetIntegration 'Microsoft.Web/sites/networkConfig@2023-12-01' = {
  parent: app
  name: 'virtualNetwork'
  properties: {
    subnetResourceId: appIntegrationSubnet.id
    swiftSupported: true
  }
}

resource aiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: aiAccountName
  location: aiLocation
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: aiAccountName
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiAccount
  name: deploymentName
  sku: {
    name: 'DataZoneStandard'
    capacity: deploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1-mini'
      version: '2025-04-14'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource openAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiAccount.id, app.id, 'cognitive-services-openai-user')
  scope: aiAccount
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
    )
  }
}

resource privateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: privateDnsZoneName
  location: 'global'
}

resource privateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZone
  name: '${environmentName}-research-ai-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: network.id
    }
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: privateEndpointName
  // A private endpoint is a network interface in the VNet and must share the
  // VNet's region. The target Azure OpenAI account may be in another region.
  location: resourceGroup().location
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'research-ai-account'
        properties: {
          privateLinkServiceId: aiAccount.id
          groupIds: ['account']
        }
      }
    ]
  }
}

resource privateDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'azure-openai'
        properties: {
          privateDnsZoneId: privateDnsZone.id
        }
      }
    ]
  }
}

resource metadataDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'research-ai-metadata-only'
  scope: aiAccount
  properties: {
    workspaceId: workspace.id
    logs: [
      {
        category: 'Audit'
        enabled: true
      }
      {
        category: 'AzureOpenAIRequestUsage'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

output azureOpenAiResourceName string = aiAccount.name
output azureOpenAiEndpoint string = aiAccount.properties.endpoint
output azureOpenAiAllowedHost string = '${aiAccount.name}.openai.azure.com'
output azureOpenAiDeployment string = modelDeployment.name
output azureOpenAiAuthentication string = 'managed_identity'
output processingBoundary string = 'EU Data Zone'
output appServicePrincipalId string = app.identity.principalId
output privateEndpointId string = privateEndpoint.id
