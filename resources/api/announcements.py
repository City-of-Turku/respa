from rest_framework import viewsets
from .base import TranslatedModelSerializer, register_view
from resources.models import MaintenanceMessage



class MaintenanceMessageSerializer(TranslatedModelSerializer):
    class Meta:
        model = MaintenanceMessage
        fields = ('message', )



class MaintenanceMessageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaintenanceMessage.objects.all()
    serializer_class = MaintenanceMessageSerializer


    def get_queryset(self):
        return self.queryset.active()


register_view(MaintenanceMessageViewSet, 'announcements', base_name='announcements')