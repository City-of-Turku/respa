from django.conf import settings
from django.utils import timezone
import django_filters
from modeltranslation.translator import NotRegistered, translator
from rest_framework import (
    serializers, status, 
    permissions, views,
    exceptions,
    fields as drf
)
from rest_framework.response import Response
from django.db.models import Q
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from django.contrib.gis.geos import Point
from resources.models.availability import Period, Day
from resources.models.resource import Resource
from resources.models.unit import Unit
from resources.models.reservation import Reservation, RESERVATION_BILLING_FIELDS
from payments.utils import is_free, get_price

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


all_views = []


def register_view(klass, name, base_name=None):
    entry = {'class': klass, 'name': name}
    if base_name is not None:
        entry['base_name'] = base_name
    all_views.append(entry)


LANGUAGES = [x[0] for x in settings.LANGUAGES]

def get_translated_field_help_text(field_name, value_type = 'string'):
    return f'example: "{field_name}": {{"fi": "{value_type}", "en": "{value_type}", "sv": "{value_type}"}}'

class TranslatedModelSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super(TranslatedModelSerializer, self).__init__(*args, **kwargs)
        model = self.Meta.model
        try:
            trans_opts = translator.get_options_for_model(model)
        except NotRegistered:
            self.translated_fields = []
            return

        self.translated_fields = trans_opts.fields.keys()
        # Remove the pre-existing data in the bundle.
        for field_name in self.translated_fields:
            for lang in LANGUAGES:
                key = "%s_%s" % (field_name, lang)
                if key in self.fields:
                    del self.fields[key]   
            field = self.fields.get(field_name, None)
            if not field:
                continue
            if isinstance(field, drf.DictField) and \
                not getattr(field, 'help_text', None):
                setattr(field, 'help_text', get_translated_field_help_text(field_name))

    def to_representation(self, obj):
        for field in self.translated_fields:
            if not isinstance(getattr(obj, field), dict):
                translated = {}
                for lang in LANGUAGES:
                    val = getattr(obj, '%s_%s' % (field, lang), None)
                    if not val:
                        continue
                    translated[lang] = val
                setattr(obj, field, translated)
    
        ret = super(TranslatedModelSerializer, self).to_representation(obj)
        if obj is None:
            return ret

        for field_name in self.translated_fields:
            if field_name not in self.fields:
                continue
            if isinstance(ret[field_name], dict):
                continue
            d = {}
            for lang in LANGUAGES:
                key = "%s_%s" % (field_name, lang)
                val = getattr(obj, key, None)
                if isinstance(val, dict):
                    val = val.get(lang, None)
                if val in (None, ""):
                    continue
                d[lang] = val

            # If no text provided, leave the field as null
            d = (d or None)
            ret[field_name] = d
        return ret


    def validate_translation(self, data):
        fields = [(key, data[key]) for key in data if key in self.translated_fields]
        for field, value in fields:
            for lang in [x[0] for x in settings.LANGUAGES]:
                if value is None and self.fields[field].allow_null:
                    data.update({
                        '%s_%s' % (field, lang): None
                    })
                    continue

                if (not lang in value or not value[lang]) and '%s_%s' % (field, lang) in self.Meta.required_translations:
                    raise ValidationError({
                        field: [
                                '%s: %s' % (_('This field is required.').replace('.',''), lang)
                            ]
                    })
                if lang in value and not isinstance(value[lang], str):
                    raise ValidationError({
                        field: [
                                _('Invalid type for field: %s_%s, expected: string, but received %s.' % (field, lang, type(value[lang]).__name__))
                            ]
                    })
                data.update({
                    '%s_%s' % (field, lang): value.get(lang, None)
                })
        return data

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if getattr(self.Meta, 'required_translations', None):
            self.validate_translation(attrs)
        return attrs


class NullableTimeField(serializers.TimeField):

    def to_representation(self, value):
        if not value:
            return None
        else:
            value = timezone.localtime(value)
        return super().to_representation(value)


class NullableDateTimeField(serializers.DateTimeField):

    def to_representation(self, value):
        if not value:
            return None
        else:
            value = timezone.localtime(value)
        return super().to_representation(value)


class DRFFilterBooleanWidget(django_filters.widgets.BooleanWidget):
    """
    Without this Django complains about missing render method when DRF renders HTML version of API.
    """
    def render(self, *args, **kwargs):
        return None

class ReservationCreateMixin():
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
    
    def set_supported_and_required_fields(self, request, resource, data):
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


class ExtraDataMixin():
    """ Mixin for serializers that provides conditionally included extra fields """
    INCLUDE_PARAMETER_NAME = 'include'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'context' in kwargs and 'request' in kwargs['context']:
            request = kwargs['context']['request']
            includes = request.GET.getlist(self.INCLUDE_PARAMETER_NAME)
            kwargs['context']['includes'] = includes
            self.fields.update(self.get_extra_fields(includes, context=kwargs['context']))

    def get_extra_fields(self, includes, context):
        """ Return a dictionary of extra serializer fields.
        includes is a list of requested extra data.

        Example:
            fields = {}
            if 'user' in includes:
                fields['user'] = UserSerializer(read_only=True, context=context)
            return fields
        """
        return {}
class DaySerializer(serializers.ModelSerializer):
    weekday = serializers.ChoiceField(choices=Day.DAYS_OF_WEEK, required=True)


    class Meta:
        model = Day
        exclude = (
            'period',
        )

class PeriodSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, help_text="This field is read-only.")
    name = serializers.CharField(required=False, max_length=200)

    days = DaySerializer(required=True, many=True)

    class Meta:
        model = Period
        exclude = ( 'resource', 'unit', )
   
    def create(self, validated_data, **kwargs):
        days = validated_data.pop('days', [])

        if 'id' in validated_data:      # "read_only" during create
            del validated_data['id']

        instance = super().create(validated_data)

        if 'unit' in kwargs:
            setattr(instance, 'unit', kwargs['unit'])
        if 'resource' in kwargs:
            setattr(instance, 'resource', kwargs['resource'])

        serializer = DaySerializer(data=days, many=True)
        if serializer.is_valid(raise_exception=True):
            days = serializer.save(period=instance)

        instance.save()
        return instance

    def update(self, instance, validated_data):
        days = validated_data.pop('days', [])

        try:
            if isinstance(instance, Resource):
                instance = self.Meta.model.objects.get(pk=validated_data['id'], resource=instance)
            elif isinstance(instance, Unit):
                instance = self.Meta.model.objects.get(pk=validated_data['id'], unit=instance)
        except ObjectDoesNotExist as exc:
            if isinstance(instance, Resource):
                instance = self.create(validated_data, resource=instance)
            elif isinstance(instance, Unit):
                instance = self.create(validated_data, unit=instance)

        query = Q()
        for weekday in days:
            query |= Q(weekday=weekday['weekday'])
        instance.days.filter(query).delete()
        
        serializer = DaySerializer(data=days, many=True)
        if serializer.is_valid(raise_exception=True):
            days = serializer.save(period=instance)

        return super().update(instance, validated_data)

    
    def to_representation(self, instance):
        obj = super(PeriodSerializer, self).to_representation(instance)
        obj['days'] = [{
            'weekday': day['weekday'],
            'opens': day['opens'],
            'closes': day['closes'],
            'closed': day['closed']
            } for day in obj['days']]
        return obj

class LocationField(serializers.DictField):
    srid = serializers.CharField(read_only=True)
    coordinates = serializers.ListField(read_only=True)
    type = serializers.CharField(read_only=True)

    def to_representation(self, value):
        if value and not value.empty and isinstance(value, Point):
            ret = {
                'type': 'Point',
                'coordinates': [value.x, value.y]
            }
            return ret

        return super().to_representation(value)

    def to_internal_value(self, data):
        if data['type'].lower() == 'point':
            x,y = data['coordinates']
            srid = data.get('srid', settings.DEFAULT_SRID)
            return Point(x=x, y=y, srid=srid)
        return super().to_internal_value(data)

    def validate_empty_values(self, data):
        if data == drf.empty:
            return super().validate_empty_values(data)


        fields = ('coordinates', 'type')

        if not data:
            raise serializers.ValidationError(_('This field cannot be empty.'))
        
        for field in fields:
            if field not in data:
                raise serializers.ValidationError({field:[_('This field is required.')]})
        
        if not isinstance(data['type'], str):
            raise serializers.ValidationError({'type': [_('Expected value type str, got %s.' % type(data['type']).__name__)]})

        if not isinstance(data['coordinates'], list):
            raise serializers.ValidationError({'coordinates':[_('Expected value type list, got %s.' % type(data['coordinates']).__name__)]})

        if len(data['coordinates']) <= 1 or len(data['coordinates']) > 2:
                raise serializers.ValidationError({'coordinates':[_('Invalid coordinate values.')]})
        for coord in data['coordinates']:
            try:
                int(coord)
            except:
                raise serializers.ValidationError({
                    'coordinates':[_('Invalid coordinate values. Expected value type float, got %s.' % type(coord).__name__)]
                })
        x,y = data['coordinates']
        data['coordinates'] = [float(x), float(y)]


        return super().validate_empty_values(data)
    

class CancelReservationPermission(permissions.BasePermission):
    def __init__(self, instance):
        self.instance = instance

    def has_permission(self, request, view):
        user = request.user
        return super().has_permission(request, view) and self.instance.is_admin(user)


class CancelReservationsSerializer(serializers.Serializer):
    begin = serializers.DateTimeField(required=True)
    end = serializers.DateTimeField(required=True)

    def validate(self, attrs):
        begin = attrs['begin']
        end = attrs['end']
        if begin > end:
            raise serializers.ValidationError({
                'begin': _('Cannot be greater than end')
            })
        return super().validate(attrs)

class CancelReservationsView(views.APIView):
    http_method_names = ('delete', )
    serializer_class = CancelReservationsSerializer

    def get_reservation_queryset(self, begin, end):
        raise NotImplementedError("Not implemented in base class")

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def get_object(self):
        try:
            return self.Meta.model.objects.get(pk=self.kwargs['pk'])
        except self.Meta.model.DoesNotExist:
            raise exceptions.NotFound(
                serializers.PrimaryKeyRelatedField.default_error_messages.get('does_not_exist').format(pk_value=self.kwargs['pk'])
            )

    def get_permissions(self):
        return (CancelReservationPermission(self.get_object()), )

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['begin', 'end'],
            properties={ 
                'begin': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                'end':openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME)
            },
        ),
        responses=None,
        tags=['v1']
    )
    def delete(self, request, **kwargs):
        user = request.user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        reservations = self.get_reservation_queryset(
            validated_data['begin'], validated_data['end']).exclude(state=Reservation.CANCELLED)

        if reservations.exists():
            reservations.cancel(user)

        return Response(status=status.HTTP_204_NO_CONTENT)