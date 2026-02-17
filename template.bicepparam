using 'template.bicep'

var prefix = readEnvironmentVariable('RESOURCE_PREFIX')
var sanitizedPrefix = replace(prefix, '-', '')
// Change between 'test' and 'prod' based on deployed environment
param environment = 'test'

param apiImageName = 'api'
param uiImageName = 'ui'
param apiUrl = environment == 'prod' ? 'https://respa.turku.fi' : 'https://testirespa.turku.fi'
param uiUrl = environment == 'prod' ? 'https://varaamo.turku.fi' : 'https://testivaraamo.turku.fi'
param apiWebAppName = '${prefix}-api'
param uiWebAppName = '${prefix}-ui'

param appInsightsName = '${prefix}-appinsights'
param cacheName = '${prefix}-cache'
param containerRegistryName = '${sanitizedPrefix}registry'
param dbName = environment == 'prod' ? 'respa_prod' : 'respa_development_jenkins'
param dbServerName = '${prefix}-db'
param dbAdminUsername = 'turkuadmin'
param dbUsername = 'respa'
param keyvaultName = '${sanitizedPrefix}-kv'
param serverfarmPlanName = 'serviceplan'
param storageAccountName = '${sanitizedPrefix}store'
param apiOutboundIpName = environment == 'prod' ? 'turku-prod-respa-outbound-ip' : 'turku-test-respa-outbound-ip'
param natGatewayName = '${prefix}-nat'
param vnetName =  '${prefix}-vnet'
param workspaceName = '${prefix}-workspace'
param timmiUsername = 'roLFYzfZC/YcKVG1fq49SvgjvNwi6EVM9EPjY6/rxYU='
param qualitytoolUsername = 'fbf1b51b-5378-459f-8b44-e502d222e13f:turku-testivaraamo-qat-api'
param qualitytoolSftpUsername = 'sftp-varaamo'
param openidAuthority = environment == 'prod' ? 'https://tunnistamo.turku.fi/openid' : 'https://testitunnistamo.turku.fi/openid'
param tunnistamoBaseUrl = environment == 'prod' ? 'https://tunnistamo.turku.fi' : 'https://testitunnistamo.turku.fi'
param qualitytoolApiBase = environment == 'prod' ? 'https://api.laatutyokalut.suomi.fi' : 'https://api.laatutyokalut.dev.suomi.fi'
param showTestSiteMessage = environment == 'prod' ? '0' : '1'
param blockSearchEngineIndexing = environment == 'prod' ? '0' : '1'
param productionFlag = environment == 'prod' ? 1 : 0
param useSwaggerOpenApiView = environment == 'prod' ? 0 : 1
param allowedHosts = environment == 'prod'
    ? '${apiWebAppName}.azurewebsites.net,127.0.0.1,respa.turku.fi,localhost,varaamo.turku.fi,varaamo-api.turku.fi'
    : '${apiWebAppName}.azurewebsites.net,127.0.0.1,testirespa.turku.fi,localhost,testivaraamo.turku.fi,testivaraamo-api.turku.fi'
param clientId = environment == 'prod' ? 'varaamo-02582b03-7bae-4156-b069-f5fafa0f3f75' : '7f80c6cd-d10c-4345-850b-c86aec3a0e98'
param matomoSiteId = environment == 'prod' ? '3' : '4';
param defaultDisabledFieldsSetId = environment == 'prod' ? 1 : 2
param respaPaymentsApiUrl = environment == 'prod' ? 'https://digiaurajoki.turku.fi:9443/verkkomaksupalvelu/api/v1/payment/create' : 'https://qadigiaurajoki.turku.fi:9443/verkkomaksupalvelu/api/v1/payment/create'
