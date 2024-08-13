from helusers.oidc import resolve_user, ApiTokenAuthentication as HelusersApiTokenAuthentication
from helusers.authz import UserAuthorization
from helusers.user_utils import _try_create_or_update
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from django.utils.translation import gettext as _
from django.conf import settings
from rest_framework import exceptions
from django.db import transaction, IntegrityError
from .jwt import JWT

class ApiTokenAuthentication(HelusersApiTokenAuthentication):
    def authenticate(self, request):
        jwt_value = self.get_jwt_value(request)
        if jwt_value is None:
            return None
        try:
            payload = self.decode_jwt(jwt_value)
        except:
            return None

        self.validate_claims(payload)
        user = get_or_create_user(payload, True)
        auth = UserAuthorization(user, payload, self.settings)

        if self.settings.REQUIRE_API_SCOPE_FOR_AUTHENTICATION:
            api_scope = self.settings.API_SCOPE_PREFIX
            if not auth.has_api_scope_with_prefix(api_scope):
                raise AuthenticationFailed(
                    _("Not authorized for API scope \"{api_scope}\"")
                    .format(api_scope=api_scope))
        user.amr = payload['amr']
        return (user, auth)

    def decode_jwt(self, jwt_value):
        jwt = JWT(jwt_value, settings=self.settings)

        try:
            jwt.validate_issuer()
        except ValidationError as e:
            raise AuthenticationFailed(str(e)) from e

        keys = self.get_oidc_config(jwt.issuer).keys()
        try:
            jwt.validate(keys, self.settings.AUDIENCE)
            jwt.validate_api_scope()
            jwt.validate_session()
            self.validate_claims(jwt.claims)
        except ValidationError as e:
            raise AuthenticationFailed(str(e)) from e
        except Exception as e:
            raise AuthenticationFailed("JWT verification failed.")

        return jwt.claims

def get_or_create_user(payload, oidc=False):
    user_id = payload.get('sub')
    if not user_id:
        msg = _('Invalid payload.')
        raise exceptions.AuthenticationFailed(msg)
    try_again = False
    try:
        user = _try_create_or_update(user_id, payload, oidc)
    except IntegrityError:
        try_again = True
    if try_again:
        user = _try_create_or_update(user_id, payload, oidc)
    return user
