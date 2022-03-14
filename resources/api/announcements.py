from rest_framework import serializers, viewsets
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly
from .base import TranslatedModelSerializer, register_view
from resources.models import MaintenanceMessage



class MaintenanceMessageSerializer(TranslatedModelSerializer):
    class Meta:
        model = MaintenanceMessage
        fields = ('message', )



class MaintenanceMessageViewSet(viewsets.ModelViewSet):
    queryset = MaintenanceMessage.objects.all()
    serializer_class = MaintenanceMessageSerializer
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly, )


    def get_queryset(self):
        return self.queryset.active()


register_view(MaintenanceMessageViewSet, 'announcements', base_name='announcements')