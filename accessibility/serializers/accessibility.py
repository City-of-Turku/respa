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

class BaseSerializer(TranslatedModelSerializer):
    def to_representation(self, instance):
        obj = super(BaseSerializer, self).to_representation(instance)
        return OrderedDict([(key, obj[key])
            if obj[key] or not obj[key] and (isinstance(obj[key], bool) or isinstance(obj[key], dict))
                else (key, "") for key in obj])

    def validate(self, attrs):
        return super().validate(attrs)


class SentenceSerializer(BaseSerializer):
    sentence = serializers.DictField(required=True)


    class Meta:
        model = Sentence
        fields = ('sentence', )
        required_translations = (
            'sentence_fi',
            'sentence_sv',
            'sentence_en'
        )

class SentenceGroupSerializer(BaseSerializer):
    sentences = SentenceSerializer(many=True)
    name = serializers.DictField(required=True)


    class Meta:
        model = SentenceGroup
        fields = ('name', 'sentences' )
        required_translations = (
            'name_fi', 'name_en', 'name_sv',
        )
    
    def create(self, validated_data):
        sentences = validated_data.pop('sentences', [])
        instance = SentenceGroup(**validated_data)
        instance.save()
        serializer = SentenceSerializer(data=sentences, many=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save(group=instance)
        return instance

class ServiceRequirementSerializer(BaseSerializer):
    id = serializers.IntegerField()
    text = serializers.DictField(required=True)

    class Meta:
        model = ServiceRequirement
        fields = (
            'id', 'text',
            'is_indoor_requirement', 'evaluation_zone'
        )
        required_translations = (
            'text_fi',
        )



class ServiceShortagesSerializer(BaseSerializer):
    id = serializers.IntegerField(required=False)
    viewpoint = serializers.IntegerField(required=True)
    shortage = serializers.DictField(required=True)

    class Meta:
        model = ServiceShortage
        fields = (
            'id', 'viewpoint',
            'shortage',
            'service_requirement'
        )
        required_translations = (
            'shortage_fi', 'shortage_en', 'shortage_sv',
        )

    def to_representation(self, instance):
        obj = super().to_representation(instance)
        if 'service_requirement' in self.context.get('includes',  []) and instance.service_requirement:
            obj['service_requirement'] = ServiceRequirementSerializer().to_representation(instance.service_requirement)
        return obj

class ServiceSentenceSerializer(BaseSerializer):
    id = serializers.IntegerField(required=False)
    sentence_group = SentenceGroupSerializer()

    sentence_order_text = serializers.DictField(required=True)


    class Meta:
        model = ServiceSentence
        fields = (
            'id', 'sentence_order_text',
            'sentence_group'
        )
        required_translations = (
            'sentence_order_text_fi',
        )

    def create(self, validated_data):
        sentence_group = validated_data.pop('sentence_group', None)
        service_point = self.context['service_point']
        service_entrance = self.context['service_entrance']
        if sentence_group:
            serializer = SentenceGroupSerializer(data=sentence_group)
            if serializer.is_valid(raise_exception=True):
                sentence_group = serializer.save()
        instance = ServiceSentence(service_point=service_point, service_entrance=service_entrance, sentence_group=sentence_group, **validated_data)
        instance.save()
        return instance

class ServiceEntranceSerializer(BaseSerializer):
    id = serializers.IntegerField()
    photo_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    street_view_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    location = serializers.JSONField(required=False)
    is_main_entrance = serializers.BooleanField(required=False)
    service_sentences = ServiceSentenceSerializer(many=True, required=False)
    name = serializers.DictField(required=True)

    class Meta:
        model = ServiceEntrance
        fields = (
            'id', 'is_main_entrance',
            'location', 'photo_url', 'street_view_url',
            'name', 'service_sentences',
        )
        required_translations = ('name_fi', )

    def validate_location(self, data, **kwargs):
        try:
            if not isinstance(data, dict):
                json.loads(data)
            return data
        except:
            raise ValidationError({
                'message':'Invalid JSON'
            })
    
    def to_representation(self, instance):
        obj = super().to_representation(instance)
        if obj["location"]:
            if not isinstance(obj["location"], dict):
                obj["location"] = json.loads(obj["location"])
        return obj


class ServicePointSerializer(BaseSerializer):
    service_shortages = ServiceShortagesSerializer(many=True)
    service_entrances = ServiceEntranceSerializer(many=True)
    system_id = serializers.UUIDField(required=False, allow_null=True)
    name = serializers.DictField(required=True)

    class Meta:
        model = ServicePoint
        fields = (
            'id', 'code', 'system_id',
            'name', 'service_shortages', 'service_entrances'
        )
        required_translations = (
            'name_fi', 
        )

    def create(self, validated_data):
        service_shortages = validated_data.pop('service_shortages', [])
        service_entrances = validated_data.pop('service_entrances', [])

        instance = super(ServicePointSerializer, self).create(validated_data)


        for service_shortage in service_shortages:
            serializer = ServiceShortagesSerializer(data=service_shortage)
            if 'service_requirement' in service_shortage:
                service_shortage['service_requirement'] = service_shortage['service_requirement'].id
            if serializer.is_valid(raise_exception=True):
                serializer.save(service_point=instance)
        
        for service_entrance in service_entrances:
            service_sentences = service_entrance.pop('service_sentences', [])
            serializer = ServiceEntranceSerializer(data=service_entrance)
            if serializer.is_valid(raise_exception=True):
                service_entrance = serializer.save(service_point=instance)

            serializer = ServiceSentenceSerializer(data=service_sentences, many=True, context=dict(service_entrance=service_entrance, service_point=instance))
            if serializer.is_valid(raise_exception=True):
                serializer.save()

        return instance

    def to_representation(self, instance):
        request = self.context['request']
        ret = OrderedDict()
        obj = super().to_representation(instance)
        ret.update({
            'url': build_url(request, instance.id),
            **obj
        })

        if 'service_shortages' not in self.context.get('includes',  []):
            ret['service_shortages'] = { 'count': instance.service_shortages.count() }
        if 'service_entrances' not in self.context.get('includes',  []):
            ret['service_entrances'] = { 'count': instance.service_entrances.count() }

        return ret


class ServicePointUpdateSerializer(ServicePointSerializer):
    service_shortages = ServiceShortagesSerializer(many=True, required=False)
    service_entrances = ServiceEntranceSerializer(many=True, required=False)

    name = serializers.DictField(required=False)
    code    = serializers.CharField(required=False)

    class Meta(ServicePointSerializer.Meta):
        required_translations = ()

    def validate(self, attrs):
        service_shortages = attrs.get('service_shortages', [])
        service_entrances = attrs.get('service_entrances', [])

        for service_shortage in service_shortages:
            pk = service_shortage.get('id', None)
            if not pk and self.context['request'].method == 'PATCH':
                raise ValidationError({
                    'message': 'PATCH service_shortage requires id'
                })
        for service_entrance in service_entrances:
            pk = service_entrance.get('id', None)
            if not pk and self.context['request'].method == 'PATCH':
                raise ValidationError({
                    'message': 'PATCH service_entrance requires id'
                })
        
        return super().validate(attrs)


    def update(self, instance, validated_data):
        service_shortages = validated_data.pop('service_shortages', [])
        service_entrances = validated_data.pop('service_entrances', [])
        instance = super().update(instance, validated_data)
        for service_shortage in service_shortages:
            try:
                service_instance = ServiceShortage.objects.get(service_point=instance, pk=service_shortage['id'])
            except:
                service_instance = ServiceShortage(service_point=instance, **service_shortage)
            serializer = ServiceShortagesSerializer(instance=service_instance, data=service_shortage)
            if 'service_requirement' in service_shortage:
                service_shortage['service_requirement'] = service_shortage['service_requirement'].id
            if serializer.is_valid(raise_exception=True):
                serializer.save()
        for service_entrance in service_entrances:
            service_sentences = service_entrance.pop('service_sentences', [])
            try:
                entrance = ServiceEntrance.objects.get(service_point=instance, pk=service_entrance['id'])
            except:
                entrance = ServiceEntrance(service_point=instance, **service_entrance)
            serializer = ServiceEntranceSerializer(instance=entrance, data=service_entrance)
            if serializer.is_valid(raise_exception=True):
                service_entrance = serializer.save()
            serializer = ServiceSentenceSerializer(data=service_sentences, many=True, context=dict(service_entrance=service_entrance, service_point=instance))
            if serializer.is_valid(raise_exception=True):
                serializer.save()
        return instance