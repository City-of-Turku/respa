import collections
import datetime
import logging
import jsonschema as json

import arrow
import base64
import django_filters
import pytz
from arrow.parser import ParserError

from django import forms
from django.conf import settings
from django.core.validators import validate_email
from django.core.files.base import ContentFile
from django.db.models import OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce, Least
from django.urls import reverse
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.auth import get_user_model
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from resources.timmi import TimmiManager
from PIL import Image
from io import BytesIO

from resources.pagination import PurposePagination
from rest_framework import (
    exceptions, filters, mixins, 
    serializers, viewsets, response, 
    status, generics, permissions, fields
)
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import action
from guardian.core import ObjectPermissionChecker
from munigeo import api as munigeo_api
from resources.models import (
    AccessibilityValue, AccessibilityViewpoint, Purpose, Reservation, Resource, ResourceAccessibility,
    ResourceImage, ResourceType, ResourceEquipment, TermsOfUse, Equipment, ReservationMetadataSet,
    ReservationMetadataField, ReservationHomeMunicipalityField,
    ReservationHomeMunicipalitySet, ResourceDailyOpeningHours, UnitAccessibility, Unit, ResourceTag
)
from resources.models.resource import determine_hours_time_range
from payments.models import Product

from ..auth import has_permission, is_general_admin, is_staff
from .accessibility import ResourceAccessibilitySerializer
from .base import (
    ExtraDataMixin, TranslatedModelSerializer, register_view,
    DRFFilterBooleanWidget, PeriodSerializer, DaySerializer, Period,
    LocationField, get_translated_field_help_text
)
from .reservation import ReservationSerializer
from .unit import UnitSerializer
from .equipment import EquipmentSerializer
from rest_framework.settings import api_settings as drf_settings

from random import sample


logger = logging.getLogger(__name__)


def parse_query_time_range(params):
    times = {}
    for name in ('start', 'end'):
        if name not in params:
            continue
        try:
            times[name] = arrow.get(params[name]).to('utc').datetime
        except ParserError:
            raise exceptions.ParseError("'%s' must be a timestamp in ISO 8601 format" % name)

    if len(times):
        if 'start' not in times or 'end' not in times:
            raise exceptions.ParseError("You must supply both 'start' and 'end'")
        if times['end'] < times['start']:
            raise exceptions.ParseError("'end' must be after 'start'")

    return times


def get_resource_reservations_queryset(begin, end):
    qs = Reservation.objects.filter(begin__lte=end, end__gte=begin).current()
    qs = qs.order_by('begin').prefetch_related('catering_orders').select_related('user', 'order')
    return qs


class PurposeSerializer(TranslatedModelSerializer):
    name = serializers.DictField(
            required=True,
            help_text='example: "name": {"fi": "string", "en": "string", "sv": "string"}'
        )
    image = serializers.FileField(
            required=False,
            help_text='Can be given as base64 encoded string. Include "file_name" in the request to name the file.'
        )
    class Meta:
        model = Purpose
        fields = ['name', 'parent', 'id', 'image', 'public']
        required_translations = ['name_fi', 'name_en', 'name_sv']

    def to_representation(self, obj):
        ret = super().to_representation(obj)
        request = self.context.get('request')
        if request:
            user = request.user
            if not is_staff(user) and not is_general_admin(user) and not has_permission(user, 'resources.view_purpose'):
                del ret['public']

        return ret

    def to_internal_value(self, data):
        if 'image' in data and isinstance(data['image'], str) and ';base64,' in data['image']:
            img_name = f'{data.get("file_name", "image")}.'
            formatt, imgstr = data['image'].split(';base64,')
            ext = formatt.split('/')[-1]
            data['image'] = ContentFile(base64.b64decode(imgstr), name=img_name + ext)
        data = super().to_internal_value(data)
        return data
    
    def create(self, validated_data):
        parent = validated_data.pop('parent', None)
        if parent and isinstance(parent, str):
            parent = Purpose.objects.get(pk=parent)

        purpose = Purpose.objects.create(parent=parent, **validated_data)
        return purpose

    def update(self, instance, validated_data):
        if 'parent' in validated_data:
            parent = validated_data.pop('parent', None)
            if parent and isinstance(parent, str):
                parent = Purpose.objects.get(pk=parent)

            validated_data['parent'] = parent
        
        super().update(instance, validated_data)
        return instance

class PurposeViewSet(viewsets.ModelViewSet):
    queryset = Purpose.objects.all()
    serializer_class = PurposeSerializer
    pagination_class = PurposePagination
    permission_classes = [DjangoModelPermissionsOrAnonReadOnly]

    def get_queryset(self):
        user = self.request.user
        if is_staff(user) or is_general_admin(user) or has_permission(user, 'resources.view_purpose'):
            return self.queryset
        else:
            return self.queryset.filter(public=True)


register_view(PurposeViewSet, 'purpose')


class ResourceTypeSerializer(TranslatedModelSerializer):
    name = serializers.DictField(required=True)

    class Meta:
        model = ResourceType
        fields = ['name', 'main_type', 'id']
        required_translations = ['name_fi']
        read_only_fields = ['id']


class ResourceTypeFilterSet(django_filters.FilterSet):
    resource_group = django_filters.Filter(field_name='resource__groups__identifier', lookup_expr='in',
                                           widget=django_filters.widgets.CSVWidget, distinct=True)

    class Meta:
        model = ResourceType
        fields = ('resource_group',)


class ResourceTypeViewSet(viewsets.ModelViewSet):
    queryset = ResourceType.objects.all()
    serializer_class = ResourceTypeSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = ResourceTypeFilterSet
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly, )


register_view(ResourceTypeViewSet, 'type')


class ImageSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    data = serializers.CharField(required=True, help_text='Data must be base64 encoded')

    def validate(self, attrs):
        try:
            img = Image.open(BytesIO(base64.b64decode(attrs['data'].encode())))
            if img.format not in ("JPEG", "PNG", "SVG"):
                raise Exception("Invalid format: %s" % img.format)
        except Exception as exc:
            raise serializers.ValidationError({
                'message':[_(str(exc))]
            }) from exc
        return attrs

    @property
    def content_file(self):
        return ContentFile(base64.b64decode(self.data['data'].encode()), name=self.data['name'])

class ResourceImageSerializer(TranslatedModelSerializer):
    id = serializers.IntegerField(required=False)
    type = serializers.ChoiceField(choices=ResourceImage.TYPES, required=True)
    caption = serializers.DictField(required=True)
    image = ImageSerializer(required=False)


    class Meta:
        model = ResourceImage
        exclude = (
            'image_format', 'sort_order', 'resource',
            'created_at', 'modified_at', 'created_by', 'modified_by'
        )
        required_translations = (
            'caption_fi', 'caption_en', 'caption_sv'
        )

    def validate(self, attrs):
        request = self.context['request']
        if 'image' not in attrs:
            raise serializers.ValidationError({
                'image': [_('This field is required.')]
            })

        return super().validate(attrs)

    def create(self, validated_data):
        if 'id' in validated_data:
            del validated_data['id']


        request = self.context['request']
        user = request.user
        image = validated_data.pop('image')
        serializer = ImageSerializer(data=image)
        serializer.is_valid()
        validated_data['image'] = serializer.content_file
        validated_data['created_by'] = user
        instance = super().create(validated_data)
        instance._process_image()
        return instance
    
    def update(self, resource, validated_data):
        if 'id' not in validated_data:
            return self.create(validated_data)

        request = self.context['request']
        user = request.user

    
        image = validated_data.pop('image')
        serializer = ImageSerializer(data=image)
        serializer.is_valid()
        validated_data['image'] = serializer.content_file
        validated_data['modified_by'] = user
        try:
            instance = self.Meta.model.objects.get(resource=resource, pk=validated_data['id'])
            instance = super().update(instance, validated_data)
        except ObjectDoesNotExist:
            if self.Meta.model.objects.filter(pk=validated_data['id']).exists():
                raise serializers.ValidationError({
                    'image': {
                        'id': 'Image with id "%d" belongs to another resource.' % validated_data['id']
                    }
                })
            validated_data['created_by'] = user
            instance = super().create(validated_data)

        instance._process_image()
        return instance
    
