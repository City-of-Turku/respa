from django.conf import settings
from rest_framework.settings import APISettings
from .defaults import SOCIAL_AUTH_PIPELINE


USER_SETTINGS = getattr(settings, 'OIDC_AUTH', None)

DEFAULTS = dict(
    # Accepted audience, the API Token must have this in its aud field
    AUDIENCE=None,

    # API scope prefix for permission checks
    API_SCOPE_PREFIX=None,

    # Is API scope required for successful authentication.
    #
    # If this setting is set, then authentication will fail, if the API
    # scopes field doesn't contain the API_SCOPE_PREFIX or any value that
    # starts with API_SCOPE_PREFIX and a dot.
    #
    # E.g. if API_SCOPE_PREFIX='xyz' and this is set to true, then the
    # authentication will fail if the API scopes doesn't contain either
    # 'xyz' or an item that starts with 'xyz.' (like 'xyz.readonly' or
    # 'xyz.view').
    REQUIRE_API_SCOPE_FOR_AUTHENTICATION=False,

    # Field name containing the API scopes authorized by the user
    API_AUTHORIZATION_FIELD='',

    # URL of the OpenID Provider
    ISSUER='https://tunnistamo.turku.fi',

    # Auth scheme used in the Authorization header
    AUTH_SCHEME='Bearer',

    # Function for resolving users
    USER_RESOLVER='tkusers.oidc.resolve_user',

    # OIDC config expiration time
    OIDC_CONFIG_EXPIRATION_TIME=24 * 60 * 60,
    OIDC_LEEWAY=24 * 60 * 60,
)
IMPORT_STRINGS = [
    'USER_RESOLVER',
]


api_token_auth_settings = APISettings(
    USER_SETTINGS, DEFAULTS, IMPORT_STRINGS)
