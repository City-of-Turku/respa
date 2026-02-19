import requests
from django.conf import settings

from allauth.socialaccount import providers
from allauth.socialaccount.providers.oauth2.views import OAuth2Adapter
from helusers.providers.helsinki_oidc.provider import HelsinkiOIDCAccount, HelsinkiOIDCProvider


class TurkuOIDCAccount(HelsinkiOIDCAccount):
    pass


class TurkuOIDCProvider(HelsinkiOIDCProvider):
    id = 'turku_oidc'
    name = 'City of Turku employees (OIDC)'
    package = 'respa.providers.turku_oidc'
    account_class = TurkuOIDCAccount


def _get_issuer():
    return getattr(settings, 'OIDC_API_TOKEN_AUTH', {}).get('ISSUER', '')


class _OAuth2URLDescriptor:
    """Descriptor so URL works when accessed on class (e.g. adapter.profile_url in respa_admin)."""
    def __init__(self, path):
        self.path = path

    def __get__(self, obj, objtype=None):
        return _get_issuer() + self.path


class OIDCOAuth2Adapter(OAuth2Adapter):
    provider_id = TurkuOIDCProvider.id
    access_token_url = _OAuth2URLDescriptor('/token/')
    authorize_url = _OAuth2URLDescriptor('/authorize/')
    profile_url = _OAuth2URLDescriptor('/userinfo/')

    def complete_login(self, request, app, token, **kwargs):
        headers = {'Authorization': 'Bearer {0}'.format(token.token)}
        resp = requests.get(self.profile_url, headers=headers)
        assert resp.status_code == 200
        extra_data = resp.json()
        return self.get_provider().sociallogin_from_response(request, extra_data)


TurkuOIDCProvider.oauth2_adapter_class = OIDCOAuth2Adapter
providers.registry.register(TurkuOIDCProvider)