class NestedResourceImageSerializer(TranslatedModelSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        url = reverse('resource-image-view', kwargs={'pk': obj.pk})
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(url)

    class Meta:
        model = ResourceImage
        fields = ('url', 'type', 'caption')
        ordering = ('resource', 'sort_order')


class ResourceEquipmentSerializer(TranslatedModelSerializer):
    equipment = EquipmentSerializer()

    class Meta:
        model = ResourceEquipment
        fields = ('equipment', 'data', 'id', 'description')

    def to_representation(self, obj):
        # remove unnecessary nesting and aliases
        if 'equipment_cache' in self.context:
            obj.equipment = self.context['equipment_cache'][obj.equipment_id]
        ret = super().to_representation(obj)
        ret['name'] = ret['equipment']['name']
        ret['id'] = ret['equipment']['id']
        del ret['equipment']
        return ret


class TermsOfUseSerializer(TranslatedModelSerializer):
    id = serializers.CharField(required=False)
    name = serializers.DictField(required=True)
    text = serializers.DictField(required=True)
    terms_type = serializers.ChoiceField(choices=TermsOfUse.TERMS_TYPES, required=True)

    class Meta:
        model = TermsOfUse
        fields = (
            'name', 'terms_type', 
            'text', 'id'
        )
        required_translations = (
            'name_fi', 
            'text_fi', 'text_en', 'text_sv'
        )
    
    def validate(self, attrs):
        terms_type = attrs.get('terms_type', "")
        if terms_type != TermsOfUse.TERMS_TYPE_GENERIC and \
            terms_type != TermsOfUse.TERMS_TYPE_PAYMENT:
            raise serializers.ValidationError({
                'terms_type': [_('Missing required field: "%(generic)s" or "%(payment)s"' % ({
                    'generic': TermsOfUse.TERMS_TYPE_GENERIC,
                    'payment': TermsOfUse.TERMS_TYPE_PAYMENT
                }))]
            })
        return super().validate(attrs)
    
    def update(self, resource, validated_data):
        if not isinstance(resource, Resource):
            raise TypeError("Invalid type: %s passed to %s" % (type(resource), str(self.__class__.__name__)))
        try:
            instance = self.Meta.model.objects.get(resources_where_generic_terms=resource, terms_type=validated_data['terms_type'])
        except ObjectDoesNotExist:
            instance = self.create(validated_data)
            setattr(resource, validated_data['terms_type'], instance)
        return super().update(instance, validated_data)

class ResourceStaffEmailsField(serializers.ListField):
    def to_internal_value(self, data):
        return '\n'.join(data)
    
    def validate_empty_values(self, data):
        if data == fields.empty:
            return super().validate_empty_values(data)

        if not data:
            raise serializers.ValidationError(_('This field cannot be empty.'))
        
        for email in data:
            validate_email(email)

        return super().validate_empty_values(data)
    
    def to_representation(self, data):
        if not data:
            return []
        if isinstance(data, list):
            return data
        return str(data).split('\n')

class ResourceSerializer(ExtraDataMixin, TranslatedModelSerializer, munigeo_api.GeoModelSerializer):
    purposes = PurposeSerializer(many=True)
    images = NestedResourceImageSerializer(many=True)
    equipment = ResourceEquipmentSerializer(many=True, read_only=True, source='resource_equipment')
    type = ResourceTypeSerializer()
    # FIXME: location field gets removed by munigeo
    location = serializers.SerializerMethodField()
    # FIXME: Enable available_hours when it's more performant
    # available_hours = serializers.SerializerMethodField()
    opening_hours = serializers.SerializerMethodField()
    reservations = serializers.SerializerMethodField()
    user_permissions = serializers.SerializerMethodField()
    supported_reservation_extra_fields = serializers.ReadOnlyField(source='get_supported_reservation_extra_field_names')
    required_reservation_extra_fields = serializers.ReadOnlyField(source='get_required_reservation_extra_field_names')
    included_reservation_home_municipality_fields = serializers.ReadOnlyField(source='get_included_home_municipality_names')
    is_favorite = serializers.SerializerMethodField()
    generic_terms = serializers.SerializerMethodField()
    payment_terms = serializers.SerializerMethodField()
    # deprecated, backwards compatibility
    reservable_days_in_advance = serializers.ReadOnlyField(source='get_reservable_max_days_in_advance')
    reservable_max_days_in_advance = serializers.ReadOnlyField(source='get_reservable_max_days_in_advance')
    reservable_before = serializers.SerializerMethodField()
    reservable_min_days_in_advance = serializers.ReadOnlyField(source='get_reservable_min_days_in_advance')
    reservable_after = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    max_price_per_hour = serializers.SerializerMethodField()
    min_price_per_hour = serializers.SerializerMethodField()
    resource_staff_emails = ResourceStaffEmailsField()

    def get_max_price_per_hour(self, obj):
        """Backwards compatibility for 'max_price_per_hour' field that is now deprecated"""
        return obj.max_price if obj.price_type == Resource.PRICE_TYPE_HOURLY else None

    def get_min_price_per_hour(self, obj):
        """Backwards compatibility for 'min_price_per_hour' field that is now deprecated"""
        return obj.min_price if obj.price_type == Resource.PRICE_TYPE_HOURLY else None

    def get_extra_fields(self, includes, context):
        """ Define extra fields that can be included via query parameters. Method from ExtraDataMixin."""
        extra_fields = {}
        if 'accessibility_summaries' in includes:
            extra_fields['accessibility_summaries'] = serializers.SerializerMethodField()
        if 'unit_detail' in includes:
            extra_fields['unit'] = UnitSerializer(read_only=True, context=context)
        return extra_fields

    def get_accessibility_summaries(self, obj):
        """ Get accessibility summaries for the resource. If data is missing for
        any accessibility viewpoints, unknown values are returned for those.
        """
        if 'accessibility_viewpoint_cache' in self.context:
            accessibility_viewpoints = self.context['accessibility_viewpoint_cache']
        else:
            accessibility_viewpoints = AccessibilityViewpoint.objects.all()
        summaries_by_viewpoint = {acc_s.viewpoint_id: acc_s for acc_s in obj.accessibility_summaries.all()}
        summaries = [
            summaries_by_viewpoint.get(
                vp.id,
                ResourceAccessibility(
                    viewpoint=vp, resource=obj, value=AccessibilityValue(value=AccessibilityValue.UNKNOWN_VALUE)))
            for vp in accessibility_viewpoints]
        return [ResourceAccessibilitySerializer(summary).data for summary in summaries]

    def get_tags(self, obj):
        return list(set(
            [tag.label for tag in ResourceTag.objects.filter(resource=obj)] + list(obj.tags.names())))

    def get_user_permissions(self, obj):
        request = self.context.get('request', None)
        prefetched_user = self.context.get('prefetched_user', None)

        if request:
            user = prefetched_user or request.user

        return {
            'can_make_reservations': obj.can_make_reservations(user) if request else False,
            'can_ignore_opening_hours': obj.can_ignore_opening_hours(user) if request else False,
            'is_admin': obj.is_admin(user) if request else False,
            'is_manager': obj.is_manager(user) if request else False,
            'is_viewer': obj.is_viewer(user) if request else False,
            'can_bypass_payment': obj.can_bypass_payment(user) if request else False,
        }

    def get_is_favorite(self, obj):
        request = self.context.get('request', None)
        return request.user in obj.favorited_by.all()

    def get_generic_terms(self, obj):
        data = TermsOfUseSerializer(obj.generic_terms).data
        return data['text']

    def get_payment_terms(self, obj):
        data = TermsOfUseSerializer(obj.payment_terms).data
        return data['text']

    def get_reservable_before(self, obj):
        request = self.context.get('request')
        prefetched_user = self.context.get('prefetched_user', None)

        user = None
        if request:
            user = prefetched_user or request.user

        user = None
        if request:
            user = prefetched_user or request.user

        if user and (obj.is_admin(user) or obj.is_manager(user)):
            return None
        else:
            return obj.get_reservable_before()

    def get_reservable_after(self, obj):
        request = self.context.get('request')
        prefetched_user = self.context.get('prefetched_user', None)

        user = None
        if request:
            user = prefetched_user or request.user

        if user and (obj.is_admin(user) or obj.is_manager(user)):
            return None
        else:
            return obj.get_reservable_after()

    def to_representation(self, obj):
        request = self.context['request']
        user = request.user
        # we must parse the time parameters before serializing
        self.parse_parameters()
        if isinstance(obj, dict):
            # resource is already serialized
            return obj

        # We cache the metadata objects to save on SQL roundtrips
        if 'reservation_metadata_set_cache' in self.context:
            set_id = obj.reservation_metadata_set_id
            if set_id:
                obj.reservation_metadata_set = self.context['reservation_metadata_set_cache'][set_id]
        if 'reservation_home_municipality_set_cache' in self.context:
            home_municipality_set_id = obj.reservation_home_municipality_set_id
            if home_municipality_set_id:
                obj.reservation_home_municipality_set = self.context['reservation_home_municipality_set_cache'][home_municipality_set_id]
        ret = super().to_representation(obj)
        if hasattr(obj, 'distance'):
            if obj.distance is not None:
                ret['distance'] = int(obj.distance.m)
            elif obj.unit_distance is not None:
                ret['distance'] = int(obj.unit_distance.m)

        if 'timmi_resource' in ret:
            del ret['timmi_resource']
        if 'timmi_room_id' in ret:
            del ret['timmi_room_id']

        if 'resource_staff_emails' in ret and \
                (not is_staff(user) and not is_general_admin(user) and
                    not has_permission(user, 'resources.view_resource')):
                        del ret['resource_staff_emails']


        if 'period_details' in self.context['includes']:
            ret['periods'] = [
                PeriodSerializer().to_representation(period) for period in Period.objects.filter(resource=obj).defer('days__length')
            ]

        return ret

    def get_location(self, obj):
        if obj.location is not None:
            return obj.location
        return obj.unit.location

    def parse_parameters(self):
        """
        Parses request time parameters for serializing available_hours, opening_hours
        and reservations
        """

        params = self.context['request'].query_params
        times = parse_query_time_range(params)

        if 'duration' in params:
            try:
                times['duration'] = int(params['duration'])
            except ValueError:
                raise exceptions.ParseError("'duration' must be supplied as an integer")

        if 'during_closing' in params:
            during_closing = params['during_closing'].lower()
            if during_closing == 'true' or during_closing == 'yes' or during_closing == '1':
                times['during_closing'] = True

        if len(times):
            self.context.update(times)

    def get_opening_hours(self, obj):
        if 'start' in self.context:
            start = self.context['start']
            end = self.context['end']
        else:
            start = None
            end = None

        hours_cache = self.context.get('opening_hours_cache', {}).get(obj.id)
        hours_by_date = obj.get_opening_hours(start, end, opening_hours_cache=hours_cache)

        ret = []
        for x in sorted(hours_by_date.items()):
            d = collections.OrderedDict(date=x[0].isoformat())
            if len(x[1]):
                d.update(x[1][0])
            ret.append(d)
        return ret

    def get_reservations(self, obj):
        if obj.timmi_resource:
            return None
        if 'start' not in self.context:
            return None

        if 'reservations_cache' in self.context:
            rv_list = self.context['reservations_cache'].get(obj.id, [])
            for rv in rv_list:
                rv.resource = obj
        else:
            rv_list = get_resource_reservations_queryset(self.context['start'], self.context['end'])
            rv_list = rv_list.filter(Q(resource=obj)|Q(resource__timmi_resource=False))

        rv_list = list(rv_list)
        if not rv_list:
            return []

        rv_ser_list = ReservationSerializer(rv_list, many=True, context=self.context).data
        return rv_ser_list

    class Meta:
        model = Resource
        exclude = ('reservation_requested_notification_extra', 'reservation_confirmed_notification_extra',
                   'access_code_type', 'reservation_metadata_set', 'reservation_home_municipality_set', 
                   'created_by', 'modified_by', 'configuration', 'resource_email')


class ResourceDetailsSerializer(ResourceSerializer):
    unit = UnitSerializer()


class ResourceInlineSerializer(ResourceDetailsSerializer):
    """
    Serializer that has a limited set of fields in order to avoid
    performance issues. Used by .reservation.ReservationSerializer,
    when request has 'include=resource_detail` parameter.

    Before including any other fields here make sure that the view
    which will call this serializer has optimized queryset, i.e. it
    selects/prefetches related fields.
    """
    class Meta:
        model = Resource
        fields = ('id', 'name', 'unit', 'location')


class ParentFilter(django_filters.Filter):
    """
    Filter that also checks the parent field
    """

    def filter(self, qs, value):
        child_matches = super().filter(qs, value)
        self.field_name = self.field_name.replace('__id', '__parent__id')
        parent_matches = super().filter(qs, value)
        return child_matches | parent_matches


class ParentCharFilter(ParentFilter):
    field_class = forms.CharField


class ResourceOrderingFilter(django_filters.OrderingFilter):
    """
    Resource ordering with added capabilities for Accessibility data.
    """

    def filter(self, qs, value):
        if value and ('accessibility' in value or '-accessibility' in value):
            viewpoint_id = self.parent.data.get('accessibility_viewpoint')
            try:
                accessibility_viewpoint = AccessibilityViewpoint.objects.get(id=viewpoint_id)
            except AccessibilityViewpoint.DoesNotExist:
                accessibility_viewpoint = AccessibilityViewpoint.objects.first()
            if accessibility_viewpoint is None:
                logging.error('Accessibility Viewpoints are not imported from Accessibility database')
                value = [val for val in value if val != 'accessibility' and val != '-accessibility']
                return super().filter(qs, value)

            # annotate the queryset with accessibility priority from selected viewpoint.
            # use the worse value of the resource and unit accessibilities.
            # missing accessibility data is considered same priority as UNKNOWN.
            resource_accessibility_summary = ResourceAccessibility.objects.filter(
                resource_id=OuterRef('pk'), viewpoint_id=accessibility_viewpoint.id)
            resource_accessibility_order = Subquery(resource_accessibility_summary.values('order')[:1])
            unit_accessibility_summary = UnitAccessibility.objects.filter(
                unit_id=OuterRef('unit_id'), viewpoint_id=accessibility_viewpoint.id)
            unit_accessibility_order = Subquery(unit_accessibility_summary.values('order')[:1])
            qs = qs.annotate(
                accessibility_priority=Least(
                    Coalesce(resource_accessibility_order, Value(AccessibilityValue.UNKNOWN_ORDERING)),
                    Coalesce(unit_accessibility_order, Value(AccessibilityValue.UNKNOWN_ORDERING))
                )
            ).prefetch_related('accessibility_summaries')
        return super().filter(qs, value)


class ResourceFilterSet(django_filters.FilterSet):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    purpose = ParentCharFilter(field_name='purposes__id', lookup_expr='iexact')
    type = django_filters.Filter(field_name='type__id', lookup_expr='in', widget=django_filters.widgets.CSVWidget)
    people = django_filters.NumberFilter(field_name='people_capacity', lookup_expr='gte')
    need_manual_confirmation = django_filters.BooleanFilter(field_name='need_manual_confirmation',
                                                            widget=DRFFilterBooleanWidget)
    is_favorite = django_filters.BooleanFilter(method='filter_is_favorite', widget=DRFFilterBooleanWidget)
    unit = django_filters.CharFilter(field_name='unit__id', lookup_expr='iexact')
    resource_group = django_filters.Filter(field_name='groups__identifier', lookup_expr='in',
                                           widget=django_filters.widgets.CSVWidget, distinct=True)
    equipment = django_filters.Filter(field_name='resource_equipment__equipment__id', lookup_expr='in',
                                      widget=django_filters.widgets.CSVWidget, distinct=True)
    available_between = django_filters.Filter(method='filter_available_between',
                                              widget=django_filters.widgets.CSVWidget)
    free_of_charge = django_filters.BooleanFilter(method='filter_free_of_charge',
                                                  widget=DRFFilterBooleanWidget)
    municipality = django_filters.Filter(field_name='unit__municipality_id', lookup_expr='in',
                                         widget=django_filters.widgets.CSVWidget, distinct=True)
    keywords = django_filters.CharFilter(method='filter_keywords')

    order_by = ResourceOrderingFilter(
        fields=(
            ('name_fi', 'resource_name_fi'),
            ('name_en', 'resource_name_en'),
            ('name_sv', 'resource_name_sv'),
            ('unit__name_fi', 'unit_name_fi'),
            ('unit__name_en', 'unit_name_en'),
            ('unit__name_sv', 'unit_name_sv'),
            ('type__name_fi', 'type_name_fi'),
            ('type__name_en', 'type_name_en'),
            ('type__name_sv', 'type_name_sv'),
            ('people_capacity', 'people_capacity'),
            ('accessibility_priority', 'accessibility'),
        ),
    )

    def filter_keywords(self, queryset, field, keywords):
        cleaned = [keyword.strip() for keyword in keywords.split(',') if keyword.strip()]
        return queryset.filter(id__in=[tag.resource.id for tag in ResourceTag.objects.filter(label__in=cleaned)])

    def filter_is_favorite(self, queryset, name, value):
        if not self.user.is_authenticated:
            if value:
                return queryset.none()
            else:
                return queryset

        if value:
            return queryset.filter(favorited_by=self.user)
        else:
            return queryset.exclude(favorited_by=self.user)

    def filter_free_of_charge(self, queryset, name, value):
        qs = Q(min_price__lte=0) | Q(min_price__isnull=True)
        if value:
            return queryset.filter(qs)
        else:
            return queryset.exclude(qs)

    def _deserialize_datetime(self, value):
        try:
            return arrow.get(value).datetime
        except ParserError:
            raise exceptions.ParseError("'%s' must be a timestamp in ISO 8601 format" % value)

    def filter_available_between(self, queryset, name, value):
        if len(value) < 2 or len(value) > 3:
            raise exceptions.ParseError('available_between takes two or three comma-separated values.')

        available_start = self._deserialize_datetime(value[0])
        available_end = self._deserialize_datetime(value[1])

        if available_start.date() != available_end.date():
            raise exceptions.ParseError('available_between timestamps must be on the same day.')
        overlapping_reservations = Reservation.objects.filter(
            resource__in=queryset, end__gt=available_start, begin__lt=available_end
        ).current()

        if len(value) == 2:
            return self._filter_available_between_whole_range(
                queryset, overlapping_reservations, available_start, available_end
            )
        else:
            try:
                period = datetime.timedelta(minutes=int(value[2]))
            except ValueError:
                raise exceptions.ParseError('available_between period must be an integer.')
            return self._filter_available_between_with_period(
                queryset, overlapping_reservations, available_start, available_end, period
            )

    def _filter_available_between_whole_range(self, queryset, reservations, available_start, available_end):
        # exclude resources that have reservation(s) overlapping with the available_between range
        queryset = queryset.exclude(reservations__in=reservations)
        closed_resource_ids = {
            resource.id
            for resource in queryset
            if not self._is_resource_open(resource, available_start, available_end)
        }

        return queryset.exclude(id__in=closed_resource_ids)

    @staticmethod
    def _is_resource_open(resource, start, end):
        opening_hours = resource.get_opening_hours(start, end)
        if len(opening_hours) > 1:
            # range spans over multiple days, assume resources aren't open all night and skip the resource
            return False

        hours = next(iter(opening_hours.values()))[0]  # assume there is only one hours obj per day
        if not hours['opens'] and not hours['closes']:
            return False

        start_too_early = hours['opens'] and start < hours['opens']
        end_too_late = hours['closes'] and end > hours['closes']
        if start_too_early or end_too_late:
            return False

        return True

    def _filter_available_between_with_period(self, queryset, reservations, available_start, available_end, period):
        reservations = reservations.order_by('begin').select_related('resource')

        reservations_by_resource = collections.defaultdict(list)
        for reservation in reservations:
            reservations_by_resource[reservation.resource_id].append(reservation)

        available_resources = set()

        hours_qs = ResourceDailyOpeningHours.objects.filter(
            open_between__overlap=(available_start, available_end, '[)'))

        # check the resources one by one to determine which ones have open slots
        for resource in queryset.prefetch_related(None).prefetch_related(
                Prefetch('opening_hours', queryset=hours_qs, to_attr='prefetched_opening_hours')):
            reservations = reservations_by_resource[resource.id]

            if self._is_resource_available(resource, available_start, available_end, reservations, period):
                available_resources.add(resource.id)

        return queryset.filter(id__in=available_resources)

    @staticmethod
    def _is_resource_available(resource, available_start, available_end, reservations, period):
        opening_hours = resource.get_opening_hours(available_start, available_end, resource.prefetched_opening_hours)
        hours = next(iter(opening_hours.values()))[0]  # assume there is only one hours obj per day

        if not (hours['opens'] or hours['closes']):
            return False

        current = max(available_start, hours['opens']) if hours['opens'] is not None else available_start
        end = min(available_end, hours['closes']) if hours['closes'] is not None else available_end

        if current >= end:
            # the resource is already closed
            return False

        if not reservations:
            # the resource has no reservations, just check if the period fits in the resource's opening times
            if end - current >= period:
                return True
            return False

        # try to find an open slot between reservations and opening / closing times.
        # start from period start time or opening time depending on which one is earlier.
        for reservation in reservations:
            if reservation.end <= current:
                # this reservation is in the past
                continue
            if reservation.begin - current >= period:
                # found an open slot before the reservation currently being examined
                return True
            if reservation.end > end:
                # the reservation currently being examined ends after the period or closing time,
                # so no free slots
                return False
            # did not find an open slot before the reservation currently being examined,
            # proceed to next reservation
            current = reservation.end
        else:
            # all reservations checked and no free slot found, check if there is a free slot after the last
            # reservation
            if end - reservation.end >= period:
                return True

        return False

    class Meta:
        model = Resource
        fields = ['purpose', 'type', 'people', 'need_manual_confirmation', 'is_favorite', 'unit', 'available_between', 'min_price']


class ResourceFilterBackend(filters.BaseFilterBackend):
    """
    Make request user available in the filter set.
    """

    def filter_queryset(self, request, queryset, view):
        accessibility_filtering = request.query_params.get('order_by', None) == 'accessibility'
        viewpoint_defined = 'accessibility_viewpoint' in request.query_params
        if accessibility_filtering and not viewpoint_defined:
            error_message = "'accessibility_viewpoint' must be defined when ordering by accessibility"
            raise exceptions.ParseError(error_message)

        return ResourceFilterSet(request.query_params, queryset=queryset, user=request.user).qs


class LocationFilterBackend(filters.BaseFilterBackend):
    """
    Filters based on resource (or resource unit) location.
    """

    def filter_queryset(self, request, queryset, view):
        query_params = request.query_params
        if 'lat' not in query_params and 'lon' not in query_params:
            return queryset

        try:
            lat = float(query_params['lat'])
            lon = float(query_params['lon'])
        except ValueError:
            raise exceptions.ParseError("'lat' and 'lon' need to be floating point numbers")
        point = Point(lon, lat, srid=4326)
        queryset = queryset.annotate(distance=Distance('location', point))
        queryset = queryset.annotate(unit_distance=Distance('unit__location', point))
        queryset = queryset.order_by('distance', 'unit_distance')

        if 'distance' in query_params:
            try:
                distance = float(query_params['distance'])
                if not distance > 0:
                    raise ValueError()
            except ValueError:
                raise exceptions.ParseError("'distance' needs to be a floating point number")
            q = Q(location__distance_lte=(point, distance)) | Q(unit__location__distance_lte=(point, distance))
            queryset = queryset.filter(q)
        return queryset

class ResourceCacheMixin:
    def _preload_opening_hours(self, times):
        # We have to evaluate the query here to make sure all the
        # resources are on the same timezone. In case of different
        # time zones, we skip this optimization.
        time_zone = None
        hours_by_resource = {}
        for resource in self._page:
            if time_zone:
                if resource.unit.time_zone != time_zone:
                    return None
            else:
                time_zone = resource.unit.time_zone
            hours_by_resource[resource.id] = []
        if not time_zone:
            return None

        begin, end = determine_hours_time_range(times.get('start'), times.get('end'), pytz.timezone(time_zone))
        hours = ResourceDailyOpeningHours.objects.filter(
            resource__in=self._page, open_between__overlap=(begin, end, '[)')
        )
        for obj in hours:
            hours_by_resource[obj.resource_id].append(obj)
        return hours_by_resource

    def _preload_reservations(self, times):
        qs = get_resource_reservations_queryset(times['start'], times['end'])
        reservations = qs.filter(resource__in=self._page)
        reservations_by_resource = {}
        for rv in reservations:
            rv_list = reservations_by_resource.setdefault(rv.resource_id, [])
            rv_list.append(rv)
        return reservations_by_resource

    def _preload_permissions(self):
        units = set()
        resource_groups = set()
        checker = ObjectPermissionChecker(self.request.user)
        for res in self._page:
            units.add(res.unit)
            for g in res.groups.all():
                resource_groups.add(g)
            res._permission_checker = checker

        if units:
            checker.prefetch_perms(units)
        if resource_groups:
            checker.prefetch_perms(resource_groups)

    def _get_cache_context(self):
        context = {}

        equipment_list = Equipment.objects.filter(resource_equipment__resource__in=self._page).distinct().\
            select_related('category').prefetch_related('aliases')
        equipment_cache = {x.id: x for x in equipment_list}

        context['equipment_cache'] = equipment_cache
        set_list = ReservationMetadataSet.objects.all().prefetch_related('supported_fields', 'required_fields')
        context['reservation_metadata_set_cache'] = {x.id: x for x in set_list}

        home_municipality_set_list = ReservationHomeMunicipalitySet.objects.all().prefetch_related('included_municipalities')
        context['reservation_home_municipality_set_cache'] = {x.id: x for x in home_municipality_set_list}

        times = parse_query_time_range(self.request.query_params)
        if times:
            context['reservations_cache'] = self._preload_reservations(times)
        context['opening_hours_cache'] = self._preload_opening_hours(times)

        context['accessibility_viewpoint_cache'] = AccessibilityViewpoint.objects.all()

        self._preload_permissions()

        return context

class ResourceCreateProductSerializer(serializers.ModelSerializer):
    id = serializers.CharField(required=False)
    type = serializers.ChoiceField(choices=Product.TYPE_CHOICES, required=False)
    sku = serializers.CharField(required=False)
    sap_code = serializers.CharField(required=False)
    sap_unit = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False)

    price = serializers.DecimalField(required=False, max_digits=10, decimal_places=2)
    tax_percentage = serializers.DecimalField(required=False, max_digits=5, decimal_places=2)

    price_type = serializers.ChoiceField(choices=Product.PRICE_TYPE_CHOICES, required=False)
    price_period = serializers.DurationField(required=False)
    max_quantity = serializers.IntegerField(required=False)

    class Meta:
        model = Product
        exclude = ('resources', )

    def validate(self, attrs):
        if not Resource.objects.filter(pk=self.context['pk']).exists():
            raise serializers.ValidationError({
                'product': {
                    'resource': [_('Not found.')]
                }
            })
        return super().validate(attrs)
    
    def create(self, validated_data):
        instance = None
        if 'id' in validated_data:
            try:
                instance = self.Meta.model.objects.get(product_id=validated_data['id'])
            except ObjectDoesNotExist:
                raise serializers.ValidationError({
                    'product': [_('Invalid id provided.')]
                })
            validated_data['product_id'] = validated_data.pop('id')

        if instance:
            if instance.resources.filter(id=self.context['pk']).exists():
                raise serializers.ValidationError({
                    'product': [_('This resource is already part of this product.')]
                })
            instance.resources.add(self.context['pk'])
            return instance
        
        validated_data['resources'] = [self.context['pk']]
        return super().create(validated_data) 

    def to_representation(self, instance):
        obj = super().to_representation(instance)
        del obj['id']
        return obj

