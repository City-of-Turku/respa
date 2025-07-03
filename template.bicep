param location string = resourceGroup().location
param apiImageName string
param apiUrl string
param uiImageName string
@description('API WebApp name. Must be globally unique')
param apiWebAppName string
@description('UI WebApp name. Must be globally unique')
param uiWebAppName string
@description('Cache name. Must be globally unique')
param cacheName string
@description('Key vault name. Must be globally unique. Lowercase and numbers only')
@maxLength(24)
@minLength(3)
param keyvaultName string
param serverfarmPlanName string
@description('Storage account name. Must be globally unique. Lowercase and numbers only')
@maxLength(24)
@minLength(3)
param storageAccountName string
param apiOutboundIpName string
param natGatewayName string
param vnetName string
@description('Container registry name. Must be globally unique. Alphanumeric only')
@maxLength(50)
@minLength(5)
param containerRegistryName string
param dbServerName string
param dbName string
param workspaceName string
param appInsightsName string
param dbPostgresExtensions string = 'POSTGIS,HSTORE,PG_TRGM,POSTGIS_TIGER_GEOCODER,POSTGIS_TOPOLOGY,FUZZYSTRMATCH'
param dbAdminUsername string
param dbUsername string
param timmiUsername string
param qualitytoolUsername string
param qualitytoolSftpUsername string
@secure()
param dbAdminPassword string
@secure()
param dbPassword string

// Application specific parameters
@secure()
param tokenAuthSharedSecret string = ''
@secure()
param socialAuthTunnistamoSecret string = ''
@secure()
param oidcSecret string = ''
@secure()
param respaPaymentsTurkuApiKey string = ''
@secure()
param timmiPassword string = ''
@secure()
param qualitytoolPassword string = ''
@secure()
param qualitytoolSftpPassword string = ''

//TODO Refactor env variables to use test/prod variables
// Varaamo Prod
param uiAppSettings object = {
  API_URL: '${apiUrl}/v1'
  ADMIN_URL: '${apiUrl}/ra'
  PORT: '8080'
  MATOMO_SITE_ID: '3'
  SHOW_TEST_SITE_MESSAGE: '0'
  BLOCK_SEARCH_ENGINE_INDEXING: '0'
  APP_TIMEZONE: 'Europe/Helsinki'
  CLIENT_ID: 'varaamo-02582b03-7bae-4156-b069-f5fafa0f3f75'
  OPENID_AUDIENCE: 'https://auth.turku.fi/respa'
  OPENID_AUTHORITY: 'https://tunnistamo.turku.fi/openid'
}
// Varaamo Test
// param uiAppSettings object = {
//   API_URL: '${apiUrl}/v1'
//   ADMIN_URL: '${apiUrl}/ra'
//   PORT: '8080'
//   MATOMO_SITE_ID: '4'
//   SHOW_TEST_SITE_MESSAGE: '1'
//   BLOCK_SEARCH_ENGINE_INDEXING: '1'
//   APP_TIMEZONE: 'Europe/Helsinki'
//   CLIENT_ID: '7f80c6cd-d10c-4345-850b-c86aec3a0e98'
//   OPENID_AUDIENCE: 'https://auth.turku.fi/respa'
//   OPENID_AUTHORITY: 'https://testitunnistamo.turku.fi/openid'
// }

