from django.conf import settings
from django.utils import timezone
import django_filters
from modeltranslation.translator import NotRegistered, translator
from rest_framework import serializers, fields as drf
from django.db.models import Q
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from django.contrib.gis.geos import Point
from resources.models.availability import Period, Day
from resources.models.resource import Resource
from resources.models.unit import Unit

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