class ResourceCreateProductView(generics.CreateAPIView):
    queryset = Resource.objects.select_related(
        'generic_terms', 'payment_terms', 
        'unit', 'type', 'reservation_metadata_set'
        )
    serializer_class = ResourceCreateProductSerializer
    permission_classes = (permissions.DjangoModelPermissions, )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['pk'] = self.kwargs['pk']
        return context

class ResourceTagSerializer(serializers.ModelSerializer):
    new_label = serializers.CharField(required=False)

    class Meta:
        model = ResourceTag
        fields = ( 'label', 'new_label', )

    def create(self, validated_data):
        if 'new_label' in validated_data:
            del validated_data['new_label']
        return super().create(validated_data)
        
    
    def update(self, resource, validated_data):
        try:
            instance = self.Meta.model.objects.get(resource=resource, label=validated_data['label'])
        except ObjectDoesNotExist:
            instance = self.create(validated_data)

        if 'new_label' in validated_data:
            validated_data['label'] = validated_data.pop('new_label')

        return super().update(instance, validated_data)


class MetadataSetSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False)
    supported_fields = serializers.ListField(required=False, write_only=True, 
            help_text='Options: \n%s' % '\n'.join(ReservationMetadataSet.get_supported_fields()))
    required_fields = serializers.ListField(required=False,  write_only=True,
            help_text='Options: \n%s' % '\n'.join(ReservationMetadataSet.get_supported_fields()))
    remove_fields = serializers.DictField(
                            child=serializers.ListField(
                                required=False, write_only=True, 
                                    child=serializers.CharField(required=True)),
                    required=False, write_only=True, allow_empty=True,
            help_text='Example: "remove_fields: { "supported_fields": [ %(example)s ] }"' % ({
                'example': ', '.join(
                    "\"%s\"" % x for x in ReservationMetadataSet.get_example())
                }))

    class Meta:
        model = ReservationMetadataSet
        exclude = (
            'id',
            'created_at', 'modified_at', 
            'created_by', 'modified_by'
        )
        list_fields = (
            'required_fields', 
            'supported_fields'
        )
        schema = {
            "type": "object",
            "properties": {
                "remove_fields": {
                    "type": "object",
                    "properties": {
                        "supported_fields": { "type": "array", "items": [{"type": "string"}], "minItems": 1 },
                        "required_fields": { "type": "array", "items": [{"type": "string"}], "minItems": 1  }
                    },
                    "required": [ "supported_fields", ]
                }
            },
            "required": [ "remove_fields" ]
        }
    
    def validate(self, attrs):
        request = self.context['request']
        supported_fields = attrs.pop('supported_fields', [])
        required_fields = attrs.pop('required_fields', [])
        remove_fields = attrs.pop('remove_fields', fields.empty)

        name = attrs.get('name', None)

        if request.method == 'POST':
            if not name:
                raise serializers.ValidationError({
                    'name':[_('This field is required.')]
                })
            try:
                self.Meta.model.objects.get(name=attrs['name'])
                raise serializers.ValidationError({
                    'name': [_('Metadata set with this name already exists.')]
                })
            except (ObjectDoesNotExist, serializers.ValidationError) as exc:
                if isinstance(exc, serializers.ValidationError):
                    raise

        if remove_fields != fields.empty:
            try:
                json.validate({'remove_fields': remove_fields}, self.Meta.schema)
            except Exception as exc:
                raise serializers.ValidationError({
                    'remove_fields': 'Invalid schema.',
                    'schema': self.Meta.schema
                }) from exc
        
        if not supported_fields:
            raise serializers.ValidationError({
                'supported_fields': [_('This field is required.')]
            })

        if not supported_fields:
            raise serializers.ValidationError({
                'supported_fields': [_('This field is required.')]
            })

        supported_fields = ReservationMetadataField.objects.filter(field_name__in=supported_fields)

        if not supported_fields.exists():
            raise serializers.ValidationError({
                'supported_fields': [_('Atleast one invalid option was given.')]
            })

        attrs['supported_fields'] = supported_fields
    
        if required_fields:
            required_fields = ReservationMetadataField.objects.filter(field_name__in=required_fields)
            if not required_fields.exists():
                raise serializers.ValidationError({
                    'required_fields': [_('Atleast one invalid option was given.'),]
                })
            attrs['required_fields'] = required_fields

        attrs['remove_fields'] = remove_fields
        return super().validate(attrs)

    def create(self, validated_data):
        if 'remove_fields' in validated_data:
            del validated_data['remove_fields'] 
        try:
            instance = super().create(validated_data)
        except Exception as exc:
            logger.error("Error while creating metadata set through api: %s", exc)
            raise serializers.ValidationError(
                {'error': [_("Something went wrong.")]}
            ) from exc
        return instance

    def update(self, resource, validated_data):
        remove_fields = validated_data.pop('remove_fields', {})
        if not isinstance(resource, Resource):
            raise TypeError("Invalid type: %s passed to %s" % (type(resource), str(self.__class__.__name__)))
        try:
            instance = self.Meta.model.objects.get(resource=resource)
        except ObjectDoesNotExist:
            instance = self.create(validated_data)
            resource.reservation_metadata_set = instance

        for field, value in (
            ('supported_fields', validated_data.pop('supported_fields', [])),
            ('required_fields', validated_data.pop('required_fields', [])),
        ):
            for field_name in value:
                if instance.filter(field, field_name).exists():
                    continue
                instance.add(field, field_name)

        if remove_fields != fields.empty:
            for field, value in (
                ('supported_fields', remove_fields.pop('supported_fields', [])),
                ('required_fields', remove_fields.pop('required_fields', [])),
            ):
                for field_name in value:
                    if instance.filter(field, field_name).exists():
                        instance.remove(field, field_name)

        return super().update(instance, validated_data)

class ReservationHomeMunicipalitySetSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=True)
    municipalities = serializers.ListField(required=True, write_only=True, 
    help_text='Options: \n%s' % '\n'.join(ReservationHomeMunicipalitySet.get_supported_fields()))
    remove_fields = serializers.DictField(
                            child=serializers.ListField(
                                required=False, write_only=True, 
                                    child=serializers.CharField(required=True)),
                    required=False, write_only=True, allow_empty=True,
                    help_text='Example: "remove_fields: { "municipalities": [ %(example)s ] }"' % ({
                'example': ', '.join(
                    "\"%s\"" % x for x in ReservationHomeMunicipalitySet.get_example())
                }))

    class Meta:
        model = ReservationHomeMunicipalitySet
        exclude = ('id', 'included_municipalities', 'created_at', 'modified_at', )
        list_fields = ('municipalities',)
        schema = {
            "type": "object",
            "properties": {
                "remove_fields": {
                    "type": "object",
                    "properties": {
                        "municipalities": { "type": "array", "items": [{"type": "string"}], "minItems": 1 },
                    },
                    "required": [ "municipalities", ]
                }
            },
            "minItems": 1,
            "required": [ "remove_fields" ]
        }

    def validate(self, attrs):
        request = self.context['request']
        municipalities = attrs.pop('municipalities', [])
        remove_fields = attrs.pop('remove_fields', fields.empty)

        if remove_fields != fields.empty:
            try:
                json.validate({'remove_fields': remove_fields}, self.Meta.schema)
            except Exception as exc:
                raise serializers.ValidationError({
                    'remove_fields': 'Invalid schema.',
                    'schema': self.Meta.schema
                }) from exc
        name = attrs.get('name', None)
        if request.method == 'POST':
            if not name:
                raise serializers.ValidationError({
                    'name':[_('This field is required.')]
                })
            try:
                self.Meta.model.objects.get(name=attrs['name'])
                raise serializers.ValidationError({
                    'name': [_('Home Municipality set with this name already exists.')]
                })
            except (ObjectDoesNotExist, serializers.ValidationError) as exc:
                if isinstance(exc, serializers.ValidationError):
                    raise

        municipalities = ReservationHomeMunicipalityField.objects.filter(name__in=municipalities)
        if not municipalities.exists():
            raise serializers.ValidationError({
                'municipalities':[_('Atleast one invalid option was given.')]
            })
    
        attrs['municipalities'] = municipalities
        attrs['remove_fields'] = remove_fields
        return attrs

    def create(self, validated_data):
        if 'remove_fields' in validated_data:
            del validated_data['remove_fields']

        validated_data['included_municipalities'] = validated_data.pop('municipalities')

        return super().create(validated_data)

    def update(self, resource, validated_data):
        remove_fields = validated_data.pop('remove_fields', {})

        if not isinstance(resource, Resource):
            raise TypeError("Invalid type: %s passed to %s" % (type(resource), str(self.__class__.__name__)))

        try:
            instance = self.Meta.model.objects.get(home_municipality_included_set=resource)
        except ObjectDoesNotExist:
            instance = self.create(validated_data)
            resource.reservation_home_municipality_set = instance

        for municipality in validated_data.pop('municipalities', []):
            if instance.filter(municipality).exists():
                continue
            instance.add(municipality)

        if remove_fields != fields.empty:
            for municipality in remove_fields.pop('municipalities', []):
                if instance.filter(municipality).exists():
                    instance.remove(municipality)

        return super().update(instance, validated_data)

