from rest_framework import serializers
from django.conf import settings

def form_languages():
    from qualitytool import models
    return models.QualityToolFormLanguageOptions.get_solo().options

class QualityToolFormSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super(QualityToolFormSerializer, self).__init__(*args, **kwargs)
        for field in form_languages():
            self.fields[field] = serializers.DictField(required=False)


    def to_representation(self, instance):
        obj = super().to_representation(instance)
        for lang in obj.keys():
            if not obj[lang]:
                del obj[lang]
        return obj


class QualityToolTargetListSerializer(serializers.Serializer):
    name = serializers.DictField(child=serializers.CharField(required=False))
    targetId = serializers.UUIDField(required=False)

    def to_internal_value(self, data):
        self._process_target_name(data)
        return super().to_internal_value(data)
    
    def _process_target_name(self, data : dict):
        """
        Some language fields might not exist, 
        Find existing one and use it as a default.
        """
        name = data['name']
        nonvalues = [lang for lang, _ in settings.LANGUAGES if not name.get(lang, None)]
        default = next(iter(lang for lang, _ in name.items() if name.get(lang, None)))
        name.update({lang: name[default] for lang in nonvalues})
