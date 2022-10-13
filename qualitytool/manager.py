from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _
from functools import wraps

from qualitytool.api.serializers.external import (
    QualityToolFormSerializer,
    QualityToolTargetListSerializer,
)
from .utils import clear_cache, has_expired, HEADERS, lru_cache

import requests
import logging
import pycountry

logger = logging.getLogger(__name__)


def ensure_token(func):
    @wraps(func)
    def wrapped(self, *args, **kwargs):
        if not hasattr(self, 'session'):
            setattr(self, 'session', requests.Session())
            self.session.headers = HEADERS
        session_auth_token = getattr(self, '__session_auth_token', None)
        if has_expired(session_auth_token):
            logger.info('QualityToolManager: Session token has expired, fetching a new one.')
            response = self.session.post(self.config['AUTHENTICATE'], json={
                'username': settings.QUALITYTOOL_USERNAME,
                'password': settings.QUALITYTOOL_PASSWORD
            })
            assert response.status_code == 200, 'HTTP: %d' % response.status_code
            new_token = response.content.decode()
            setattr(self, '__session_auth_token', new_token)
            self.session.headers.update({
                'Authorization': 'Bearer %s' % new_token
            })
        return func(self, *args, **kwargs)
    return wrapped

class QualityToolManager(models.QuerySet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = self.get_config()

    def __call__(self, *args, **kwargs):
        return super().__init__(*args, **kwargs)

    @staticmethod
    def get_config():
        return {
            'AUTHENTICATE': f'{settings.QUALITYTOOL_API_BASE}/auth/v1/authenticate',
            'FEEDBACK_LIST': f'{settings.QUALITYTOOL_API_BASE}/external/v1/feedback/list',
            'FEEDBACK_INSERT': f'{settings.QUALITYTOOL_API_BASE}/external/v1/feedback/insert',
            'FEEDBACK_FORM': f'{settings.QUALITYTOOL_API_BASE}/external/v1/feedback/form-resources',
            'TARGET_LIST': f'{settings.QUALITYTOOL_API_BASE}/external/v1/target/list',
        }

    @ensure_token
    @clear_cache(seconds=600)
    @lru_cache
    def get_target_list(self):
        response = self.session.get(self.config['TARGET_LIST'])
        serializer = QualityToolTargetListSerializer(data=response.json(), many=True)
        serializer.is_valid(True)
        return serializer.data

    @ensure_token
    @clear_cache(seconds=43200) # Clear lru_cache after 12 hours.
    @lru_cache
    def get_form(self):
        response = self.session.get(self.config['FEEDBACK_FORM'])
        serializer = QualityToolFormSerializer(data=response.json())
        serializer.is_valid(True)
        return serializer.data

    @ensure_token
    @clear_cache(seconds=86400)
    @lru_cache
    def get_form_languages(self):
        response = self.session.get(self.config['FEEDBACK_FORM'])
        if response.status_code == 200:
            return \
                [(
                    key,
                    _(pycountry.languages.get(alpha_2=key.upper()).name).capitalize()
                ) for key, __ in response.json().items()]
        return []
    
    @ensure_token
    def post_rating(self, data):
        response = self.session.post(self.config['FEEDBACK_INSERT'], json=[data])
        return response.json()


qt_manager = QualityToolManager()