class ResourceCreateSerializer(TranslatedModelSerializer):
    id = serializers.CharField(required=False)
    public = serializers.BooleanField(required=True)
    name = serializers.DictField(required=True)
    description = serializers.DictField(required=True)
    responsible_contact_info = serializers.DictField(
        required=False,
        help_text=get_translated_field_help_text('responsible_contact_info')
    )
    specific_terms = serializers.DictField(
        required=False,
        help_text=get_translated_field_help_text('specific_terms')
    )
    need_manual_confirmation = serializers.BooleanField(required=True)
    authentication = serializers.ChoiceField(choices=Resource.AUTHENTICATION_TYPES, required=True)
    people_capacity = serializers.IntegerField(required=True)
    min_period = serializers.DurationField(required=True)
    max_period = serializers.DurationField(required=True)
    slot_size = serializers.DurationField(required=True)
    reservation_info = serializers.DictField(required=True)

    reservation_confirmed_notification_extra = serializers.DictField(required=False)
    reservation_requested_notification_extra = serializers.DictField(required=False)
    reservation_additional_information = serializers.DictField(required=False)

    resource_staff_emails = ResourceStaffEmailsField(required=False)

    terms_of_use = TermsOfUseSerializer(required=True, many=True)
    tags = ResourceTagSerializer(required=False, many=True)
    periods  = PeriodSerializer(required=False, many=True)
    images = ResourceImageSerializer(required=True, allow_empty=False, many=True)
    reservation_metadata_set = MetadataSetSerializer(required=False)
    reservation_home_municipality_set = ReservationHomeMunicipalitySetSerializer(required=False)

    location = LocationField(required=False, help_text='example: {"type": "Point", "coordinates": [22.00000, 60.0000]}')

    class Meta:
        model = Resource
        exclude = (
            'resource_email', 'configuration',
            'created_at', 'modified_at',
            'modified_by', 'created_by',
            'generic_terms', 'payment_terms'
        )
        required_translations = (
            'name_fi', 'name_sv', 'name_en'
            'description_fi', 'description_sv', 'description_en',
            'reservation_info_fi', 'reservation_info_sv', 'reservation_info_en',
            'responsible_contact_info_fi',
            'specific_terms_fi', 'specific_terms_en', 'specific_terms_sv',
            'reservation_confirmed_notification_extra_fi',
            'reservation_confirmed_notification_extra_en',
            'reservation_confirmed_notification_extra_sv',
            'reservation_requested_notification_extra_fi',
            'reservation_requested_notification_extra_en',
            'reservation_requested_notification_extra_sv',
            'reservation_additional_information_fi', 
            'reservation_additional_information_en', 
            'reservation_additional_information_sv'

            )
        extra_serializers = {
            'images': ResourceImageSerializer,
            'tags': ResourceTagSerializer,
            'periods': PeriodSerializer,
            'terms_of_use': TermsOfUseSerializer,
            'reservation_metadata_set': MetadataSetSerializer,
            'reservation_home_municipality_set': ReservationHomeMunicipalitySetSerializer
        }

    def validate(self, attrs):
        request = self.context['request']
        unit = attrs.get('unit', None)
        if not unit and request.method == 'POST':
            raise serializers.ValidationError({
                'unit': [_('This field is required.')]
            })
        resource = None
        try:
            if attrs.get('id', 0):
                resource = Resource.objects.get(pk=attrs['id'])
        except ObjectDoesNotExist:
            pass
        if resource:
            raise serializers.ValidationError({
                'id': [_('This resource already exists.')]
            })
        return super().validate(attrs)
    
    def create(self, validated_data):
        return self.create_or_update(validated_data)

    def get_tags(self, resource):
        return [ tag.label for tag in ResourceTag.objects.filter(resource=resource) ]

    def to_representation(self, obj):
        data = ResourceSerializer(context=self.context).to_representation(obj)
        data['tags'] = self.get_tags(obj)
        return data

    def create_or_update(self, validated_data, _instance=None):
        extra = (
            ('images', 
                {'kwargs': { 'many': True, 'context': self.context, 'data': validated_data.pop('images', {}), },
                    'validate': ( (lambda data: len(data) <= 5, _('Invalid length, max: 5')), ),
                    'save_kw': { 'resource_fk': True, }, } ),

            ('tags',
                {'kwargs': {'many': True, 'context': self.context, 'data': validated_data.pop('tags', []), },
                    'validate': ( (lambda data: len(data) <= 20,  _('Invalid length, max: 20')), ),
                    'save_kw': { 'resource_fk': True }, } ),

            ('periods', 
                { 'kwargs': { 'many': True, 'context': self.context, 'data': validated_data.pop('periods', {}), },
                    'validate': ( (lambda data: len(data) <= 10,  _('Invalid length, max: 10')), ),
                    'save_kw': { 'resource_fk': True }, } ),

            ('terms_of_use', 
                { 'kwargs': { 'many': True, 'context': self.context, 'data': validated_data.pop('terms_of_use', []), },
                    'validate': ( (lambda data: len(data) <= 2,  _('Invalid length, max: 2')), ),
                    'perform': ( lambda instance, serializer: setattr(instance, serializer.terms_type, serializer), ), } ),

            ('reservation_metadata_set',
                { 'kwargs': { 'data': validated_data.pop('reservation_metadata_set', {}), 'context': self.context, },
                    'perform': ( lambda instance, serializer: setattr(instance, 'reservation_metadata_set', serializer), ), } ),

            ('reservation_home_municipality_set', 
                { 'kwargs': { 'data': validated_data.pop('reservation_home_municipality_set', {}), 'context': self.context, },
                    'perform': ( lambda instance, serializer: setattr(instance, 'reservation_home_municipality_set', serializer), ), } ),
        )

        if _instance:
            instance = super().update(_instance, validated_data)
        else:
            instance = super().create(validated_data)

        if instance.timmi_resource and not instance.timmi_room_id:
            try:
                TimmiManager().get_room_part_id(instance)
            except ValidationError as exc:
                raise serializers.ValidationError(exc.message_dict) from exc

        for field in extra:
            name, data = field

            actions = data.pop('perform', [])
            kwargs = data.pop('kwargs', {})
            save_kw = data.pop('save_kw', {})
            validate = data.pop('validate', [])

            if _instance:
                kwargs['instance'] = instance

            serializer = self.get_extra_serializer(name, validate=validate, **kwargs)
            if not serializer:
                continue

            if isinstance(serializer, list):
                for ser in serializer:
                    ser.is_valid(raise_exception=True)
                    if save_kw.get('resource_fk', False):
                        ser = ser.save(resource=instance)
                    else:
                        ser = ser.save()
                    for action in actions:
                        action(instance, ser)
                continue

            serializer.is_valid(raise_exception=True)

            if save_kw.get('resource', False):
                serializer = serializer.save(resource=instance)
            else:
                serializer = serializer.save()

            for action in actions:
                action(instance, serializer)

        instance.save()
        return instance

    def get_extra_serializer(self, name, **kwargs):
        if not kwargs.get('data', None):
            return None
        validations = kwargs.pop('validate', [])

        for validate, message in validations:
            if not validate(kwargs['data']):
                raise serializers.ValidationError({
                    'error': [_('%s failed validation.' % name)],
                    'message': [message],
                    'length': len(kwargs['data'])
                })

        serializer = self.Meta.extra_serializers.get(name, None)
        if not serializer or \
            not kwargs.get('data', None):
            return None
        if kwargs.get('many', False):
            datas = kwargs.pop('data', [])
            del kwargs['many']
            return [serializer(data=data, **kwargs) for data in datas]

        return serializer(**kwargs)



