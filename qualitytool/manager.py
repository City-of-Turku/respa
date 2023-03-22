from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from functools import wraps
from datetime import datetime, timedelta
from qualitytool.api.serializers.external import (
    QualityToolFormSerializer,
    QualityToolTargetListSerializer,
)
from resources.models import Reservation, Resource
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

class QualityToolManager():
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = self.get_config()

    @staticmethod
    def get_config():
        return {
            'AUTHENTICATE': f'{settings.QUALITYTOOL_API_BASE}/auth/v1/authenticate',
            'FEEDBACK_LIST': f'{settings.QUALITYTOOL_API_BASE}/external/v1/feedback/list',
            'FEEDBACK_INSERT': f'{settings.QUALITYTOOL_API_BASE}/external/v1/feedback/insert',
            'FEEDBACK_FORM': f'{settings.QUALITYTOOL_API_BASE}/external/v1/feedback/form-resources',
            'TARGET_LIST': f'{settings.QUALITYTOOL_API_BASE}/external/v1/target/list',
            'UTILIZATION_UPSERT': f'{settings.QUALITYTOOL_API_BASE}/external/v1/utilization/upsert'
        }

    @ensure_token
    @clear_cache(seconds=600)
    @lru_cache(maxsize=None)
    def get_targets(self):
        response = self.session.get(self.config['TARGET_LIST'])
        serializer = QualityToolTargetListSerializer(data=response.json(), many=True)
        serializer.is_valid(raise_exception=True)
        return serializer.data

    def _instance_to_dict(self, instance, **extra):
        obj = dict(targetId=instance.target_id, name={})
        for lang, _ in settings.LANGUAGES:
            obj['name'][lang] = getattr(instance, 'name_%s' % lang)
        obj.update(**extra)
        return obj

    @ensure_token
    @clear_cache(seconds=43200) # Clear lru_cache after 12 hours.
    @lru_cache(maxsize=None)
    def get_form(self):
        response = self.session.get(self.config['FEEDBACK_FORM'])
        serializer = QualityToolFormSerializer(data=response.json())
        serializer.is_valid(raise_exception=True)
        return serializer.data

    @ensure_token
    @clear_cache(seconds=86400)
    @lru_cache(maxsize=None)
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
    def post_rating(self, data : dict):
        if not isinstance(data, dict):
            raise ValueError('Data must be dict')
        response = self.session.post(self.config['FEEDBACK_INSERT'], json=data)
        return response.json()

    @ensure_token
    def post_utilization(self, data : list):
        if not isinstance(data, list):
            raise ValueError('Data must be list')
        response = self.session.post(self.config['UTILIZATION_UPSERT'], json=data)
        return response.json()

    def get_daily_utilization(self, qualitytool, date) -> dict:
        """
        Returns volume count of reservations that were created the given date
        return: {
            'targetId': uuid,
            'date': (date - timedelta(days=1)).date(),
            'volume': int
        }
        """
        begin = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date.replace(hour=23, minute=59, second=59, microsecond=0)
    
        query = models.Q(reservations__created_at__gte=begin, reservations__created_at__lte=end)
        if qualitytool.emails:
            query &= models.Q(
                models.Q(reservations__user__email__in=qualitytool.emails) |
                models.Q(reservations__reserver_email_address__in=qualitytool.emails)
            )
        volume = qualitytool.resources.filter(query).values_list('reservations', flat=True)
        return {
            'targetId': str(qualitytool.target_id), 
            'date': str(date.date()),
            'volume': volume.count()
        }

qt_manager = QualityToolManager()