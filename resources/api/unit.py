from resources.models.utils import get_municipality_help_options
from munigeo.models import Municipality
from resources.auth import has_permission, is_general_admin, is_staff
from rest_framework import serializers, viewsets
from django.contrib.auth.models import AnonymousUser
import django_filters
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly
from resources.api.base import (
    NullableDateTimeField, TranslatedModelSerializer,
    register_view, DRFFilterBooleanWidget
)
from resources.models import Unit
from resources.models.resource import Resource
from .accessibility import UnitAccessibilitySerializer
from .base import ExtraDataMixin, LocationField, PeriodSerializer
from resources.models.utils import log_entry


class UnitFilterSet(django_filters.FilterSet):
    resource_group = django_filters.Filter(field_name='resources__groups__identifier', lookup_expr='in',
                                           widget=django_filters.widgets.CSVWidget, distinct=True)
    unit_has_resource = django_filters.BooleanFilter(method='filter_unit_has_resource', widget=DRFFilterBooleanWidget)

    def filter_unit_has_resource(self, queryset, name, value):
        return queryset.exclude(resources__isnull=value)

    class Meta:
        model = Unit
        fields = ('resource_group',)


class UnitSerializer(ExtraDataMixin, TranslatedModelSerializer):
    name = serializers.DictField(required=True)
    description = serializers.DictField(required=False)
    street_address = serializers.DictField(required=True)
    www_url = serializers.DictField(required=False)
    picture_caption = serializers.DictField(required=False)
    periods = PeriodSerializer(required=False, many=True)
    opening_hours_today = serializers.DictField(
        required=False,
        read_only=True,
        source='get_opening_hours',
        child=serializers.ListField(
            child=serializers.DictField(
                child=NullableDateTimeField())
        )
    )
    location = LocationField(
        required=False,
        help_text='example: "location": {"type": "Point", "coordinates": [22.00000, 60.00000]}'
    )
    municipality = serializers.PrimaryKeyRelatedField(
        required=False,
        queryset=Municipality.objects.all(),
        help_text=f'options: {get_municipality_help_options()}')

    # depracated, available for backwards compatibility
    reservable_days_in_advance      = serializers.ReadOnlyField(source='reservable_max_days_in_advance')
    reservable_max_days_in_advance  = serializers.ReadOnlyField()
    reservable_before               = serializers.SerializerMethodField()
    reservable_min_days_in_advance  = serializers.ReadOnlyField()
    reservable_after                = serializers.SerializerMethodField()
    hidden                          = serializers.SerializerMethodField()

    def get_extra_fields(self, includes, context):
        """ Define extra fields that can be included via query parameters. Method from ExtraDataMixin."""
        extra_fields = {}
        if 'accessibility_summaries' in includes:
            # TODO: think about populating "unknown" results here if no data is available
            extra_fields['accessibility_summaries'] = UnitAccessibilitySerializer(
                many=True, read_only=True, context=context)
        return extra_fields

    def get_reservable_before(self, obj):
        request = self.context.get('request')
        user = request.user if request else None

        if user and (obj.is_admin(user) or obj.is_manager(user)):
            return None
        else:
            return obj.get_reservable_before()

    def get_reservable_after(self, obj):
        request = self.context.get('request')
        user = request.user if request else None

        if user and (obj.is_admin(user) or obj.is_manager(user)):
            return None
        else:
            return obj.get_reservable_after()

    def get_hidden(self, obj):
        request = self.context.get('request')
        user = request.user
        if not isinstance(user, AnonymousUser):
            if (user.is_staff and user.has_perm('unit:can_view_unit', obj)) or user.is_general_admin or user.is_superuser:
                return False
        x = True
        for ob in Resource.objects.filter(unit=obj).all():
            if ob.public:
                x = False
        return x
    
    def to_representation(self, obj):
        request = self.context['request']
        user = request.user
        ret = super().to_representation(obj)
        if 'timmi_profile_id' in ret:
            del ret['timmi_profile_id']

        if 'created_by' in ret and 'modified_by' in ret and \
                (not is_staff(user) and not is_general_admin(user) and
                    not has_permission(user, 'resources.view_unit')):
                        del ret['created_by']
                        del ret['modified_by']

        return ret

    
    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        periods_data = validated_data.pop('periods', [])
        unit = Unit.objects.create(**validated_data)

        periods = PeriodSerializer(data=periods_data, many=True)
        if periods.is_valid(raise_exception=True):
            periods.save(unit=unit)
        log_entry(unit, user, is_edit=False, message='Created through API')
        return unit


    def update(self, instance, validated_data):
        request = self.context['request']
        user = request.user

        if 'periods' in validated_data:
            periods_data = validated_data.pop('periods', [])
            periods = PeriodSerializer(data=periods_data, many=True)
            if periods.is_valid(raise_exception=True):
                periods.save(unit=instance)
        unit = super().update(instance, validated_data)
        log_entry(unit, user, is_edit=True, message='Edited through API: %s' % ', '.join([k for k in validated_data]))
        return unit
    
    class Meta:
        model = Unit
        fields = '__all__'
        required_translations = ('name_fi', 'name_en', 'name_sv', 'street_address_fi')
        read_only_fields = ('created_at', 'modified_at', 'created_by', 'modified_by', 'time_zone', 'id')


class UnitViewSet(viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = UnitFilterSet
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly, )


register_view(UnitViewSet, 'unit')
