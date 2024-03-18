import warnings
import uuid

from calendar import timegm
from datetime import datetime
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.settings import api_settings

def jwt_payload_handler(user):
    username_field = get_user_model().USERNAME_FIELD
    username = getattr(user, 'get_username', lambda: user.username)()

    warnings.warn(
        'The following fields will be removed in the future: '
        '`email` and `user_id`. ',
        DeprecationWarning
    )

    payload = {
        'user_id': user.pk,
        'sub': str(user.uuid), # addition to original payload
        'username': username,
        'exp': datetime.utcnow() + api_settings.EXPIRATION_DELTA
    }
    if hasattr(user, 'email'):
        payload['email'] = user.email
    if isinstance(user.pk, uuid.UUID):
        payload['user_id'] = str(user.pk)

    payload[username_field] = username

    # Include original issued at time for a brand new token,
    # to allow token refresh
    if api_settings.ALLOW_REFRESH:
        payload['orig_iat'] = timegm(
            datetime.utcnow().utctimetuple()
        )

    if api_settings.AUDIENCE is not None:
        payload['aud'] = api_settings.AUDIENCE

    if api_settings.ISSUER is not None:
        payload['iss'] = api_settings.ISSUER

    return payload