// Respa prod
param apiAppSettings object = {
  ALLOWED_HOSTS: '${apiWebAppName}.azurewebsites.net,127.0.0.1,respa.turku.fi,localhost,varaamo.turku.fi,varaamo-api.turku.fi'
  AUTHENTICATION_CLASSES: 'respa.providers.turku_oidc.oidc.ApiTokenAuthentication,respa.providers.turku_oidc.jwt.JWTAuthentication'
  CSRF_TRUSTED_ORIGINS: 'https://respa.turku.fi'
  DEBUG: '0'
  DEFAULT_DISABLED_FIELDS_SET_ID: 1
  DJANGO_ADMIN_CONFIG: 'respa.providers.turku_oidc.admin_site.AdminConfig'
  DJANGO_LOG_LEVEL: 'INFO'
  DJANGO_ADMIN_LOGOUT_REDIRECT_URL: '${apiUrl}/admin'
  EMAIL_HOST: 'smtp.turku.fi'
  EMAIL_PORT: '587'
  EMAIL_USE_TLS: 'True'
  MAIL_ENABLED: 1
  MAIL_DEFAULT_FROM: 'varaamo@turku.fi'
  ENABLE_SSH: 'true'
  GSM_NOTIFICATION_ADDRESS: 'gsm.turku.fi'
  HELUSERS_PROVIDER: 'respa.providers.turku_oidc'
  HELUSERS_AUTHENTICATION_BACKEND: 'respa.providers.turku_oidc.tunnistamo_oidc.TunnistamoOIDCAuth'
  HELUSERS_SOCIALACCOUNT_ADAPTER: 'respa.providers.turku_oidc.adapter.SocialAccountAdapter'
  INTERNAL_IPS: '127.0.0.1'
  LOGOUT_REDIRECT_URL: '${apiUrl}/ra'
  MACHINE_TO_MACHINE_AUTH_ENABLED: 1
  MEDIA_ROOT: '/fileshare/media'
  MEDIA_URL: '/media/'
  OIDC_AUDIENCE: 'varaamo-02582b03-7bae-4156-b069-f5fafa0f3f75'
  OIDC_SECRET: oidcSecret
  OIDC_API_SCOPE_PREFIX: 'varaamo-02582b03-7bae-4156-b069-f5fafa0f3f75'
  OIDC_REQUIRE_API_SCOPE_FOR_AUTHENTICATION: 0
  OIDC_ISSUER: 'https://tunnistamo.turku.fi/openid'
  OIDC_LEEWAY: 86400
  PRODUCTION: 1
  QUALITYTOOL_USERNAME: qualitytoolUsername
  QUALITYTOOL_PASSWORD: qualitytoolPassword
  QUALITYTOOL_API_BASE: 'https://api.laatutyokalut.suomi.fi'
  QUALITYTOOL_ENABLED: 1
  QUALITYTOOL_SFTP_HOST: 'tkusiirto1.turku.fi'
  QUALITYTOOL_SFTP_USERNAME: qualitytoolSftpUsername
  QUALITYTOOL_SFTP_PASSWORD: qualitytoolSftpPassword
  RESPA_ADMIN_SUPPORT_EMAIL: 'varaamo@turku.fi'
  RESPA_ADMIN_INSTRUCTIONS_URL: 'https://digipoint-turku.gitbook.io/varaamo-turku/yllapitoliittyma/aloitus'
  RESPA_ADMIN_LOGOUT_REDIRECT_URL: '${apiUrl}/ra'
  RESPA_ADMIN_LOGO: 'ra-logo-tku.png'
  RESPA_ADMIN_KORO_STYLE: 'koro-storm'
  RESPA_ADMIN_VIEW_RESOURCE_URL: 'https://varaamo.turku.fi/resources/'
  RESPA_ADMIN_VIEW_UNIT_URL: 'https://varaamo.turku.fi/units/'
  RESPA_PAYMENTS_ENABLED: 1
  RESPA_PAYMENTS_PROVIDER_CLASS: 'payments.providers.TurkuPaymentProviderV3'
  RESPA_PAYMENTS_TURKU_API_URL: 'https://digiaurajoki.turku.fi:9443/verkkomaksupalvelu/api/v1/payment/create'
  RESPA_PAYMENTS_TURKU_API_KEY: respaPaymentsTurkuApiKey
  RESPA_PAYMENTS_TURKU_API_APP_NAME: 'Varaamo'
  RESPA_PAYMENTS_TURKU_SAP_SALES_ORGANIZATION: '1100'
  RESPA_PAYMENTS_TURKU_SAP_DISTRIBUTION_CHANNEL: '11'
  RESPA_PAYMENTS_TURKU_SAP_SECTOR: '1A'
  // SECURE_PROXY_SSL_HEADER: 'HTTP_X_FORWARDED_PROTO,https'
  // SECURE_SSL_REDIRECT: 'False'
  SOCIAL_AUTH_TUNNISTAMO_KEY: 'https://auth.turku.fi/respa'
  SOCIAL_AUTH_TUNNISTAMO_SECRET: socialAuthTunnistamoSecret
  SMS_ENABLED: 1
  STATIC_ROOT: '/fileshare/static'
  STATIC_URL: '/static/'
  STRONG_AUTH_CLAIMS: 'turku_adfs,turku_suomifi'
  TIMMI_ADMIN_ID: 1
  TIMMI_API_URL: 'https://timmi.turku.fi/WebTimmi/rest'
  TIMMI_USERNAME: timmiUsername
  TIMMI_PASSWORD: timmiPassword
  TOKEN_AUTH_ACCEPTED_AUDIENCE: 'https://varaamo.turku.fi'
  TOKEN_AUTH_SHARED_SECRET: tokenAuthSharedSecret
  TUNNISTAMO_BASE_URL: 'https://tunnistamo.turku.fi'
  USE_DJANGO_DEFAULT_EMAIL: 1
  USE_SWAGGER_OPENAPI_VIEW: 1
  USE_RESPA_EXCHANGE: 0
  // WEBSITES_ENABLE_APP_SERVICE_STORAGE: 'false'
  // WEBSITES_PORT: '8000'
}
// // Respa Test
// param apiAppSettings object = {
//   ALLOWED_HOSTS: '${apiWebAppName}.azurewebsites.net,127.0.0.1,respa-testi.turku.fi, testirespa.turku.fi, localhost,testivaraamo.turku.fi,testivaraamo-api.turku.fi' // TODO
//   AUTHENTICATION_CLASSES: 'respa.providers.turku_oidc.oidc.ApiTokenAuthentication,respa.providers.turku_oidc.jwt.JWTAuthentication'
//   CSRF_TRUSTED_ORIGINS: 'https://testirespa.turku.fi'
//   DEBUG: '0'
//   DEFAULT_DISABLED_FIELDS_SET_ID: 2
//   DJANGO_ADMIN_CONFIG: 'respa.providers.turku_oidc.admin_site.AdminConfig'
//   DJANGO_ADMIN_LOGOUT_REDIRECT_URL: '${apiUrl}/admin'
//   EMAIL_HOST: 'smtp.turku.fi'
//   EMAIL_PORT: '587'
//   EMAIL_USE_TLS: 'True'
//   ENABLE_SSH: 'true'
//   GSM_NOTIFICATION_ADDRESS: 'gsm.turku.fi'
//   HELUSERS_PROVIDER: 'respa.providers.turku_oidc'
//   HELUSERS_AUTHENTICATION_BACKEND: 'respa.providers.turku_oidc.tunnistamo_oidc.TunnistamoOIDCAuth'
//   HELUSERS_SOCIALACCOUNT_ADAPTER: 'respa.providers.turku_oidc.adapter.SocialAccountAdapter'
//   INTERNAL_IPS: '127.0.0.1'
//   LOGOUT_REDIRECT_URL: '${apiUrl}/ra'
//   MACHINE_TO_MACHINE_AUTH_ENABLED: 1
//   MAIL_ENABLED: '1'
//   MAIL_DEFAULT_FROM: 'varaamo@turku.fi'
//   MEDIA_ROOT: '/fileshare/media'
//   MEDIA_URL: '/media/'
//   OIDC_AUDIENCE: '7f80c6cd-d10c-4345-850b-c86aec3a0e98'
//   OIDC_SECRET: oidcSecret
//   OIDC_API_SCOPE_PREFIX: '7f80c6cd-d10c-4345-850b-c86aec3a0e98'
//   OIDC_REQUIRE_API_SCOPE_FOR_AUTHENTICATION: 0
//   OIDC_ISSUER: 'https://testitunnistamo.turku.fi/openid'
//   OIDC_LEEWAY: 86400
//   PRODUCTION: 0
//   QUALITYTOOL_USERNAME: qualitytoolUsername
//   QUALITYTOOL_PASSWORD: qualitytoolPassword
//   QUALITYTOOL_API_BASE: 'https://api.laatutyokalut.dev.suomi.fi'
//   QUALITYTOOL_ENABLED: 1
//   QUALITYTOOL_SFTP_HOST: 'tkusiirto1.turku.fi'
//   QUALITYTOOL_SFTP_USERNAME: qualitytoolSftpUsername
//   QUALITYTOOL_SFTP_PASSWORD: qualitytoolSftpPassword
//   RESPA_ADMIN_SUPPORT_EMAIL: 'varaamo@turku.fi'
//   RESPA_ADMIN_INSTRUCTIONS_URL: 'https://digipoint-turku.gitbook.io/varaamo-turku/yllapitoliittyma/aloitus'
//   RESPA_ADMIN_LOGOUT_REDIRECT_URL: 'https://testivaraamo-api.turku.fi/ra'
//   RESPA_ADMIN_LOGO: 'ra-logo.png'
//   RESPA_ADMIN_KORO_STYLE: 'koro-storm'
//   RESPA_ADMIN_VIEW_RESOURCE_URL: 'https://testivaraamo.turku.fi/resources/'
//   RESPA_ADMIN_VIEW_UNIT_URL: 'https://testivaraamo.turku.fi/units/'
//   RESPA_PAYMENTS_ENABLED: 1
//   RESPA_PAYMENTS_PROVIDER_CLASS: 'payments.providers.TurkuPaymentProviderV3'
//   RESPA_PAYMENTS_TURKU_API_URL: 'https://qadigiaurajoki.turku.fi:9443/verkkomaksupalvelu/api/v1/payment/create'
//   RESPA_PAYMENTS_TURKU_API_KEY: respaPaymentsTurkuApiKey
//   RESPA_PAYMENTS_TURKU_API_APP_NAME: 'Testivaraamo'
//   RESPA_PAYMENTS_TURKU_SAP_SALES_ORGANIZATION: '1100'
//   RESPA_PAYMENTS_TURKU_SAP_DISTRIBUTION_CHANNEL: '11'
//   RESPA_PAYMENTS_TURKU_SAP_SECTOR: '1A'
//   SOCIAL_AUTH_TUNNISTAMO_KEY: 'https://auth.turku.fi/respa'
//   SOCIAL_AUTH_TUNNISTAMO_SECRET: socialAuthTunnistamoSecret
//   STATIC_ROOT: '/fileshare/static'
//   STATIC_URL: '/static/'
//   STRONG_AUTH_CLAIMS: 'turku_adfs,turku_suomifi'
//   TIMMI_ADMIN_ID: 1
//   TIMMI_API_URL: 'https://timmi.turku.fi/WebTimmi/rest'
//   TIMMI_USERNAME: timmiUsername
//   TIMMI_PASSWORD: timmiPassword
//   TOKEN_AUTH_ACCEPTED_AUDIENCE: 'https://testivaraamo.turku.fi'
//   TOKEN_AUTH_SHARED_SECRET: tokenAuthSharedSecret
//   TUNNISTAMO_BASE_URL: 'https://testitunnistamo.turku.fi' 
//   USE_DJANGO_DEFAULT_EMAIL: 1
//   USE_SWAGGER_OPENAPI_VIEW: 1
//   USE_RESPA_EXCHANGE: 0
// }

