from django.utils import timezone
from rest_framework import viewsets, serializers
from resources.api.base import TranslatedModelSerializer, register_view
from maintenance.models import MaintenanceMessage



class MaintenanceMessageSerializer(TranslatedModelSerializer):
    is_maintenance_mode_on = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceMessage
        fields = ('message', 'is_maintenance_mode_on')

    def get_is_maintenance_mode_on(self, obj):
        maintenance_modes = obj.maintenancemode_set.all()
        now = timezone.now()

        for maintenance_mode in maintenance_modes:
            if maintenance_mode.start <= now <= maintenance_mode.end:
                return True

        return False



class MaintenanceMessageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaintenanceMessage.objects.all()
    serializer_class = MaintenanceMessageSerializer


    def get_queryset(self):
        return self.queryset.active()


register_view(MaintenanceMessageViewSet, 'announcements', base_name='announcements')