class ResourceUpdateSerializer(ResourceCreateSerializer):
    id = serializers.CharField(read_only=True)
    terms_of_use = TermsOfUseSerializer(required=False, many=True)
    tags = ResourceTagSerializer(required=False, many=True)
    periods  = PeriodSerializer(required=False, many=True)
    images = ResourceImageSerializer(required=False, allow_empty=False, many=True)
    reservation_metadata_set = MetadataSetSerializer(required=False)
    reservation_home_municipality_set = ReservationHomeMunicipalitySetSerializer(required=False)
    location = LocationField(required=False, help_text='example: {"type": "Point", "coordinates": [22.00000, 60.0000]}')

    authentication = serializers.ChoiceField(choices=Resource.AUTHENTICATION_TYPES, required=False)
    description = serializers.DictField(required=False)
    min_period = serializers.DurationField(required=False)
    max_period = serializers.DurationField(required=False)
    name = serializers.DictField(required=False)
    need_manual_confirmation = serializers.BooleanField(required=False)
    people_capacity = serializers.IntegerField(required=False)
    public = serializers.BooleanField(required=False)
    slot_size = serializers.DurationField(required=False)
    reservation_info = serializers.DictField(required=False)

    unit = serializers.PrimaryKeyRelatedField(required=False, queryset=Unit.objects.all())
    purposes = serializers.PrimaryKeyRelatedField(required=False, many=True, queryset=Purpose.objects.all())
    type = serializers.PrimaryKeyRelatedField(required=False, queryset=ResourceType.objects.all())
    
    def validate(self, attrs):
        request = self.context['request']

        if 'periods' in attrs:
            for period in attrs['periods']:
                if not 'id' in period and \
                    request.method in ('PUT', 'PATCH'):
                    raise serializers.ValidationError({
                        'period': [_('id is required when updating periods.')]
                    })

        return super().validate(attrs)

    def update(self, instance, validated_data):
        return self.create_or_update(validated_data, _instance=instance)
    

