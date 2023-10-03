import requests

from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter, OAuth2LoginView, OAuth2CallbackView
)
from respa.providers.turku_oidc.provider import TurkuOIDCProvider
from django.conf import settings

if settings.USE_KEYCLOAK:
    ACCESS_TOKEN_URL = '%s/protocol/openid-connect/token' % getattr(settings, 'OIDC_API_TOKEN_AUTH')['ISSUER']
    AUTHORIZE_URL =  '%s/protocol/openid-connect/auth' % getattr(settings, 'OIDC_API_TOKEN_AUTH')['ISSUER']
    PROFILE_URL = '%s/protocol/openid-connect/userinfo' % getattr(settings, 'OIDC_API_TOKEN_AUTH')['ISSUER']
else:
    ACCESS_TOKEN_URL = '%s/openid/token/' % getattr(settings, 'OIDC_API_TOKEN_AUTH')['ISSUER']
    AUTHORIZE_URL = '%s/openid/authorize/' % getattr(settings, 'OIDC_API_TOKEN_AUTH')['ISSUER']
    PROFILE_URL = '%s/openid/userinfo/' % getattr(settings, 'OIDC_API_TOKEN_AUTH')['ISSUER']


class OIDCOAuth2Adapter(OAuth2Adapter):
    provider_id = TurkuOIDCProvider.id
    access_token_url = ACCESS_TOKEN_URL
    authorize_url = AUTHORIZE_URL
    profile_url = PROFILE_URL

    def complete_login(self, request, app, token, **kwargs):
        headers = {'Authorization': 'Bearer {0}'.format(token.token)}
        resp = requests.get(self.profile_url, headers=headers)
        assert resp.status_code == 200
        extra_data = resp.json()
        return self.get_provider().sociallogin_from_response(request,
                                                             extra_data)


oauth2_login = OAuth2LoginView.adapter_view(OIDCOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(OIDCOAuth2Adapter)