from rest_framework import serializers

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
    name = serializers.DictField(child=serializers.CharField(), required=False)
    targetId = serializers.UUIDField(required=False)