@allowed([
  0
  1
  2
  3
  4
  5
])
param cacheCapacity int = 1

var webAppRequirements = [
  {
    name: apiWebAppName
    image: apiImageName
    allowKeyvaultSecrets: true
    applicationGatewayAccessOnly: true
    appSettings: {
      DATABASE_URL: '@Microsoft.KeyVault(VaultName=${keyvault.name};SecretName=${keyvault::dbUrlSecret.name})'
      CACHE_LOCATION: '@Microsoft.KeyVault(VaultName=${keyvault.name};SecretName=${keyvault::cacheLocationSecret.name})'
      CELERY_BROKER_URL: '@Microsoft.KeyVault(VaultName=${keyvault.name};SecretName=${keyvault::celeryBrokerUrlSecret.name})'
      ...apiAppSettings
    }
    fileshares: {
      'api-files': '/fileshare'
    }
  }
  {
    name: uiWebAppName
    image: uiImageName
    allowKeyvaultSecrets: false
    applicationGatewayAccessOnly: true
    appSettings: uiAppSettings
    fileshares: {}
  }
]

var fileshareNames = union(flatten(map(webAppRequirements, x => objectKeys(x.fileshares))), []) // union removes duplicate keys

var dnsZoneRequirements = [
  'privatelink.azurecr.io'
  'privatelink.file.core.windows.net'
  'privatelink.postgres.database.azure.com'
  'privatelink.redis.cache.windows.net'
  'privatelink.vaultcore.azure.net'
]

