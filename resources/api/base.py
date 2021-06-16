from django.conf import settings
from django.utils import timezone
import django_filters
from modeltranslation.translator import NotRegistered, translator
from rest_framework import serializers
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

all_views = []


def register_view(klass, name, base_name=None):
    entry = {'class': klass, 'name': name}
    if base_name is not None:
        entry['base_name'] = base_name
    all_views.append(entry)


LANGUAGES = [x[0] for x in settings.LANGUAGES]

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
            del data[field]
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
