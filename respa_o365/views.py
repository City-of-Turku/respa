from django.shortcuts import render

from respa_o365.calendar_sync import perform_sync_to_exchange
from respa_o365.o365_calendar import MicrosoftApi, O365Calendar
from respa_o365.o365_notifications import O365Notifications
from respa_o365.serializers import OutlookCalendarLinkSerializer
from respa_o365.models import OutlookCalendarLink, OutlookCalendarReservation
from resources.api.base import register_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.request import Request
from django.conf import settings
from requests_oauthlib import OAuth2Session
import os

class OutlookCalendarLinkViewSet(viewsets.ModelViewSet):
    queryset = OutlookCalendarLink.objects.none()
    serializer_class = OutlookCalendarLinkSerializer

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
