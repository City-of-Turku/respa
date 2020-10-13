from django.shortcuts import render
from respa_o365.serializers import OutlookCalendarLinkSerializer
from respa_o365.models import OutlookCalendarLink
from resources.api.base import register_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.request import Request
from django.conf import settings
from requests_oauthlib import OAuth2Session
import os

class OutlookCalendarLinkViewSet(viewsets.ReadOnlyModelViewSet):
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
