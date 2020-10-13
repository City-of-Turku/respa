import logging
from rest_framework import serializers
from resources.models import Resource
from users.models import User

logger = logging.getLogger(__name__)

class OutlookCalendarLinkSerializer(serializers.Serializer):
    id = serializers.ReadOnlyField()
    resource = serializers.PrimaryKeyRelatedField(queryset=Resource.objects.all())
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    authorization_response_url = serializers.CharField(required=False)
    token = serializers.CharField(required=False, write_only=True)
    reservation_calendar_id = serializers.CharField(required=False)
    availability_calendar_id = serializers.CharField(required=False)
