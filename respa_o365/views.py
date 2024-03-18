from resources.models.resource import Resource
from django.shortcuts import render
from django.http import JsonResponse, QueryDict
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View
from rest_framework.response import Response

from respa_o365.o365_calendar import MicrosoftApi, O365Calendar
from respa_o365.o365_notifications import O365Notifications
from respa_o365.serializers import OutlookCalendarLinkSerializer
from respa_o365.calendar_login import LoginStartView
from respa_o365.models import OutlookCalendarLink, OutlookCalendarReservation, OutlookTokenRequestData
from rest_framework import viewsets
from rest_framework.decorators import action

from resources.api.reservation import UserFilterBackend
from resources.models import Unit, UnitAuthorization, Resource
from resources.auth import is_any_admin, is_authenticated_user, is_general_admin, is_unit_admin
from respa_admin.views.base import ExtraContextMixin




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
class RAOutlookLinkListView(ExtraContextMixin, TemplateView):
    context_object_name = 'ra_outlook'
    template_name = 'respa_admin/page_outlook.html'


    def get_units(self, user):
        units = Unit.objects.filter(
            id__in=UnitAuthorization.objects.for_user(user).values_list(
            'subject', flat=True).distinct())
        linked_only = not self.outlook_filter or self.outlook_filter == 'has_link'
        return [unit for unit in units if unit.has_outlook_links()] if linked_only \
                else units

    def get_context_data(self, **kwargs):
        user = self.request.user
        context = super().get_context_data(**kwargs)
        if not user.has_outlook_link() and not is_any_admin(user):
            self.outlook_filter = 'no_link'

        context['selected_outlook_filter'] = self.outlook_filter or ''
        context['selected_self_link'] = self.self_link
        context['units'] = self.get_units(user)
        context['user_has_link'] = user.has_outlook_link()
        return context

    def get(self, request, *args, **kwargs):
        self.outlook_filter = request.GET.get('resource_link')
        self.self_link = request.GET.get('self_link')
        return super().get(request, *args, **kwargs)


class RAOutlookLinkCreateView(View):
    def post(self, request, *args, **kwargs):
        user = request.user
        if not is_authenticated_user(user):
            return JsonResponse({'message': _('You are not authorized to create links')}, status=403)

        authorization_url, state = LoginStartView.generate_msgraph_auth()

        resource_id = request.POST.get('resource_id')
        return_to = request.POST.get('return_to')

        resource = Resource.objects.get(pk=resource_id)
        if not resource.is_manager(user) and not resource.is_admin(user):
            return JsonResponse({'message': _('You are not authorized to create links')}, status=403)
        
        if user.has_outlook_link():
            return JsonResponse({'message': _('You already have an existing outlook link')}, status=403)
        
        OutlookTokenRequestData.objects.create(
            state=state,
            return_to=return_to,
            resource_id=resource_id,
            created_at=timezone.now(),
            user=user
        )
        return JsonResponse({
                'redirect_link': authorization_url,
                'state': state
            })

class RAOutlookLinkDeleteView(View):
    def delete(self, request, *args, **kwargs):
        user = request.user
        request_body = QueryDict(request.body)
        outlook_id = request_body.get('outlook_id')
        try:
            outlook_link = OutlookCalendarLink.objects.get(id=outlook_id)
        except OutlookCalendarLink.DoesNotExist:
            return JsonResponse({'message': _('Invalid link ID')}, status=400)

        unit = outlook_link.resource.unit

        if not unit.is_admin(user) \
            and outlook_link.user != user:
            return JsonResponse({'message': _('You are not authorized to delete this link')}, status=403)

        try:
            outlook_link.delete()
        except:
            return JsonResponse({'message': _('Something went wrong')}, status=500)
        return JsonResponse({'message': _('Outlook link removed')}, status=200)


