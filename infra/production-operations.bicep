// Isolated production-operation runner. This is separate from main.bicep so
// provisioning never requires application secret values. GitHub can enqueue a
// fixed request but cannot start, alter, or inspect a secret-bearing execution.
targetScope = 'resourceGroup'

@description('Azure region for the existing production resources.')
param location string = resourceGroup().location

@description('Existing production ACR name.')
param productionRegistryName string

@description('Existing production App Service name, read only by the workflow identity.')
param productionAppName string

@description('Existing production Key Vault name.')
param keyVaultName string

@description('Existing Key Vault secret name containing the application database URL.')
param databaseUrlSecretName string = 'database-url'

@description('Dedicated Container Apps managed-environment name.')
param operationsEnvironmentName string = 'pcip-production-operations'

@description('Dedicated event-driven job name.')
param operationsJobName string = 'pcip-production-operations'

@description('Dedicated Service Bus namespace name.')
param operationsServiceBusName string = 'pcip-production-operations'

@description('Dedicated Service Bus queue name.')
param operationsQueueName string = 'approved-operations'

@description('Immutable approved operations-worker image; independent of the App Service rollback image.')
@minLength(71)
param imageDigest string

@description('Full source revision used to build and approve the immutable operations-worker image.')
@minLength(40)
@maxLength(40)
param workerProvenanceRevision string

@description('Object ID of the dedicated GitHub OIDC service principal for approved operations.')
param operationsWorkflowPrincipalId string

var operationsLogName = '${operationsEnvironmentName}-log'
var operationsWorkerIdentityName = '${operationsJobName}-identity'
var imageReference = '${productionRegistry.properties.loginServer}/pcip@${imageDigest}'
var serviceBusNamespaceFqdn = '${operationsServiceBus.name}.servicebus.windows.net'

resource operationsLog 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: operationsLogName
  location: location
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource productionRegistry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: productionRegistryName
}

resource productionApp 'Microsoft.Web/sites@2023-12-01' existing = {
  name: productionAppName
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource databaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: keyVault
  name: databaseUrlSecretName
}

// This identity and its narrowly scoped access are provisioned before the job.
// A system-assigned job identity cannot receive ACR access until after its first
// revision succeeds, which creates an image-pull bootstrap cycle.
resource operationsWorkerIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: operationsWorkerIdentityName
  location: location
}

resource operationsServiceBus 'Microsoft.ServiceBus/namespaces@2024-01-01' = {
  name: operationsServiceBusName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {
    disableLocalAuth: true
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource operationsQueue 'Microsoft.ServiceBus/namespaces/queues@2024-01-01' = {
  parent: operationsServiceBus
  name: operationsQueueName
  properties: {
    lockDuration: 'PT1M'
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'PT5M'
    deadLetteringOnMessageExpiration: true
  }
}

resource operationsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: operationsEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: operationsLog.properties.customerId
        sharedKey: operationsLog.listKeys().primarySharedKey
      }
    }
  }
}