var subnetRequirements = [
  {
    name: 'default'
    delegations: []
    serviceEndpoints: []
    enableNatGateway: false
  }
  {
    name: 'azureservices'
    delegations: []
    serviceEndpoints: []
    enableNatGateway: false
  }
  {
    name: 'api'
    delegations: ['Microsoft.Web/serverfarms'] // Required
    serviceEndpoints: []
    enableNatGateway: true
  }
]

var privateEndpointRequirements = [
  {
    name: '${cacheName}-endpoint'
    privateLinkServiceId: cache.id
    groupId: 'redisCache'
    privateDnsZoneName: 'privatelink.redis.cache.windows.net'
    privateDnsZoneId: dnsZone[3].id
  }
  {
    name: '${containerRegistryName}-endpoint'
    privateLinkServiceId: containerRegistry.id
    groupId: 'registry'
    privateDnsZoneName: 'privatelink.azurecr.io'
    privateDnsZoneId: dnsZone[0].id
  }
  {
    name: '${storageAccountName}-endpoint'
    privateLinkServiceId: storageAccount.id
    groupId: 'file'
    privateDnsZoneName: 'privatelink.file.core.windows.net'
    privateDnsZoneId: dnsZone[1].id
  }
  {
    name: '${keyvaultName}-endpoint'
    privatelinkServiceId: keyvault.id
    groupId: 'vault'
    privateDnsZoneName: 'privatelink.vaultcore.azure.net'
    privateDnsZoneId: dnsZone[4].id
  }
  {
    name: '${dbServerName}-endpoint'
    privateLinkServiceId: db.id
    groupId: 'postgresqlServer'
    privateDnsZoneName: 'privatelink.postgres.database.azure.com'
    privateDnsZoneId: dnsZone[2].id
  }
]

