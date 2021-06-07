from rest_framework import serializers
from collections import OrderedDict
from django.utils.translation import ugettext_lazy as _
from accessibility.models import ServicePoint, ServiceShortage, ServiceRequirement, ServiceEntrance, ServiceSentence, Sentence, SentenceGroup
from django.core.exceptions import ValidationError
from resources.api.base import TranslatedModelSerializer
import json

import re

def build_url(request, pk):
    url = request.build_absolute_uri(request.get_full_path())
    if re.search(r'/\?', url):
        url = url.replace(re.search(r'\?.*$', url)[0], '')
    if re.search(str(pk), url):
        return url
    return f"{url}{pk}/"

class BaseSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        obj = super(BaseSerializer, self).to_representation(instance)
        return OrderedDict([(key, obj[key])
            if obj[key] or not obj[key] and isinstance(obj[key], bool) and isinstance(obj[key], dict)
                else (key, "") for key in obj])

    def validate(self, attrs):
        return super().validate(attrs)


class SentenceSerializer(BaseSerializer):
    class Meta:
        model = Sentence
        fields = (
            'sentence_fi',
            'sentence_sv',
            'sentence_en'
        )

class SentenceGroupSerializer(BaseSerializer):
    sentences = SentenceSerializer(many=True)
    class Meta:
        model = SentenceGroup
        fields = (
            'name_fi', 'name_en', 'name_sv',
            'sentences'
        )
    


class ServiceRequirementSerializer(BaseSerializer):
    id = serializers.IntegerField()
    text_fi = serializers.CharField(required=True)

    class Meta:
        model = ServiceRequirement
        fields = (
            'id', 'text_fi', 'text_en', 'text_sv',
            'is_indoor_requirement', 'evaluation_zone'
        )



class ServiceShortagesSerializer(BaseSerializer):
    viewpoint = serializers.IntegerField(required=False)

    class Meta:
        model = ServiceShortage
        fields = (
            'id',
            'system_id', 'viewpoint',
            'shortage_fi', 'shortage_en', 'shortage_sv',
            'service_requirement'
        )

    def to_representation(self, instance):
        obj = super().to_representation(instance)
        if obj["service_requirement"]:
            requirement = ServiceRequirement.objects.get(pk=obj["service_requirement"])
            obj["service_requirement"] = ServiceRequirementSerializer(requirement).data
        return obj

class ServiceSentenceSerializer(BaseSerializer):
    id = serializers.IntegerField(required=False)
    sentence_group = SentenceGroupSerializer()


    class Meta:
        model = ServiceSentence
        fields = (
            'id',
            'system_id',
            'sentence_order_text',
            'sentence_group'
        )

class ServiceEntranceSerializer(BaseSerializer):
    id = serializers.IntegerField()
    location = serializers.JSONField(required=False)
    is_main_entrance = serializers.BooleanField(required=False)

    service_sentences = ServiceSentenceSerializer(many=True, required=False)

    class Meta:
        model = ServiceEntrance
        fields = (
            'id',
            'system_id', 'is_main_entrance',
            'location', 'photo_url', 'street_view_url',
            'name_fi', 'name_en', 'name_sv', 'service_sentences',
        )
    def validate_location(self, data, **kwargs):
        try:
            json.loads(data)
            return data
        except:
            raise ValidationError({
                'message':'Invalid JSON'
            })
    
    def to_representation(self, instance):
        obj = super().to_representation(instance)
        obj["location"] = json.loads(obj["location"])
        return obj

class ServicePointSerializer(BaseSerializer):
    service_shortages = ServiceShortagesSerializer(many=True)
    service_entrances = ServiceEntranceSerializer(many=True)

    name_fi = serializers.CharField(required=True)
    code    = serializers.CharField(required=True)

    class Meta:
        model = ServicePoint
        fields = (
            'id', 'code',
            'name_fi', 'name_en', 'name_sv',
            'service_shortages', 'service_entrances'
        )

    def create(self, validated_data):
        service_shortages = validated_data.pop('service_shortages', [])
        service_entrances = validated_data.pop('service_entrances', [])
        instance = ServicePoint.objects.create(**validated_data)

        for service_shortage in service_shortages:
            ServiceShortage.objects.create(service_point=instance, **service_shortage)
        
        for service_entrance in service_entrances:
            service_sentences = service_entrance.pop('service_sentences', [])
            service_entrance = ServiceEntrance.objects.create(service_point=instance, **service_entrance)
            for service_sentence in service_sentences:
                sentence_group = service_sentence.pop('sentence_group', [])
                sentences = sentence_group.pop('sentences', [])
                sentence_group = SentenceGroup.objects.create(**sentence_group)
                service_sentence = ServiceSentence.objects.create(service_point=instance, service_entrance=service_entrance, sentence_group=sentence_group, **service_sentence)
                for sentence in sentences:
                    sentence = Sentence.objects.create(group=sentence_group, **sentence)
        return instance

    def to_representation(self, instance):
        request = self.context['request']
        obj = OrderedDict()
        obj.update({
            'url': build_url(request, instance.id)
        })
        obj.update(super().to_representation(instance))
        return obj


class ServicePointUpdateSerializer(ServicePointSerializer):
    service_shortages = ServiceShortagesSerializer(many=True, required=False)
    service_entrances = ServiceEntranceSerializer(many=True, required=False)

    name_fi = serializers.CharField(required=False)
    code    = serializers.CharField(required=False)

    def update(self, instance, validated_data):
        shortages = validated_data.pop('service_shortages', [])
        service_entrances = validated_data.pop('service_entrances', [])
        for shortage in shortages:
            ServiceShortage.objects.update_or_create(service_point=instance, **shortage)
        for service_entrance in service_entrances:
            service_sentences = service_entrance.pop('service_sentences', [])
            service_entrance, _ = ServiceEntrance.objects.update_or_create(service_point=instance, **service_entrance)
            for service_sentence in service_sentences:

                sentence_group = service_sentence.pop('sentence_group', [])
                sentences = sentence_group.pop('sentences', [])

                sentence_group, _ = SentenceGroup.objects.update_or_create(**sentence_group)

                service_sentence, _ = ServiceSentence.objects.update_or_create(service_point=instance, service_entrance=service_entrance, sentence_group=sentence_group, **service_sentence)
                
                for sentence in sentences:
                    sentence, _ = Sentence.objects.update_or_create(group=sentence_group, **sentence)
        return instance