from django.shortcuts import render

from respa_o365.o365_calendar import MicrosoftApi, O365Calendar
from respa_o365.o365_notifications import O365Notifications
from respa_o365.serializers import OutlookCalendarLinkSerializer
from respa_o365.models import OutlookCalendarLink, OutlookCalendarReservation
from rest_framework import viewsets
from rest_framework.decorators import action
from resources.api.reservation import UserFilterBackend

class OutlookCalendarLinkViewSet(viewsets.ModelViewSet):
    queryset = OutlookCalendarLink.objects.none()
    serializer_class = OutlookCalendarLinkSerializer
    filter_backends = [UserFilterBackend]
    
    def get_queryset(self):
        if self.request.user.is_anonymous:
            return OutlookCalendarLink.objects.none()

        if self.request and self.request.user:
            if self.request.user.is_superuser:
                queryset = OutlookCalendarLink.objects.all()
            else:
                queryset = OutlookCalendarLink.objects.all().filter(user=self.request.user)

            resource_id = self.request.query_params.get('resource_id', None)
            if resource_id is not None:
                queryset = queryset.filter(resource=resource_id)

            return queryset
        return OutlookCalendarLink.objects.none()

    def perform_destroy(self, instance):
        # Clear outlook
        token = instance.token
        api = MicrosoftApi(token)
        notifications = O365Notifications(microsoft_api=api)
        notifications.delete(instance.exchange_subscription_id)
        cal = O365Calendar(microsoft_api=api)
        mappings = OutlookCalendarReservation.objects.filter(calendar_link_id=instance.id)
        for m in mappings:
            cal.remove_event(m.exchange_id)
        mappings.delete()
        super().perform_destroy(instance)