var goforeIps = {
  goforeKamppi: '81.175.255.179' // Gofore Kamppi egress
  goforeTampere: '82.141.89.43' // Gofore Tampere egress
  goforeVpn: '80.248.248.85' // Gofore VPN egress
}
var goforeCidrs = {
  goforeKamppi: '${goforeIps.goforeKamppi}/24'
  goforeTampere: '${goforeIps.goforeTampere}/24'
  goforeVpn: '${goforeIps.goforeVpn}/24'
}
var goforeAndAzureContainerRegistryIps = union(goforeIps, {
  // Needed to build an image in the container registry, networkRuleBypassOptions: AzureServices is not enough for some reason. These IPs can probably change. Sourced from https://www.microsoft.com/en-us/download/details.aspx?id=56519
  azureRange1: '51.12.32.0/25'
  azureRange2: '51.12.32.128/26'
})
var goforeStorageNetworkAcls = {
  defaultAction: 'Deny'
  ipRules: map(items(goforeIps), ip => {
    action: 'Allow'
    value: ip.value
  })
}
var goforeContainerRegistryNetworkRuleSet = {
  defaultAction: 'Deny'
  ipRules: map(items(goforeAndAzureContainerRegistryIps), ip => {
    action: 'Allow'
    value: ip.value
  })
}
var goforeNetworkAcls = {
  bypass: 'AzureServices'
  defaultAction: 'Deny'
  ipRules: map(items(goforeIps), ip => {
    value: ip.value
  })
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

resource apiOutboundIp 'Microsoft.Network/publicIPAddresses@2024-01-01' existing = {
  name: apiOutboundIpName
  scope: resourceGroup('turku-common')
}

resource natGateway 'Microsoft.Network/natGateways@2024-01-01' = {
  name: natGatewayName
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 4
    publicIpAddresses: [
      {
        id: apiOutboundIp.id
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: ['10.0.0.0/16']
    }
    encryption: {
      enabled: false
      enforcement: 'AllowUnencrypted'
    }
    enableDdosProtection: false
  }

  @batchSize(1)
  resource subnets 'subnets@2023-11-01' = [
    for i in range(0, length(subnetRequirements)): {
      name: subnetRequirements[i].name
      properties: {
        addressPrefixes: ['10.0.${i}.0/24']
        natGateway: subnetRequirements[i].enableNatGateway ? { id: natGateway.id } : null
        serviceEndpoints: [
          for serviceEndpoint in subnetRequirements[i].serviceEndpoints: {
            service: serviceEndpoint
            locations: [location]
          }
        ]
        delegations: [
          for delegation in subnetRequirements[i].delegations: {
            name: 'delegation'
            properties: {
              serviceName: delegation
            }
            type: 'Microsoft.Network/virtualNetworks/subnets/delegations'
          }
        ]
        privateEndpointNetworkPolicies: 'Disabled'
        privateLinkServiceNetworkPolicies: 'Enabled'
      }
    }
  ]
}

resource dnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = [
  for dnsZoneRequirement in dnsZoneRequirements: {
    name: dnsZoneRequirement
    location: 'global'
  }
]

resource privateDnsZoneVnetLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [
  for i in range(0, length(dnsZoneRequirements)): {
    parent: dnsZone[i]
    location: 'global'
    name: 'vnetlink'
    properties: {
      registrationEnabled: false
      virtualNetwork: {
        id: vnet.id
      }
    }
  }
]

resource cache 'Microsoft.Cache/Redis@2024-04-01-preview' = {
  name: cacheName
  location: location
  properties: {
    redisVersion: '6.0'
    sku: {
      name: 'Basic'
      family: 'C'
      capacity: cacheCapacity
    }
    enableNonSslPort: false
    publicNetworkAccess: 'Disabled'
    redisConfiguration: {
      'aad-enabled': 'true'
      'maxmemory-reserved': '30'
      'maxfragmentationmemory-reserved': '30'
      'maxmemory-delta': '30'
    }
    updateChannel: 'Stable'
    disableAccessKeyAuthentication: false
  }
  dependsOn: [
    dnsZone[3]
    vnet::subnets[1]
  ]
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: containerRegistryName
  location: location
  sku: {
    name: 'Premium'
  }
  properties: {
    adminUserEnabled: true // Required to create RBAC rights
    publicNetworkAccess: 'Enabled'
    networkRuleBypassOptions: 'AzureServices'
    networkRuleSet: goforeContainerRegistryNetworkRuleSet
  }
  dependsOn: [
    dnsZone[0]
    vnet::subnets[1]
  ]

  resource webhooks 'webhooks@2023-01-01-preview' = [
    for webAppRequirement in webAppRequirements: {
      name: '${replace(webAppRequirement.name, '-', '')}webhook'
      location: location
      properties: {
        actions: ['push']
        scope: '${webAppRequirement.image}:latest'
        serviceUri: '${list(resourceId('Microsoft.Web/sites/config', webAppRequirement.name, 'publishingcredentials'), '2015-08-01').properties.scmUri}/docker/hook'
        status: 'enabled'
      }
    }
  ]
}

var dbProperties = {
  storage: {
    iops: 120
    tier: 'P4'
    storageSizeGB: 32
    autoGrow: 'Disabled'
  }
  network: {
    publicNetworkAccess: 'Enabled'
  }
  dataEncryption: {
    type: 'SystemManaged'
  }
  authConfig: {
    activeDirectoryAuth: 'Disabled'
    passwordAuth: 'Enabled'
  }
  version: '16'
  administratorLogin: dbAdminUsername
  administratorLoginPassword: dbAdminPassword
  availabilityZone: '2'
}

var dbSku = {
  // Must be above Burstable for replication
  name: 'Standard_D2ds_v5'
  tier: 'GeneralPurpose'
}

resource db 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: dbServerName
  location: location
  sku: dbSku
  properties: {
    replicationRole: 'Primary'
    createMode: 'Default'
    ...dbProperties
  }
  dependsOn: [
    dnsZone[2]
    vnet::subnets[1]
  ]

  resource dbFirewallRules 'firewallRules' = [
    for ip in items(goforeIps): {
      name: ip.key
      properties: {
        startIpAddress: ip.value
        endIpAddress: ip.value
      }
    }
  ]
}

