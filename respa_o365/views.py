from resources.models.resource import Resource
from django.shortcuts import render
from rest_framework.response import Response

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

    def list(self, request, *args, **kwargs):
        resource_id = request.query_params.get('resource_id', None)
        if resource_id is None:
            return super().list(self, request, *args, **kwargs)
        
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)

        try:
            resource = Resource.objects.get(pk=resource_id)
            resource_has_link = True
            user_has_link = True
            has_permission = resource.is_manager(request.user) or resource.is_admin(request.user)
            if has_permission:
                resource_has_link = OutlookCalendarLink.objects.all().filter(resource=resource_id).exists()
            if not resource_has_link:
                user_has_link = OutlookCalendarLink.objects.all().filter(user=request.user)
            can_create = has_permission and not resource_has_link and not user_has_link
                
        except:
            can_create = False

        data = {
            'results': serializer.data,
            'can_create': can_create
        }

        return Response(data)
  