class ResourceCreateView(generics.CreateAPIView):
    queryset = Resource.objects.select_related(
        'generic_terms', 'payment_terms', 
        'unit', 'type', 'reservation_metadata_set'
        )
    serializer_class = ResourceCreateSerializer
    permission_classes = (permissions.DjangoModelPermissions, )

class ResourceUpdateView(generics.UpdateAPIView):
    queryset = Resource.objects.select_related(
        'generic_terms', 'payment_terms', 
        'unit', 'type', 'reservation_metadata_set'
        )
    serializer_class = ResourceUpdateSerializer
    permission_classes = (permissions.DjangoModelPermissions, )


class ResourceListViewSet(munigeo_api.GeoModelAPIView, mixins.ListModelMixin,
                          viewsets.GenericViewSet, ResourceCacheMixin):
    queryset = Resource.objects.select_related('generic_terms', 'payment_terms', 'unit', 'type', 'reservation_metadata_set')
    queryset = queryset.prefetch_related('favorited_by', 'resource_equipment', 'resource_equipment__equipment',
                                         'purposes', 'images', 'purposes', 'groups', 'resource_tags')
    if settings.RESPA_PAYMENTS_ENABLED:
        queryset = queryset.prefetch_related('products')
    filter_backends = (filters.SearchFilter, ResourceFilterBackend, LocationFilterBackend)
    search_fields = (
                    'name_fi', 'description_fi', 'unit__name_fi', 'type__name_fi',
                    'name_sv', 'description_sv', 'unit__name_sv', 'type__name_sv',
                    'name_en', 'description_en', 'unit__name_en', 'type__name_en', '=resource_tags__label'
                    )

    serializer_class = ResourceSerializer
    authentication_classes = (
        list(drf_settings.DEFAULT_AUTHENTICATION_CLASSES) +
        [SessionAuthentication])

    def get_serializer_class(self):
        if settings.RESPA_PAYMENTS_ENABLED:
            from payments.api.resource import PaymentsResourceSerializer  # noqa
            return PaymentsResourceSerializer
        else:
            return ResourceSerializer

    def get_serializer(self, page, *args, **kwargs):
        self._page = page
        return super().get_serializer(page, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update(self._get_cache_context())

        request_user = self.request.user
        if request_user.is_authenticated:
            prefetched_user = get_user_model().objects.prefetch_related('unit_authorizations', 'unit_group_authorizations__subject__members').\
                get(pk=request_user.pk)

            context['prefetched_user'] = prefetched_user

        return context

    def get_queryset(self):
        return self.queryset.visible_for(self.request.user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return response


class ResourceViewSet(munigeo_api.GeoModelAPIView, mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet, ResourceCacheMixin):
    queryset = ResourceListViewSet.queryset
    authentication_classes = (
        list(drf_settings.DEFAULT_AUTHENTICATION_CLASSES) +
        [SessionAuthentication] +
        ([TokenAuthentication] if settings.ENABLE_RESOURCE_TOKEN_AUTH else []))

    def get_serializer_class(self):
        if settings.RESPA_PAYMENTS_ENABLED:
            from payments.api.resource import PaymentsResourceDetailsSerializer  # noqa
            return PaymentsResourceDetailsSerializer
        else:
            return ResourceDetailsSerializer

    def get_serializer(self, page, *args, **kwargs):
        self._page = [page]
        return super().get_serializer(page, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update(self._get_cache_context())

        request_user = self.request.user
        if request_user.is_authenticated:
            prefetched_user = get_user_model().objects.prefetch_related('unit_authorizations', 'unit_group_authorizations__subject__members').\
                get(pk=request_user.pk)

            context['prefetched_user'] = prefetched_user

        return context

    def get_queryset(self):
        return self.queryset.visible_for(self.request.user)

    def _set_favorite(self, request, value):
        resource = self.get_object()
        user = request.user

        exists = user.favorite_resources.filter(id=resource.id).exists()
        if value:
            if not exists:
                user.favorite_resources.add(resource)
                return response.Response(status=status.HTTP_201_CREATED)
            else:
                return response.Response(status=status.HTTP_304_NOT_MODIFIED)
        else:
            if exists:
                user.favorite_resources.remove(resource)
                return response.Response(status=status.HTTP_204_NO_CONTENT)
            else:
                return response.Response(status=status.HTTP_304_NOT_MODIFIED)

    @action(detail=True, methods=['post'])
    def favorite(self, request, pk=None):
        return self._set_favorite(request, True)

    @action(detail=True, methods=['post'])
    def unfavorite(self, request, pk=None):
        return self._set_favorite(request, False)
    
    def retrieve(self, request, *args, **kwargs):
        from resources.timmi import TimmiManager
        resource = self.get_object()
        response = super().retrieve(request, *args, **kwargs)
        if resource.timmi_resource:
            timmi = TimmiManager(request=request)
            try:
                response = timmi.bind(resource, response)
            except:
                return Response({'message': 'Timmi connection failed'}, status=404)
        return response


register_view(ResourceListViewSet, 'resource')
register_view(ResourceViewSet, 'resource')
