import logging
from .base import TranslatedModelSerializer, register_view
from rest_framework import exceptions, filters, serializers, viewsets, response, permissions
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.settings import api_settings as drf_settings

from resources.models import (
    Resource, Period, Day
)

logger = logging.getLogger(__name__)

class DaySerializer(TranslatedModelSerializer):
    class Meta:
        model = Day
        fields = ['weekday', 'opens', 'closes']

class DayViewSet(viewsets.ModelViewSet):
    queryset = Day.objects.all()
    serializer_class = DaySerializer

class PeriodPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if (view.kwargs.get('pk', None)):
            # Handled by has_object_permission
            return True
            
        resource_id = request.data.get('resource', None)        
        if resource_id == None:
            resource_id = request.query_params.get('resource', None)
        resource = None
        try:
            resource = Resource.objects.get(pk=resource_id)
        except Resource.DoesNotExist:
            return False
        
        if resource.can_modify_opening_hours(user):
            return True

        return False

    def has_object_permission(self, request, view, obj):
        try: 
            resource = obj.resource
        except AttributeError:
            return False
        return request.user and request.user.is_authenticated and resource.can_modify_opening_hours(request.user)

class PeriodSerializer(TranslatedModelSerializer):
    def validate(self, data):
        # Check that weekdays are unique
        used_days = []
        for day in data['days']:
            if day['weekday'] in used_days:
                raise serializers.ValidationError({"day": "Weekdays must be unique"})
            used_days.append(day['weekday'])

        # Check that period starts before it ends
        if data['start'] > data['end']:
            raise serializers.ValidationError({"end": "Period must start before its end"})

        # Check for other periods with overlapping days
        resource_id = data['resource']
        days = Day.objects.filter(period__resource=resource_id, period__end__gte=data['start'], period__start__lte=data['end'])
        instance = self.instance
        if (instance != None):
            days = days.exclude(period=instance.pk)
        for day in days:
            for data_day in data['days']:
                if (day.weekday == data_day['weekday']):
                    raise serializers.ValidationError({"days": "If the period overlaps with another period it cannot have the same open days."})
                    
        return data

    days = DaySerializer(many=True)
    resource = serializers.PrimaryKeyRelatedField(
        many=False,
        read_only=False,
        required=True,
        queryset=Resource.objects.all()
     )

    class Meta:
        model = Period
        fields = ['id', 'resource', 'start', 'end', 'name', 'days']
    
    def create(self, validated_data):
        days_data = validated_data.pop("days")
        period = Period.objects.create(**validated_data)
        for day_data in days_data:
            Day.objects.create(period=period, closed=False, **day_data)
        period.save()
        return period
               
class PeriodUpdateSerializer(PeriodSerializer):
    def validate(self, data):
        super().validate(data)
        instance = self.instance
        resource = data['resource']
        if (resource != None and instance.resource != resource):
            raise serializers.ValidationError({"resource": "Resource can not be changed."})
        return data

    resource = serializers.PrimaryKeyRelatedField(
        many=False,
        read_only=False,
        required=False,
        queryset=Resource.objects.all()
    )
     
    class Meta:
        model = Period
        fields = ['start', 'resource', 'end', 'name', 'days']

    def update(self, instance, validated_data):
        days_data = validated_data.pop("days")
        instance.name = validated_data.get("name")
        instance.start = validated_data.get("start")
        instance.stop = validated_data.get("stop")
        Day.objects.filter(period=instance).delete()
        for day_data in days_data:
            Day.objects.create(period=instance, **day_data)
        instance.save()
        return instance

class PeriodViewSet(viewsets.ModelViewSet):
    serializer_class = PeriodSerializer
    queryset = Period.objects.all()
    permission_classes = (PeriodPermission, )
    authentication_classes = (
        list(drf_settings.DEFAULT_AUTHENTICATION_CLASSES) +
        [TokenAuthentication, SessionAuthentication])

    def get_serializer_class(self):
        serializer_class = self.serializer_class

        if self.request.method == 'PUT':
            serializer_class = PeriodUpdateSerializer

        return serializer_class

    http_method_names = ['get', 'post', 'put', 'delete', 'head', 'options']

register_view(PeriodViewSet, 'period', 'period')