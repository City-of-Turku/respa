from rest_framework import viewsets
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly
import django_filters
from .base import TranslatedModelSerializer, register_view
from resources.models import UniversalFormFieldType

class UniversalFormFieldTypeSerializer(TranslatedModelSerializer):    
    class Meta:
        model = UniversalFormFieldType
        fields = ('type',)

    def to_representation(self, obj):
        return obj.type
    
class UniversalFormFieldTypeViewSet(viewsets.ModelViewSet):
    queryset = UniversalFormFieldType.objects.all()
    serializer_class = UniversalFormFieldTypeSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly,)


register_view(UniversalFormFieldTypeViewSet, 'universal_field_type')