resource dbConfigurationClientEncoding 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  name: 'client_encoding'
  parent: db
  properties: {
    value: 'UTF8'
    source: 'user-override'
  }
  dependsOn: [waitForDbReady]
}

resource dbConfigurationAzureExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  name: 'azure.extensions'
  parent: db
  properties: {
    value: dbPostgresExtensions
    source: 'user-override'
  }
  dependsOn: [waitForDbReady]
}

resource dbDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  name: dbName
  parent: db
  properties: {
    charset: 'UTF8'
    collation: 'fi_FI.utf8'
  }
}

resource waitForDbReady 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  kind: 'AzurePowerShell'
  name: 'waitForDbReady'
  location: location
  properties: {
    azPowerShellVersion: '3.0'
    scriptContent: 'start-sleep -Seconds 60'
    cleanupPreference: 'Always'
    retentionInterval: 'PT1H'
  }
  dependsOn: [db]
}

resource waitForDbReadyAndConfigured 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  kind: 'AzurePowerShell'
  name: 'waitForDbReadyAndConfigured'
  location: location
  properties: {
    azPowerShellVersion: '3.0'
    scriptContent: 'start-sleep -Seconds 60'
    cleanupPreference: 'Always'
    retentionInterval: 'PT1H'
  }
  dependsOn: [
    dbConfigurationClientEncoding
    dbConfigurationAzureExtensions
  ]
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    dnsEndpointType: 'Standard'
    publicNetworkAccess: 'Enabled'
    networkAcls: goforeStorageNetworkAcls
    allowSharedKeyAccess: true // Required for uploading files with Azure CLI
    largeFileSharesState: 'Enabled'
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot' // Required since swedencentral doesn't support others at the time of writing, even if we don't use blob storage
  }

  resource fileServices 'fileServices@2024-01-01' = {
    name: 'default'

    resource fileshares 'shares@2024-01-01' = [
      for fileshareName in fileshareNames: {
        name: fileshareName
      }
    ]
  }
}

