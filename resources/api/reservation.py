import uuid
import arrow
import django_filters
from arrow.parser import ParserError
from django.conf import settings
from guardian.core import ObjectPermissionChecker
from django.contrib.auth import get_user_model
from django.conf import settings
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import (
    PermissionDenied, ValidationError as DjangoValidationError
)
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.models import AnonymousUser
from notifications.models import NotificationType
from rest_framework import viewsets, serializers, filters, exceptions, permissions
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.fields import BooleanField, IntegerField
from rest_framework import renderers
from rest_framework.exceptions import NotAcceptable, ValidationError
from rest_framework.settings import api_settings as drf_settings

from munigeo import api as munigeo_api

import phonenumbers
from phonenumbers.phonenumberutil import (
    region_code_for_country_code
)
from payments.models import Order


from resources.models import (
    Reservation, Resource, ReservationMetadataSet,
    ReservationHomeMunicipalityField, ReservationBulk, Unit
)
from resources.models.reservation import RESERVATION_BILLING_FIELDS, RESERVATION_EXTRA_FIELDS
from resources.models.utils import build_reservations_ical_file
from resources.pagination import ReservationPagination
from resources.models.utils import generate_reservation_xlsx, get_object_or_none

from ..auth import is_general_admin, is_underage, is_overage, is_authenticated_user, is_any_admin, is_any_manager
from .base import (
    NullableDateTimeField, TranslatedModelSerializer, register_view, DRFFilterBooleanWidget,
    ExtraDataMixin
)

from ..models.utils import dateparser, is_reservation_metadata_or_times_different
from respa.renderers import ResourcesBrowsableAPIRenderer
from payments.utils import is_free, get_price

from maintenance.models import MaintenanceMode

User = get_user_model()

# FIXME: Make this configurable?
USER_ID_ATTRIBUTE = 'id'
try:
    User._meta.get_field('uuid')
    USER_ID_ATTRIBUTE = 'uuid'
except Exception:
    pass


class UserSerializer(TranslatedModelSerializer):
    display_name = serializers.ReadOnlyField(source='get_display_name')
    email = serializers.ReadOnlyField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if USER_ID_ATTRIBUTE == 'id':
            # id field is read_only by default, that needs to be changed
            # so that the field will be validated
            self.fields['id'] = IntegerField(label='ID')
        else:
            # if the user id attribute isn't id, modify the id field to point to the right attribute.
            # the field needs to be of the right type so that validation works correctly
            model_field_type = type(get_user_model()._meta.get_field(USER_ID_ATTRIBUTE))
            serializer_field = self.serializer_field_mapping[model_field_type]
            self.fields['id'] = serializer_field(source=USER_ID_ATTRIBUTE, label='ID')

    class Meta:
        model = get_user_model()
        fields = ('id', 'display_name', 'email')
        ref_name = 'ReservationUserSerializer'


