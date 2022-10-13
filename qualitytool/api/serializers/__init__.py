from rest_framework import serializers
from django.utils.translation import ugettext_lazy as _

class QualityToolFeedbackSerializer(serializers.Serializer):
    reservation_id = serializers.IntegerField()
    rating = serializers.IntegerField()
    text = serializers.CharField()


    def validate(self, attrs):
        from qualitytool import models
        
        attrs = super().validate(attrs)
        try:
            rqt = models.ResourceQualityTool.objects.get(resources__reservation__pk=attrs['reservation_id'])
        except models.ResourceQualityTool.DoesNotExist:
            raise serializers.ValidationError({'resource': _('Invalid pk')})
        except models.ResourceQualityTool.MultipleObjectsReturned:
            raise serializers.ValidationError({'resource': 'Something went wrong'})

        attrs['resource_quality_tool'] = rqt
        return attrs



class QualityToolCheckSerializer(serializers.Serializer):
    resource = serializers.CharField()



    def validate(self, attrs):
        from resources.models import Resource
        attrs = super().validate(attrs)
        try:
            resource = Resource.objects.get(pk=attrs['resource'])
        except Resource.DoesNotExist:
            raise serializers.ValidationError({'resource': _('Invalid pk')})
        attrs['resource'] = resource
        return attrs