resource serverfarmPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: serverfarmPlanName
  location: location
  sku: {
    name: 'P0v3'
    tier: 'Premium0V3'
    size: 'P0v3'
    family: 'Pv3'
    capacity: 1
  }
  kind: 'linux'
  properties: {
    perSiteScaling: false
    elasticScaleEnabled: false
    maximumElasticWorkerCount: 1
    isSpot: false
    reserved: true
    isXenon: false
    hyperV: false
    targetWorkerCount: 0
    targetWorkerSizeId: 0
    zoneRedundant: false
  }
}

resource privateEndpoints 'Microsoft.Network/privateEndpoints@2023-11-01' = [
  for privateEndpointRequirement in privateEndpointRequirements: {
    name: privateEndpointRequirement.name
    location: location
    properties: {
      customNetworkInterfaceName: '${privateEndpointRequirement.name}-nic'
      subnet: {
        id: vnet::subnets[1].id
      }
      privateLinkServiceConnections: [
        {
          name: privateEndpointRequirement.name
          properties: {
            privateLinkServiceId: privateEndpointRequirement.privateLinkServiceId
            groupIds: [privateEndpointRequirement.groupId]
          }
        }
      ]
    }
  }
]

resource privateDnsZoneGroups 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = [
  for i in range(0, length(privateEndpointRequirements)): {
    parent: privateEndpoints[i]
    name: 'default'
    properties: {
      privateDnsZoneConfigs: [
        {
          name: privateEndpointRequirements[i].privateDnsZoneName
          properties: {
            privateDnsZoneId: privateEndpointRequirements[i].privateDnsZoneId
          }
        }
      ]
    }
  }
]

resource applicationGatewayVnet 'Microsoft.Network/virtualNetworks@2020-11-01' existing = {
  name: 'turku-common-vnet'
  scope: resourceGroup('turku-common')
}

resource applicationGatewaySubnet 'Microsoft.Network/virtualNetworks/subnets@2022-01-01' existing = {
  name: 'AgwSubnet'
  parent: applicationGatewayVnet
}

var ipSecurityRestrictionsForGoforeIpsOnly = [
  {
    action: 'Allow'
    tag: 'Default'
    priority: 100
    name: 'AllowGoforeKamppiInbound'
    description: 'Allow HTTP/HTTPS from Application Gateway subnet'
    ipAddress: goforeCidrs.goforeKamppi
  }
  {
    action: 'Allow'
    tag: 'Default'
    priority: 101
    name: 'AllowGoforeTampereInbound'
    description: 'Allow HTTP/HTTPS from Application Gateway subnet'
    ipAddress: goforeCidrs.goforeTampere
  }
  {
    action: 'Allow'
    tag: 'Default'
    priority: 102
    name: 'AllowGoforeVpnInbound'
    description: 'Allow HTTP/HTTPS from Application Gateway subnet'
    ipAddress: goforeCidrs.goforeVpn
  }
  {
    ipAddress: 'Any'
    action: 'Deny'
    priority: 2147483647
    name: 'Deny all'
    description: 'Deny all access'
  }
]

var ipSecurityRestrictionsForApplicationGatewayAccessOnly = [
  {
    vnetSubnetResourceId: applicationGatewaySubnet.id
    action: 'Allow'
    tag: 'Default'
    priority: 100
    name: 'AllowAppGWInbound'
    description: 'Allow HTTP/HTTPS from Application Gateway subnet'
  }
  {
    ipAddress: 'Any'
    action: 'Deny'
    priority: 2147483647
    name: 'Deny all'
    description: 'Deny all access'
  }
]