resource operationsJob 'Microsoft.App/jobs@2025-01-01' = {
  name: operationsJobName
  location: location
  dependsOn: [
    operationsAcrPull
    operationsDatabaseSecretReader
    operationsQueueReceiver
  ]
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${operationsWorkerIdentity.id}': {}
    }
  }
  properties: {
    environmentId: operationsEnvironment.id
    configuration: {
      triggerType: 'Event'
      replicaTimeout: 300
      replicaRetryLimit: 0
      eventTriggerConfig: {
        scale: {
          minExecutions: 0
          maxExecutions: 1
          pollingInterval: 15
          rules: [
            {
              name: 'approved-operation-request'
              type: 'azure-servicebus'
              identity: operationsWorkerIdentity.id
              metadata: {
                queueName: operationsQueue.name
                // The KEDA Azure Service Bus scaler accepts the namespace
                // resource name, while the worker SDK uses the full hostname.
                namespace: operationsServiceBus.name
                messageCount: '1'
              }
            }
          ]
        }
      }
      registries: [
        {
          server: productionRegistry.properties.loginServer
          identity: operationsWorkerIdentity.id
        }
      ]
      secrets: [
        {
          name: 'database-url'
          keyVaultUrl: databaseUrlSecret.properties.secretUriWithVersion
          identity: operationsWorkerIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'production-operation'
          image: imageReference
          command: [
            'python'
            '-m'
            'scripts.production_operation_worker'
          ]
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'ENVIRONMENT'
              value: 'production'
            }
            {
              name: 'RUN_MIGRATIONS'
              value: 'false'
            }
            {
              name: 'RUN_RIVERMERE_PRODUCTION_DEMO_SEED'
              value: 'false'
            }
            {
              name: 'PCIP_OPERATIONS_SERVICEBUS_NAMESPACE'
              value: serviceBusNamespaceFqdn
            }
            {
              name: 'PCIP_OPERATIONS_QUEUE'
              value: operationsQueue.name
            }
            {
              // DefaultAzureCredential otherwise attempts a nonexistent
              // system-assigned identity instead of this job's UAMI.
              name: 'AZURE_CLIENT_ID'
              value: operationsWorkerIdentity.properties.clientId
            }
            {
              name: 'PCIP_OPERATIONS_WORKER_PROVENANCE'
              value: workerProvenanceRevision
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
    }
  }
}

// The runner receives only the database URL secret, scoped to this one secret.
resource operationsDatabaseSecretReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(databaseUrlSecret.id, operationsWorkerIdentity.id, 'operations-database-url-reader')
  scope: databaseUrlSecret
  properties: {
    principalId: operationsWorkerIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

resource operationsAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(productionRegistry.id, operationsWorkerIdentity.id, 'operations-acr-pull')
  scope: productionRegistry
  properties: {
    principalId: operationsWorkerIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource operationsQueueReceiver 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(operationsQueue.id, operationsWorkerIdentity.id, 'operations-queue-receiver')
  scope: operationsQueue
  properties: {
    principalId: operationsWorkerIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0')
  }
}

// GitHub can request an operation, but cannot start, modify, or read the
// secret-bearing job. Reader assignments are scoped to exact check resources.
resource operationsWorkflowQueueSender 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(operationsQueue.id, operationsWorkflowPrincipalId, 'operations-queue-sender')
  scope: operationsQueue
  properties: {
    principalId: operationsWorkflowPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39')
  }
}

resource operationsWorkflowJobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(operationsJob.id, operationsWorkflowPrincipalId, 'operations-job-reader')
  scope: operationsJob
  properties: {
    principalId: operationsWorkflowPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  }
}

resource operationsWorkflowAppReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(productionApp.id, operationsWorkflowPrincipalId, 'operations-app-reader')
  scope: productionApp
  properties: {
    principalId: operationsWorkflowPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  }
}

resource operationsWorkflowAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(productionRegistry.id, operationsWorkflowPrincipalId, 'operations-workflow-acr-pull')
  scope: productionRegistry
  properties: {
    principalId: operationsWorkflowPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource operationsWorkflowLogReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(operationsLog.id, operationsWorkflowPrincipalId, 'operations-log-reader')
  scope: operationsLog
  properties: {
    principalId: operationsWorkflowPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '73c42c96-874c-492b-b04d-ab87d138a893')
  }
}

output operationsJobResourceId string = operationsJob.id
output operationsWorkerIdentityResourceId string = operationsWorkerIdentity.id
output operationsLogWorkspaceId string = operationsLog.properties.customerId
output operationsServiceBusNamespace string = serviceBusNamespaceFqdn
output operationsQueueName string = operationsQueue.name
output operationsWorkerDigest string = imageDigest
output operationsWorkerProvenanceRevision string = workerProvenanceRevision