class ReservationBulkSerializer(ExtraDataMixin, TranslatedModelSerializer):
    bucket = serializers.SerializerMethodField()

    class Meta:
        model = ReservationBulk
        fields = [
            'bucket'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_bucket(self, obj):
        data = []
        for res in obj.bucket.all():
            data.append(
                (res.begin, res.end)
            )


class HomeMunicipalitySerializer(TranslatedModelSerializer):
    class Meta:
        model = ReservationHomeMunicipalityField
        fields = ('id', 'name')
        ref_name = 'ReservationHomeMunicipalitySerializer'

    def to_internal_value(self, data):
        # if string or dict is given, try to use its id and convert the id to correct home municipality object
        if isinstance(data, str) or isinstance(data, dict):
            home_municipality = None

            if isinstance(data, str):
                home_municipality = get_object_or_none(ReservationHomeMunicipalityField, id=data)

            # if dict and key id exists
            if isinstance(data, dict):
                if "id" in data:
                    home_municipality = get_object_or_none(ReservationHomeMunicipalityField, id=data['id'])
                else:
                    raise ValidationError(_('Invalid home municipality object - id is missing.'))

            if not home_municipality:
                raise ValidationError({
                    'home_municipality': {
                        'id': [_('Invalid pk "{pk_value}" - object does not exist.').format(pk_value=data)]
                    }
                })
            data = home_municipality
            return data
        else:
            return super().to_internal_value(data)


class ReservationSerializer(ExtraDataMixin, TranslatedModelSerializer, munigeo_api.GeoModelSerializer):
    begin = NullableDateTimeField()
    end = NullableDateTimeField()
    user = UserSerializer(required=False)
    is_own = serializers.SerializerMethodField()
    state = serializers.ChoiceField(choices=Reservation.STATE_CHOICES, required=False)
    need_manual_confirmation = serializers.ReadOnlyField()
    user_permissions = serializers.SerializerMethodField()
    preferred_language = serializers.ChoiceField(choices=settings.LANGUAGES, required=False)
    home_municipality = HomeMunicipalitySerializer(required=False)

    class Meta:
        model = Reservation
        fields = [
            'url', 'id', 'resource', 'user', 'begin', 'end', 'comments', 'is_own', 'state',
            'need_manual_confirmation', 'require_assistance', 'require_workstation', 'private_event',
            'staff_event', 'access_code', 'user_permissions', 'preferred_language', 'type',
            'has_arrived', 'takes_place_virtually', 'virtual_address', 'universal_data'
        ] + list(RESERVATION_EXTRA_FIELDS)
        read_only_fields = list(RESERVATION_EXTRA_FIELDS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        data = self.get_initial()
        resource = None
        request = self.context['request']

        # try to find out the related resource using initial data if that is given
        resource_id = data.get('resource') if data else None
        if resource_id:
            resource = get_object_or_none(Resource, id=resource_id)

        # if that didn't work out use the reservation's old resource if such exists
        if not resource:
            if isinstance(self.instance, Reservation) and isinstance(self.instance.resource, Resource):
                resource = self.instance.resource

        # set supported and required extra fields
        if resource:
            cache = self.context.get('reservation_metadata_set_cache')
            supported = resource.get_supported_reservation_extra_field_names(cache=cache)
            required = resource.get_required_reservation_extra_field_names(cache=cache)

            # reservations without an order don't require billing fields
            self.handle_reservation_modify_request(request, resource)
            order = request.data.get('order')

            begin, end = (request.data.get('begin', None), request.data.get('end', None))
            if not order or isinstance(order, str) or (order and is_free(get_price(order, begin=begin, end=end))):
                required = [field for field in required if field not in RESERVATION_BILLING_FIELDS]

            # staff events have less requirements
            is_staff_event = data.get('staff_event', False)

            if is_staff_event and resource.can_create_staff_event(request.user):
                required = {'reserver_name', 'event_description'}

            # reservations of type blocked don't require any fields
            is_blocked_type = data.get('type') == Reservation.TYPE_BLOCKED
            if is_blocked_type and resource.can_create_special_type_reservation(request.user):
                required = []

            # we don't need to remove a field here if it isn't supported, as it will be read-only and will be more
            # easily removed in to_representation()
            for field_name in supported:
                self.fields[field_name].read_only = False

            for field_name in required:
                self.fields[field_name].required = True

        self.context.update({'resource': resource})

    def handle_reservation_modify_request(self, request, resource):
        # handle removing order from data when updating reservation without paying
        if self.instance and resource.has_products() and 'order' in request.data:
            state = request.data.get('state')
            # states where reservation updates can be made
            if state in (
                    Reservation.CONFIRMED, Reservation.CANCELLED, Reservation.DENIED,
                    Reservation.REQUESTED, Reservation.READY_FOR_PAYMENT, Reservation.WAITING_FOR_CASH_PAYMENT):
                has_staff_perms = resource.is_manager(request.user) or resource.is_admin(request.user)
                user_can_modify = self.instance.can_modify(request.user)
                # staff members never pay after reservation creation and their order can be removed safely here
                # non staff members i.e. clients must include order when state is ready for payment
                if has_staff_perms or (user_can_modify and state != Reservation.READY_FOR_PAYMENT):
                    del request.data['order']

    def get_required_fields(self):
        return [field_name for field_name in self.fields if self.fields[field_name].required]

    def get_extra_fields(self, includes, context):
        from .resource import ResourceInlineSerializer

        """ Define extra fields that can be included via query parameters. Method from ExtraDataMixin."""
        extra_fields = {}
        if 'resource_detail' in includes:
            extra_fields['resource'] = ResourceInlineSerializer(read_only=True, context=context)
        return extra_fields

    def validate_state(self, value):
        instance = self.instance
        request_user = self.context['request'].user

        # new reservations will get their value regardless of this value
        if not instance:
            return value

        # state not changed
        if instance.state == value:
            return value

        if instance.resource.can_approve_reservations(request_user):
            allowed_states = (Reservation.REQUESTED, Reservation.CONFIRMED,
                              Reservation.DENIED, Reservation.WAITING_FOR_PAYMENT,
                              Reservation.WAITING_FOR_CASH_PAYMENT)
            if instance.state in allowed_states and value in allowed_states:
                return value
        if value == Reservation.WAITING_FOR_PAYMENT:
            return value

        raise ValidationError(_('Illegal state change'))

    def validate(self, data):
        reservation = self.instance
        request_user = self.context['request'].user
        # this check is probably only needed for PATCH

        obj_user_is_staff = bool(request_user and request_user.is_staff)

        if (not reservation or (reservation and reservation.state != Reservation.WAITING_FOR_PAYMENT)) \
            and MaintenanceMode.objects.active().exists():
                raise ValidationError(_('Reservations are disabled at this moment.'))


        try:
            resource = data['resource']
        except KeyError:
            resource = reservation.resource
            data.update({
                'resource': resource
            })

        if not data.get('begin', None):
            data.update({
                'begin': reservation.begin
            })

        if not data.get('end', None):
            data.update({
                'end': reservation.end
            })

        if not resource.can_make_reservations(request_user):
            raise PermissionDenied(_('You are not allowed to make reservations in this resource.'))

        if data['end'] < timezone.now():
            raise ValidationError(_('You cannot make a reservation in the past'))

        if resource.min_age and is_underage(request_user, resource.min_age):
            raise PermissionDenied(_('You have to be over %s years old to reserve this resource' % (resource.min_age)))

        if resource.max_age and is_overage(request_user, resource.max_age):
            raise PermissionDenied(_('You have to be under %s years old to reserve this resource' % (resource.max_age)))

        is_resource_admin = resource.is_admin(request_user)
        is_resource_manager = resource.is_manager(request_user)

        if not isinstance(request_user, AnonymousUser):
            if request_user.preferred_language is None:
                request_user.preferred_language = settings.LANGUAGES[0][0]
                request_user.save()

        if not resource.can_ignore_opening_hours(request_user):
            reservable_before = resource.get_reservable_before()
            if reservable_before and data['begin'] >= reservable_before:
                raise ValidationError(_('The resource is reservable only before %(datetime)s' %
                                        {'datetime': reservable_before}))
            reservable_after = resource.get_reservable_after()
            if reservable_after and data['begin'] < reservable_after:
                raise ValidationError(_('The resource is reservable only after %(datetime)s' %
                                        {'datetime': reservable_after}))

        # Check given home municipality is included in resource's home municipality set
        if 'home_municipality' in data:
            included = resource.get_included_home_municipality_names()
            found = False

            for municipality in included:
                if data['home_municipality'].id == municipality['id']:
                    found = True
                    break

            if not found:
                raise ValidationError(_('Home municipality has to be one of the included home municipality options'))

        # normal users cannot make reservations for other people
        if not resource.can_create_reservations_for_other_users(request_user):
            data.pop('user', None)

        # Check user specific reservation restrictions relating to given period.
        resource.validate_reservation_period(reservation, request_user, data=data)
        reserver_phone_number = data.get('reserver_phone_number', '')
        if reserver_phone_number.startswith('+'):
            if not region_code_for_country_code(phonenumbers.parse(reserver_phone_number).country_code):
                raise ValidationError(dict(reserver_phone_number=_('Invalid country code')))

        if data.get('staff_event', False):
            if not resource.can_create_staff_event(request_user):
                raise ValidationError(dict(staff_event=_('Only allowed to be set by resource managers')))

        if 'type' in data:
            if (data['type'] != Reservation.TYPE_NORMAL and
                    not resource.can_create_special_type_reservation(request_user)):
                raise ValidationError({'type': _('You are not allowed to make a reservation of this type')})

        if 'comments' in data:
            perm_skip = (obj_user_is_staff and (is_resource_admin or is_resource_manager)) or \
                obj_user_is_staff and resource.reservable_by_all_staff
            if perm_skip is False:
                if not resource.can_comment_reservations(request_user):
                    raise ValidationError(dict(comments=_('Only allowed to be set by staff members')))

        if 'takes_place_virtually' in data:
            if not resource.can_create_staff_event(request_user):
                # allow only staff to change virtual data
                if reservation.takes_place_virtually != data['takes_place_virtually']:
                    raise ValidationError(dict(takes_place_virtually=_(
                        'Only allowed to be set and changed by staff members')))

        if 'virtual_address' in data:
            if not resource.can_create_staff_event(request_user):
                # allow only staff to change virtual data
                if reservation.virtual_address != data['virtual_address']:
                    raise ValidationError(dict(
                        virtual_address=_('Only allowed to be set by staff members')))

        if 'access_code' in data:
            if data['access_code'] is None:
                data['access_code'] = ''

            access_code_enabled = resource.is_access_code_enabled()

            if not access_code_enabled and data['access_code']:
                raise ValidationError(dict(access_code=_('This field cannot have a value with this resource')))

            if access_code_enabled and reservation and data['access_code'] != reservation.access_code:
                raise ValidationError(dict(access_code=_('This field cannot be changed')))

        # Mark begin of a critical section. Subsequent calls with this same resource will block here until the first
        # request is finished. This is needed so that the validations and possible reservation saving are
        # executed in one block and concurrent requests cannot be validated incorrectly.
        Resource.objects.select_for_update().get(pk=resource.pk)

        # Check maximum number of active reservations per user per resource.
        # Only new reservations are taken into account ie. a normal user can modify an existing reservation
        # even if it exceeds the limit. (one that was created via admin ui for example).
        if reservation is None and not isinstance(request_user, AnonymousUser):
            resource.validate_max_reservations_per_user(request_user)

        request = self.context.get('request')
        if request.method == 'POST':
            if 'order' in data:
                if data.order.payment_method == Order.CASH and not resource.cash_payments_allowed:
                    raise ValidationError(dict(cash_payments_allowed=_('Cash payments are not allowed')))

        # Run model clean
        instance = Reservation(**data)
        try:
            instance.clean(original_reservation=reservation, user=request_user)
        except DjangoValidationError as exc:
            # Convert Django ValidationError to DRF ValidationError so that in the response
            # field specific error messages are added in the field instead of in non_field_messages.
            if not hasattr(exc, 'error_dict'):
                raise ValidationError(exc)
            error_dict = {}
            for key, value in exc.error_dict.items():
                error_dict[key] = [error.message for error in value]
            raise ValidationError(error_dict)
        return data

    def to_internal_value(self, data):
        hotfix = []
        for field_name in data:
            if not data[field_name]:
                hotfix.append(field_name)

        for field in hotfix:
            if isinstance(data[field], int):
                data[field] = 0
            elif isinstance(data[field], bool):
                data[field] = False
            elif isinstance(data[field], str):
                data[field] = "-"
            elif isinstance(data[field], dict):
                data[field] = {}

        user_data = data.copy().pop('user', None)  # handle user manually
        deserialized_data = super().to_internal_value(data)

        # validate user and convert it to User object
        if user_data:
            UserSerializer(data=user_data).is_valid(raise_exception=True)
            try:
                deserialized_data['user'] = User.objects.get(**{USER_ID_ATTRIBUTE: user_data['id']})
            except User.DoesNotExist:
                raise ValidationError({
                    'user': {
                        'id': [_('Invalid pk "{pk_value}" - object does not exist.').format(pk_value=user_data['id'])]
                    }
                })
        return deserialized_data

    def to_representation(self, instance):
        data = super(ReservationSerializer, self).to_representation(instance)
        resource = instance.resource
        prefetched_user = self.context.get('prefetched_user', None)
        user = prefetched_user or self.context['request'].user

        if self.context['request'].accepted_renderer.format == 'xlsx':
            # Return somewhat different data in case we are dealing with xlsx.
            # The excel renderer needs datetime objects, so begin and end are passed as objects
            # to avoid needing to convert them back and forth.
            data.update(**{
                'unit': resource.unit.name,  # additional
                'resource': resource.name,  # resource name instead of id
                'begin': instance.begin,  # datetime object
                'end': instance.end,  # datetime object
                'user': instance.user.email if instance.user else '',  # just email
                'created_at': instance.created_at,
                'require_assistance': instance.require_assistance,
                'require_workstation': instance.require_workstation,
            })

        # true if user is not admin, manager or viewer for the resource.
        if not resource.can_access_reservation_comments(user):
            insufficient_rights = [
                not user.is_staff and not resource.reservable_by_all_staff,
                user.is_staff and not resource.reservable_by_all_staff,
                not user.is_staff and resource.reservable_by_all_staff,
                instance.user != user
            ]
            if any(insufficient_rights):
                del data['comments']

        # staff should be able to see reservation creation time
        if user.is_superuser or resource.is_admin(user) or resource.is_manager(user) or resource.is_viewer(user):
            tz = resource.unit.get_tz()
            data.update(**{'created_at': instance.created_at.astimezone(tz)})

        if not resource.can_view_reservation_user(user):
            del data['user']

        if not is_authenticated_user(user):
            del data['require_assistance']
            del data['require_workstation']

        if (instance.are_extra_fields_visible(user) or
                (self.context['request'].method == 'POST' and resource.authentication == 'unauthenticated')):
            cache = self.context.get('reservation_metadata_set_cache')
            supported_fields = set(resource.get_supported_reservation_extra_field_names(cache=cache))
        else:
            supported_fields = set()

        if not resource.can_access_reservation_comments(user) and instance.user != user:
            # restrict reservation virtual data visibility to only those who can access comments
            # and to the reserver
            del data['takes_place_virtually']
            del data['virtual_address']

        for field_name in RESERVATION_EXTRA_FIELDS:
            if field_name not in supported_fields:
                data.pop(field_name, None)

        if not (resource.is_access_code_enabled() and instance.can_view_access_code(user)):
            data.pop('access_code')

        if 'access_code' in data and data['access_code'] == '':
            data['access_code'] = None

        if instance.can_view_catering_orders(user):
            data['has_catering_order'] = instance.catering_orders.exists()

        return data

    def get_is_own(self, obj):
        return obj.user == self.context['request'].user

    def get_user_permissions(self, obj):
        request = self.context.get('request')
        prefetched_user = self.context.get('prefetched_user', None)
        user = prefetched_user or request.user

        can_modify_and_delete = obj.can_modify(user) if request else False
        return {
            'can_modify': can_modify_and_delete,
            'can_delete': can_modify_and_delete,
        }


class UserFilterBackend(filters.BaseFilterBackend):
    """
    Filter by user uuid and by is_own.
    """

    def filter_queryset(self, request, queryset, view):
        user = request.query_params.get('user', None)
        if user:
            try:
                user_uuid = uuid.UUID(user)
            except ValueError:
                raise exceptions.ParseError(_('Invalid value in filter %(filter)s') % {'filter': 'user'})
            queryset = queryset.filter(user__uuid=user_uuid)

        if not request.user.is_authenticated:
            return queryset

        is_own = request.query_params.get('is_own', None)
        if is_own is not None:
            is_own = is_own.lower()
            if is_own in ('true', 't', 'yes', 'y', '1'):
                queryset = queryset.filter(user=request.user)
            elif is_own in ('false', 'f', 'no', 'n', '0'):
                queryset = queryset.exclude(user=request.user)
            else:
                raise exceptions.ParseError(_('Invalid value in filter %(filter)s') % {'filter': 'is_own'})
        return queryset


class ExcludePastFilterBackend(filters.BaseFilterBackend):
    """
    Exclude reservations in the past.
    """

    def filter_queryset(self, request, queryset, view):
        past = request.query_params.get('all', 'false')
        past = BooleanField().to_internal_value(past)
        if not past:
            now = timezone.now()
            return queryset.filter(end__gte=now)
        return queryset


class ReservationFilterBackend(filters.BaseFilterBackend):
    """
    Filter reservations by time.
    """

    def filter_queryset(self, request, queryset, view):
        params = request.query_params
        times = {}
        past = False
        for name in ('start', 'end'):
            if name not in params:
                continue
            # whenever date filtering is in use, include past reservations
            past = True
            try:
                times[name] = arrow.get(params[name]).to('utc').datetime
            except ParserError:
                raise exceptions.ParseError("'%s' must be a timestamp in ISO 8601 format" % name)
        is_detail_request = 'pk' in request.parser_context['kwargs']
        if not past and not is_detail_request:
            past = params.get('all', 'false')
            past = BooleanField().to_internal_value(past)
            if not past:
                now = timezone.now()
                queryset = queryset.filter(end__gte=now)
        if times.get('start', None):
            queryset = queryset.filter(end__gte=times['start'])
        if times.get('end', None):
            queryset = queryset.filter(begin__lte=times['end'])
        return queryset


class HasArrivedFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        has_arrived = request.query_params.get('has_arrived', None)
        if has_arrived is not None:
            has_arrived = BooleanField().to_internal_value(has_arrived)
            return queryset.filter(has_arrived=has_arrived)
        return queryset


class PhonenumberFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        phonenumber = request.query_params.get('reserver_phone_number', '')
        phonenumber = phonenumber.strip()
        if phonenumber and phonenumber.isdigit():
            queryset = queryset.filter(Q(reserver_phone_number=phonenumber) |
                                       Q(reserver_phone_number='+%s' % phonenumber))
        return queryset


class NeedManualConfirmationFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        filter_value = request.query_params.get('need_manual_confirmation', None)
        if filter_value is not None:
            need_manual_confirmation = BooleanField().to_internal_value(filter_value)
            return queryset.filter(resource__need_manual_confirmation=need_manual_confirmation)
        return queryset


class StateFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        state = request.query_params.get('state', None)
        if state:
            queryset = queryset.filter(state__in=state.replace(' ', '').split(','))
        return queryset


class CanApproveFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        filter_value = request.query_params.get('can_approve', None)
        if filter_value:
            queryset = queryset.filter(resource__need_manual_confirmation=True)
            allowed_resources = Resource.objects.with_perm('can_approve_reservation', request.user)
            can_approve = BooleanField().to_internal_value(filter_value)
            if can_approve:
                queryset = queryset.filter(resource__in=allowed_resources)
            else:
                queryset = queryset.exclude(resource__in=allowed_resources)
        return queryset


class ReservationFilterSet(django_filters.rest_framework.FilterSet):
    class Meta:
        model = Reservation
        fields = ('event_subject', 'host_name', 'reserver_name', 'resource_name', 'is_favorite_resource', 'unit')

    @property
    def qs(self):
        qs = super().qs
        user = self.request.user
        query_params = set(self.request.query_params)

        # if any of the extra field related filters are used, restrict results to reservations
        # the user has right to see
        if bool(query_params & set(RESERVATION_EXTRA_FIELDS)):
            qs = qs.extra_fields_visible(user)

        if 'has_catering_order' in query_params:
            qs = qs.catering_orders_visible(user)

        return qs

    event_subject = django_filters.CharFilter(lookup_expr='icontains')
    host_name = django_filters.CharFilter(lookup_expr='icontains')
    reserver_name = django_filters.CharFilter(lookup_expr='icontains')
    resource_name = django_filters.CharFilter(field_name='resource', lookup_expr='name__icontains')
    is_favorite_resource = django_filters.BooleanFilter(method='filter_is_favorite_resource',
                                                        widget=DRFFilterBooleanWidget)
    resource_group = django_filters.Filter(field_name='resource__groups__identifier', lookup_expr='in',
                                           widget=django_filters.widgets.CSVWidget, distinct=True)
    unit = django_filters.CharFilter(field_name='resource__unit_id')
    has_catering_order = django_filters.BooleanFilter(method='filter_has_catering_order', widget=DRFFilterBooleanWidget)
    resource = django_filters.Filter(lookup_expr='in', widget=django_filters.widgets.CSVWidget)

    def filter_is_favorite_resource(self, queryset, name, value):
        user = self.request.user

        if not user.is_authenticated:
            return queryset.none() if value else queryset

        filtering = {'resource__favorited_by': user}
        return queryset.filter(**filtering) if value else queryset.exclude(**filtering)

    def filter_has_catering_order(self, queryset, name, value):
        return queryset.exclude(catering_orders__isnull=value)

    def filter_reserver_info_search(self, queryset, name, value):
        """
        A partial copy of rest_framework.filters.SearchFilter.filter_queryset.
        Needed due to custom filters applied to queryset within this ReservationFilterSet.

        Does not support comma separation of values, i.e. '?reserver_info_search=foo,bar' will
        be considered as one string - 'foo,bar'.
        """
        if not value:
            return queryset

        fields = ('user__first_name', 'user__last_name', 'user__email')
        conditions = []
        for field in fields:
            conditions.append(Q(**{field + '__icontains': value}))

        # assume that first_name and last_name were provided if empty space was found
        if ' ' in value and value.count(' ') == 1:
            name1, name2 = value.split()
            filters = Q(
                user__first_name__icontains=name1,
                user__last_name__icontains=name2,
            ) | Q(
                user__first_name__icontains=name2,
                user__last_name__icontains=name1,
            )
            conditions.append(filters)
        return queryset.filter(reduce(operator.or_, conditions))


class ReservationPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        resource_id = request.data.get('resource')
        try:
            resource = Resource.objects.get(pk=resource_id)
        except Resource.DoesNotExist:
            return request.method in permissions.SAFE_METHODS or \
                request.user and request.user.is_authenticated

        if resource.authentication == 'strong' and \
                not request.user.is_strong_auth:
            return False
        if request.method in permissions.SAFE_METHODS or \
                request.user and request.user.is_authenticated:
            return True
        return request.method == 'POST' and resource.authentication == 'unauthenticated'

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.can_modify(request.user)


class ReservationExcelRenderer(renderers.BaseRenderer):
    media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    format = 'xlsx'
    charset = None
    render_style = 'binary'

    def render(self, data, media_type=None, renderer_context=None):
        if not renderer_context or renderer_context['response'].status_code == 404:
            return bytes()

        request = renderer_context['request']
        if renderer_context['view'].action == 'retrieve':
            return generate_reservation_xlsx([data], request=request)
        elif renderer_context['view'].action == 'list':
            weekdays = request.GET.get('weekdays', '').split(',')
            weekdays = [int(day) for day in weekdays if day]
            reservations = data['results']
            for reservation in reservations.copy():
                begin = reservation['begin']
                if weekdays and begin.weekday() not in weekdays:
                    reservations.remove(reservation)
            return generate_reservation_xlsx(reservations, request=request, weekdays=weekdays)
        else:
            return NotAcceptable()


class ReservationCacheMixin:
    def _preload_permissions(self):
        units = set()
        resource_groups = set()
        resources = set()
        checker = ObjectPermissionChecker(self.request.user)

        for rv in self._page:
            resources.add(rv.resource)
            rv.resource._permission_checker = checker

        for res in resources:
            units.add(res.unit)
            for g in res.groups.all():
                resource_groups.add(g)

        if units:
            checker.prefetch_perms(units)
        if resource_groups:
            checker.prefetch_perms(resource_groups)

    def _get_cache_context(self):
        context = {}
        set_list = ReservationMetadataSet.objects.all().prefetch_related('supported_fields', 'required_fields')
        context['reservation_metadata_set_cache'] = {x.id: x for x in set_list}

        self._preload_permissions()
        return context


class ReservationBulkViewSet(viewsets.ModelViewSet, ReservationCacheMixin):
    queryset = ReservationBulk.objects.all()
    permission_classes = (permissions.IsAuthenticatedOrReadOnly, ReservationPermission, permissions.IsAdminUser,)

    def get_serializer_class(self):
        return ReservationBulkSerializer

    def get_serializer(self, *args, **kwargs):
        return super().get_serializer(*args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset

    """
    {
    "reservation_stack": [{
        "begin": "2019-11-26T13:00:00+02:00",
        "end": "2019-11-26T14:00:00+02:00",
        "resource": "awmdvkth2vea"
    }, {
        "begin": "2019-11-27T11:00:00.000Z",
        "end": "2019-11-27T12:00:00.000Z"
    }, {
        "begin": "2019-11-28T11:00:00.000Z",
        "end": "2019-11-28T12:00:00.000Z"
    }, {
        "begin": "2019-11-29T11:00:00.000Z",
        "end": "2019-11-29T12:00:00.000Z"
    }],
    "reserver_name": "nimi",
    "reserver_phone_number": "2092393939",
    "reserver_email_address": "asd@ewq.com",
    "preferred_language": "fi",
    "resource": "awmdvkth2vea"
    }
    """
    @transaction.atomic
    def create(self, request):
        stack = request.data.pop('reservation_stack')
        if 'resource' in stack[0]:
            stack[0].pop('resource')
        if len(stack) > 100:
            return JsonResponse({
                'status': 'false',
                'recurring_validation_error': _('Reservation failed. Too many reservations at once.'),
            }, status=400
            )
        data = {
            **request.data
        }
        data.update({
            'user': request.user
        })
        resource_id = data.get('resource')
        try:
            for key in stack:
                begin = key.get('begin')
                end = key.get('end')
                if begin is None or end is None:
                    return JsonResponse({
                        'status': 'false',
                        'recurring_validation_error': _('Reservation failed. Begin or end time is missing.')
                    }, status=400
                    )
            reservations = []
            for key in stack:
                begin = parse_datetime(key.get('begin'))
                end = parse_datetime(key.get('end'))
                try:
                    resource = Resource.objects.get(id=resource_id)
                except:
                    raise
                data['resource'] = resource
                res = Reservation(
                    **data
                )
                res.begin = begin
                res.end = end
                if resource.validate_reservation_period(res, res.user):
                    return JsonResponse({
                        'status': 'false',
                        'recurring_validation_error': _('Reservation failed. Make sure reservation period is correct.')
                    }, status=400
                    )
                if resource.validate_max_reservations_per_user(res.user):
                    return JsonResponse({
                        'status': 'false',
                        'recurring_validation_error': _('Reservation failed. Too many reservations at once.')
                    }, status=400
                    )
                if resource.check_reservation_collision(begin, end, res):
                    return JsonResponse({
                        'status': 'false',
                        'recurring_validation_error': _('Reservation failed. Overlap with existing reservations.')
                    }, status=400
                    )
                reservations.append(res)
            reservation_dates_context = {'dates': []}

            """
            {% if bulk_email_context is defined %}
                {% for date in bulk_email_context['dates'] %}
                    Alku: {{ date.get('begin') }}
                    Loppu {{ date.get('end') }}
                {% endfor %}
            {% endif %}
            """
            for res in reservations:
                res.state = 'confirmed'
                if resource.validate_reservation_period(res, res.user):
                    return JsonResponse({
                        'status': 'false',
                        'recurring_validation_error': _('Reservation failed. Make sure reservation period is correct.')
                    }, status=400
                    )
                if resource.validate_max_reservations_per_user(res.user):
                    return JsonResponse({
                        'status': 'false',
                        'recurring_validation_error': _('Reservation failed. Too many reservations at once.')
                    }, status=400
                    )
                if resource.check_reservation_collision(begin, end, res):
                    return JsonResponse({
                        'status': 'false',
                        'recurring_validation_error': _('Reservation failed. Overlap with existing reservations.')
                    }, status=400
                    )
                res.save()
                reservation_dates_context['dates'].append(
                    {
                        'begin': dateparser(reservations[0].begin, res.begin),
                        'end': dateparser(reservations[0].end, res.end)
                    }
                )

            reservation_dates_context.update({
                'first_reservation': {
                    'begin': dateparser(reservations[0].begin, reservations[0].begin),
                    'end': dateparser(reservations[0].end, reservations[0].end)
                }
            })
            reservation_dates_context.update({
                'last_reservation': {
                    'begin': dateparser(reservations[0].begin, reservations[len(reservations) - 1].begin),
                    'end': dateparser(reservations[0].end, reservations[len(reservations) - 1].end)
                }
            })
            res = reservations[0]
            url = ''.join([request.is_secure() and 'https' or 'http', get_current_site(
                request).domain, '/v1/', 'reservation/', str(res.id), '/'])
            ical_file = build_reservations_ical_file(reservations)
            attachment = ('reservation.ics', ical_file, 'text/calendar')
            res.send_reservation_mail(
                NotificationType.RESERVATION_BULK_CREATED,
                attachments=[attachment],
                extra_context=reservation_dates_context
            )
            return JsonResponse(
                data={
                    **ReservationSerializer(context={'request': self.request if self.request else request}).to_representation(res)},
                status=200)
        except Exception as ex:
            return JsonResponse(
                {
                    'status': 'false',
                    'recurring_validation_error': 'Reservation failed. Try again later.'
                }, status=500
            )


class ReservationViewSet(munigeo_api.GeoModelAPIView, viewsets.ModelViewSet, ReservationCacheMixin):
    queryset = Reservation.objects.select_related('user', 'resource', 'resource__unit')\
        .prefetch_related('catering_orders').prefetch_related('resource__groups').order_by('begin', 'resource__unit__name', 'resource__name')
    if settings.RESPA_PAYMENTS_ENABLED:
        queryset = queryset.prefetch_related('order', 'order__order_lines', 'order__order_lines__product')
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter, UserFilterBackend, ReservationFilterBackend,
                       NeedManualConfirmationFilterBackend, StateFilterBackend, CanApproveFilterBackend, PhonenumberFilterBackend, HasArrivedFilterBackend)
    filterset_class = ReservationFilterSet
    permission_classes = (ReservationPermission, )
    renderer_classes = (renderers.JSONRenderer, ResourcesBrowsableAPIRenderer, ReservationExcelRenderer)
    pagination_class = ReservationPagination
    authentication_classes = (
        list(drf_settings.DEFAULT_AUTHENTICATION_CLASSES) +
        [TokenAuthentication, SessionAuthentication])
    ordering_fields = ('begin',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.srs = getattr(self, 'srs', munigeo_api.srid_to_srs(None))

    def get_serializer_class(self):
        if settings.RESPA_PAYMENTS_ENABLED:
            from payments.api.reservation import PaymentsReservationSerializer  # noqa
            return PaymentsReservationSerializer
        else:
            return ReservationSerializer

    def get_serializer(self, *args, **kwargs):
        if 'data' not in kwargs and len(args) == 1:
            # It's a read operation
            instance_or_page = args[0]
            if isinstance(instance_or_page, Reservation):
                self._page = [instance_or_page]
            else:
                self._page = instance_or_page

        return super().get_serializer(*args, **kwargs)

    def get_serializer_context(self, *args, **kwargs):
        context = super().get_serializer_context(*args, **kwargs)
        if hasattr(self, '_page'):
            context.update(self._get_cache_context())

        request_user = self.request.user

        if request_user.is_authenticated:
            prefetched_user = get_user_model().objects.prefetch_related('unit_authorizations', 'unit_group_authorizations__subject__members').\
                get(pk=request_user.pk)

            context['prefetched_user'] = prefetched_user

        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # General Administrators can see all reservations
        if is_general_admin(user):
            return queryset

        # normal users can see only their own reservations and reservations that are confirmed, requested or
        # waiting for payment. Unit admins and managers can see all reservations of their units.
        filters = Q(state__in=(Reservation.CONFIRMED, Reservation.REQUESTED,
                               Reservation.WAITING_FOR_PAYMENT, Reservation.READY_FOR_PAYMENT,
                               Reservation.WAITING_FOR_CASH_PAYMENT))
        if user.is_authenticated:
            filters |= Q(user=user)

        if is_any_admin(user) or is_any_manager(user):
            filters |= Q(resource__unit__in=Unit.objects.managed_by(user))

        queryset = queryset.filter(filters)
        queryset = queryset.filter(resource__in=Resource.objects.visible_for(user))
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        override_data = {'created_by': user if user.is_authenticated else None,
                         'modified_by': user if user.is_authenticated else None}

        if 'user' not in serializer.validated_data:
            override_data['user'] = user if user.is_authenticated else None
        override_data['state'] = Reservation.CREATED
        instance = serializer.save(**override_data)

        resource = serializer.validated_data['resource']

        order = instance.get_order()

        if resource.need_manual_confirmation and not resource.can_bypass_manual_confirmation(user):
            new_state = Reservation.REQUESTED
        else:
            if order and order.state != Order.CONFIRMED and not resource.can_bypass_manual_confirmation(user):
                new_state = Reservation.WAITING_FOR_PAYMENT
            elif order and order.state == Order.WAITING and order.payment_method == Order.CASH \
                    and resource.cash_payments_allowed and resource.can_bypass_manual_confirmation(user):
                new_state = Reservation.WAITING_FOR_CASH_PAYMENT
            else:
                new_state = Reservation.CONFIRMED

        if new_state == Reservation.CONFIRMED and \
                order and order.state == Order.WAITING and not resource.can_bypass_manual_confirmation(user):
            new_state = Reservation.WAITING_FOR_PAYMENT

        instance.set_state(new_state, self.request.user)

    def perform_update(self, serializer):
        old_instance = self.get_object()
        new_state = serializer.validated_data.pop('state', old_instance.state)
        order = old_instance.get_order()
        resource = serializer.validated_data['resource']
        can_edit_paid = resource.can_modify_paid_reservations(self.request.user)

        # when staff makes an update (can edit paid perm), state should not change to waiting for payment
        if new_state == Reservation.READY_FOR_PAYMENT and \
                order and order.state == Order.WAITING and not can_edit_paid:
            new_state = Reservation.WAITING_FOR_PAYMENT

        if new_state == Reservation.CONFIRMED and order and order.state == Order.WAITING:
            if old_instance.state == Reservation.REQUESTED:
                if order.payment_method == Order.CASH:
                    new_state = Reservation.WAITING_FOR_CASH_PAYMENT
                else:
                    new_state = Reservation.READY_FOR_PAYMENT

        new_instance = serializer.save(modified_by=self.request.user)
        new_instance.set_state(new_state, self.request.user)

        if old_instance.state == Reservation.WAITING_FOR_CASH_PAYMENT and \
                new_state == Reservation.CONFIRMED:
            new_instance.get_order().set_state(Order.CONFIRMED, 'Cash payment confirmed.')

        # Reservation was modified, don't send modified upon patch.
        if new_state == old_instance.state and new_state not in ['denied'] and self.request.method != 'PATCH':
            # dont send if main reservation fields are not different e.g. only comments changes
            if is_reservation_metadata_or_times_different(old_instance, new_instance):
                self.send_modified_mail(new_instance, is_staff=self.request.user.is_staff)

    def perform_destroy(self, instance):
        instance.set_state(Reservation.CANCELLED, self.request.user)
        if instance.has_order():
            order = instance.get_order()
            order.set_state(Order.CANCELLED, 'Order reservation was cancelled.', user = self.request.user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if request.accepted_renderer.format == 'xlsx':
            response['Content-Disposition'] = 'attachment; filename={}.xlsx'.format(_('reservations'))
        return response

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        if request.accepted_renderer.format == 'xlsx':
            response['Content-Disposition'] = 'attachment; filename={}-{}.xlsx'.format(_('reservation'), kwargs['pk'])
        return response

    def send_modified_mail(self, new_instance, is_staff=False):
        new_instance.send_reservation_modified_mail(action_by_official=is_staff)
        if not is_staff:
            new_instance.notify_staff_about_reservation(NotificationType.RESERVATION_MODIFIED_OFFICIAL)


register_view(ReservationViewSet, 'reservation')
register_view(ReservationBulkViewSet, 'reservation_bulk')
