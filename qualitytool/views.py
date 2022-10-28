from itertools import chain
from django.utils.translation import ugettext as _
from django.shortcuts import redirect
from django.urls import reverse
from django.forms import ValidationError
from django.http import JsonResponse
from django.views.generic.base import TemplateView, View
from django.db.models import Q
from qualitytool.models import ResourceQualityTool
from resources.auth import is_authenticated_user, is_general_admin
from resources.models import Unit, UnitAuthorization
from resources.models.resource import Resource
from resources.models.utils import generate_id
from respa_admin.views.base import ExtraContextMixin
from qualitytool.manager import qt_manager

from copy import copy

import json

class QualityToolBase(ExtraContextMixin):
    def get_user_resources(self, user):
        units = Unit.objects.filter(
                id__in=UnitAuthorization.objects.for_user(user).values_list(
                'subject', flat=True).distinct())
        return list(chain.from_iterable(unit.resources.all() for unit in units))

    def _process_list_view(self, request, *args, **kwargs):
        self.object = None
        self._page_title = ''
        self.is_edit = False
    
    def _process_detail_view(self, request, *args, **kwargs):
        if self.pk_url_kwarg in kwargs:
            self.object = self.get_object()
            self._page_title = _('Manage quality tool target')
        else:
            self._page_title = _('Create quality tool target')
            self.object = None
        self.is_edit = self.object is not None

    def process_request(self, request, *args, **kwargs):
        self.user = request.user
        self.query_params = request.GET
        self.session_context = request.session.pop('session_context', None)
        if not hasattr(self, 'pk_url_kwarg'):
            return self._process_list_view(request, *args, **kwargs)
        return self._process_detail_view(request, *args, **kwargs)

    def get_object(self):
        self.pk = self.kwargs.get(self.pk_url_kwarg)
        return self.model.objects.get(pk=self.pk)

    def set_session_context(self, request, **kwargs):
        request.session['session_context'] = kwargs

class QualityToolBaseView(QualityToolBase, View):
    context_object_name = 'qualitytool'
    model = ResourceQualityTool




class QualityToolRemoveLinkView(QualityToolBaseView):
    context_object_name = 'qualitytool'
    model = ResourceQualityTool
    pk_url_kwarg = 'qualitytool_id'

    def post(self, request, *args, **kwargs):
        self.process_request(request, *args, **kwargs)
        instance = self.get_object()
        unit = instance.get_unit()

        if not unit.is_admin(self.user):
            self.set_session_context(request, redirect_message={
                'message':_('You must be unit admin to delete quality tool target.'),
                'type':'error'
            })
        else:
            instance.delete()
            self.set_session_context(request, redirect_message={
                'message': _('Quality tool target removed.'),
                'type':'success'
            })
        return redirect('respa_admin:ra-qualitytool')

class QualityToolManagementView(QualityToolBaseView, TemplateView):
    template_name = 'respa_admin/page_qualitytool.html'
    

    def get_queryset(self):
        queryset = self.model.objects.all()
        search = self.query_params.get('search' '')
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

        

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()

        if not is_general_admin(self.user):
            resources = [resource.pk for resource in self.get_user_resources(self.user)]
            queryset = queryset.filter(resources__pk__in=resources)
        
        context['qualitytools'] = queryset
        context['random_id_str'] = generate_id()
        if self.session_context:
            context['qualitytool_redirect_context'] = self.session_context['redirect_message']
        return context

    def get(self, request, *args, **kwargs):
        self.process_request(request, *args, **kwargs)
        return super().get(request, *args, **kwargs)


class QualityToolLinkView(QualityToolBaseView, TemplateView):
    template_name = 'respa_admin/qualitytool/_qualitytool_link.html'
    pk_url_kwarg = 'qualitytool_id'

    class Meta:
        fields = ('resources', 'target_id', 'name')

    def validate(self, payload):
        for field in self.Meta.fields:
            if field not in payload:
                raise ValidationError(_('Missing fields'), 400)
        if len(set(self.Meta.fields) - set(payload)) > 0:
            raise ValidationError( _('Invalid set size'), 400)

        if not isinstance(payload['name'], dict):
            raise ValidationError(_('Name must be a dict'), 400)

        if not payload['resources']:
            raise ValidationError(_('Resources must be selected'), 400)
        
        if not isinstance(payload['resources'], list):
            raise ValidationError(_('Resources must be a list'), 400)

        
        query = Q(resources__pk__in=payload['resources'])
        if self.is_edit:
            query &= ~Q(pk=self.object.pk)

        if ResourceQualityTool.objects.filter(query).exists():
            raise ValidationError(_('Some of these resources are already linked to another quality tool target'), 400)


    def process_resources(self, resources):
        for resource in copy(resources):
            if resource.qualitytool.exists():
                if not self.is_edit or \
                    (self.is_edit and not self.object.resources.filter(pk=resource.pk).exists()):
                    resources.remove(resource)
                    continue
                setattr(resource, 'checked', True)
        resources.sort(key=lambda val: not getattr(val, 'checked', False))
        return resources


    def get_context_data(self, instance, **kwargs):
        context = super(QualityToolLinkView, self).get_context_data(**kwargs)
        context['resources'] = self.process_resources(self.get_user_resources(self.user))
        context['is_edit'] = self.is_edit
        context['page_title'] = self._page_title

        if self.session_context:
            context['qualitytool_redirect_context'] = self.session_context['redirect_message']
        search = self.query_params.get('search', '')
        if instance:
            context['qualitytool_target_options'] = [qt_manager._instance_to_dict(instance, id=generate_id(), checked=True)]
        elif search:
            targets = []
            target_list = qt_manager.get_targets()
            for target in target_list:
                if any(name.lower().find(search) > -1 for _, name in target['name'].items()):
                    target['id'] = generate_id()
                    if ResourceQualityTool.objects.filter(target_id=target['targetId']).exists():
                        continue
                    targets.append(target)
            context['qualitytool_target_options'] = targets
        return context

    def get(self, request, *args, **kwargs):
        self.process_request(request, *args, **kwargs)
        return self.render_to_response(
            self.get_context_data(
                self.object
            )
        )

    def post(self, request, *args, **kwargs):
        self.process_request(request, *args, **kwargs)
        if not is_authenticated_user(self.user):
            return JsonResponse({'message': _('You are not authorized to create links')}, status=403)        
        payload = json.loads(request.body)

        try:
            self.validate(payload)
        except ValidationError as exc:
            return JsonResponse({'message': exc.message}, status=exc.code)

        resources = Resource.objects.filter(pk__in=payload['resources'])
        
        if not self.object:
            target_id = payload['target_id']
            name = payload['name']
            self.object = ResourceQualityTool(target_id=target_id)
            for lang, text in name.items():
                setattr(self.object, 'name_%s' % lang, text)
            self.object.save()
            for resource in resources:
                self.object.resources.add(resource)
            self.object.save()
        else:
            for resource in set(self.object.resources.all()) - set(resources):
                self.object.resources.remove(resource)
            for resource in resources:
                self.object.resources.add(resource)
            self.object.save()
        msg = _('Quality tool target created') if not self.is_edit else _('Quality tool target updated')
        self.set_session_context(request, redirect_message={
            'message': msg,
            'type': 'success'
        })
        
        return JsonResponse({
            'redirect_url': reverse('respa_admin:ra-qualitytool-edit', kwargs={'qualitytool_id': self.object.pk})
        })