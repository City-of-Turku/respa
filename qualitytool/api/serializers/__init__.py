from rest_framework import serializers
from django.utils.translation import ugettext_lazy as _

class QualityToolFeedbackSerializer(serializers.Serializer):
    reservation_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, min_length=1, max_length=2048, allow_null=True)


    def validate(self, attrs):
        from qualitytool import models
        from resources.models import Reservation
        
        attrs = super().validate(attrs)
        try:
            reservation = Reservation.objects.get(pk=attrs['reservation_id'])
        except Reservation.DoesNotExist:
            raise serializers.ValidationError({'reservation': _('Invalid pk')})

        try:
            rqt = models.ResourceQualityTool.objects.get(resources__id=reservation.resource.id)
        except models.ResourceQualityTool.DoesNotExist:
            raise serializers.ValidationError({'resource': _('Invalid pk') })
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