from rest_framework import serializers


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
            raise serializers.ValidationError({'resource': 'Invalid pk'})
        except models.ResourceQualityTool.MultipleObjectsReturned:
            raise serializers.ValidationError({'resource': 'Something went wrong'})

        attrs['resource_quality_tool'] = rqt
        return attrs