resource webApps 'Microsoft.Web/sites@2023-12-01' = [
  for webAppRequirement in webAppRequirements: {
    name: webAppRequirement.name
    location: location
    kind: 'app,linux,container'
    identity: {
      type: 'SystemAssigned'
    }
    properties: {
      serverFarmId: serverfarmPlan.id
      reserved: true
      hyperV: false
      vnetRouteAllEnabled: true
      vnetImagePullEnabled: true
      vnetContentShareEnabled: false
      clientAffinityEnabled: false
      httpsOnly: true
      redundancyMode: 'None'
      publicNetworkAccess: 'Enabled'
      virtualNetworkSubnetId: vnet::subnets[2].id
      keyVaultReferenceIdentity: 'SystemAssigned'
      siteConfig: {
        numberOfWorkers: 1
        linuxFxVersion: 'DOCKER|${containerRegistryName}.azurecr.io/${webAppRequirement.image}:latest'
        acrUseManagedIdentityCreds: true
        alwaysOn: true
        http20Enabled: false
        functionAppScaleLimit: 0
        minimumElasticInstanceCount: 1
        ipSecurityRestrictionsDefaultAction: webAppRequirement.applicationGatewayAccessOnly ? 'Deny' : 'Allow'
        ipSecurityRestrictions: webAppRequirement.applicationGatewayAccessOnly
          ? ipSecurityRestrictionsForApplicationGatewayAccessOnly
          : []
        scmIpSecurityRestrictionsDefaultAction: 'Deny'
        scmIpSecurityRestrictionsUseMain: false
        scmIpSecurityRestrictions: ipSecurityRestrictionsForGoforeIpsOnly
        azureStorageAccounts: reduce(
          items(webAppRequirement.fileshares),
          {},
          (build, fileshare) =>
            union(build, {
              '${fileshare.key}-mount': {
                type: 'AzureFiles'
                accountName: storageAccountName
                shareName: fileshare.key
                mountPath: fileshare.value
                protocol: 'Smb'
                accessKey: listKeys(
                  resourceId('Microsoft.Storage/storageAccounts', storageAccountName),
                  providers('Microsoft.Storage', 'storageAccounts').apiVersions[0]
                ).keys[0].value
              }
            })
        )
        appSettings: map(
          items({
            DOCKER_ENABLE_CI: 'true'
            APPLICATIONINSIGHTS_CONNECTION_STRING: appInsights.properties.ConnectionString
            ApplicationInsightsAgent_EXTENSION_VERSION: '~3'
            XDT_MicrosoftApplicationInsights_Mode: 'Recommended'
            ...webAppRequirement.appSettings
          }),
          x => {
            name: x.key
            value: x.value
          }
        )
      }
    }
  }
]

resource keyvault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyvaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enabledForDeployment: true
    enabledForDiskEncryption: true
    enabledForTemplateDeployment: true
    enableRbacAuthorization: true
    enablePurgeProtection: true
    enableSoftDelete: true
    publicNetworkAccess: 'Enabled'
    networkAcls: goforeNetworkAcls
  }

  resource dbUrlSecret 'secrets' = {
    name: 'dbUrl'
    properties: {
      value: 'postgis://${dbUsername}:${dbPassword}@${dbServerName}.postgres.database.azure.com/${dbName}'
    }
  }

  resource cacheLocationSecret 'secrets' = {
    name: 'cacheLocation'
    properties: {
      value: 'rediss://:${cache.listKeys().primaryKey}@${cacheName}.redis.cache.windows.net:6380/0'
    }
  }

  resource celeryBrokerUrlSecret 'secrets' = {
    name: 'celeryBrokerUrl'
    properties: {
      value: 'rediss://:${cache.listKeys().primaryKey}@${cacheName}.redis.cache.windows.net:6380/1'
    }
  }
}

@description('Key Vault Secret User role')
resource keyVaultSecretUserRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: resourceGroup()
  name: '4633458b-17de-408a-b874-0445c86b69e6'
}

@description('Container Registry AcrPull role')
resource acrPullRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: resourceGroup()
  name: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
}

@description('Grant the app service identity with key vault secret user role permissions over the key vault. This allows reading secret contents')
resource webAppKeyvaultSecretUserRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for i in range(0, length(webAppRequirements)): if (webAppRequirements[i].allowKeyvaultSecrets) {
    scope: keyvault
    name: guid(resourceGroup().id, webApps[i].id, keyVaultSecretUserRoleDefinition.id)
    properties: {
      roleDefinitionId: keyVaultSecretUserRoleDefinition.id
      principalId: webApps[i].identity.principalId
      principalType: 'ServicePrincipal'
    }
  }
]

@description('Grant the app service identity with ACR pull role permissions over the container registry. This allows pulling container images')
resource webAppAcrPullRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for i in range(0, length(webAppRequirements)): {
    scope: containerRegistry
    name: guid(resourceGroup().id, webApps[i].id, acrPullRoleDefinition.id)
    properties: {
      roleDefinitionId: acrPullRoleDefinition.id
      principalId: webApps[i].identity.principalId
      principalType: 'ServicePrincipal'
    }
  }
]
