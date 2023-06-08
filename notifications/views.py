from django.utils.translation import gettext as _
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from django.http import JsonResponse, Http404
from django.views.generic.base import TemplateView, View
from django.db.models import Q
from respa_admin.views.base import ExtraContextMixin
from resources.models.utils import generate_id
from resources.auth import is_superuser
import json

from notifications.models import NotificationTemplate, DEFAULT_LANG



IGNORED_TEMPLATE_NAMES = (
    '.gitkeep',
    '.gitignore'
)

LANGUAGES = [lang for lang, _ in settings.LANGUAGES]


class NotificationTemplateValidationError(Exception):
    pass

class NotificationTemplateBase(ExtraContextMixin):
    def _process_list_view(self, request, *args, **kwargs):
        self.object = None
        self._page_title = ''
        self.is_edit = False
    
    def _process_detail_view(self, request, *args, **kwargs):
        if self.pk_url_kwarg in kwargs:
            self.object = self.get_object()
            self._page_title = _('Edit notification template')
        else:
            self._page_title = _('Create notification template')
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


class NotificationTemplateBaseView(NotificationTemplateBase, View):
    context_object_name = 'notification_template'
    model = NotificationTemplate

    def dispatch(self, request, *args, **kwargs):
        if not is_superuser(request.user):
            raise Http404
        return super().dispatch(request, *args, **kwargs)
    

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = self.is_edit
        context['page_title'] = self._page_title
        context['random_id_str'] = generate_id()
        if self.session_context:
            context['notification_redirect_context'] = self.session_context['redirect_message']
        return context
    

    def post(self, request, *args, **kwargs):
        raise NotImplementedError()
    
    def get(self, request, *args, **kwargs):
        self.process_request(request, *args, **kwargs)
        return super().get(request, *args, **kwargs)


class NotificationTemplateImportView(NotificationTemplateBaseView):
    def post(self, request, *args, **kwargs):
        self.process_request(request, *args, **kwargs)

        notification_templates = request.FILES.getlist('notification_templates')

        templates =  {}

        for template in notification_templates:
            if template.name in IGNORED_TEMPLATE_NAMES:
                continue
            language, type = template.name.strip().split('-')
            type = type.replace('.html', '')
            html_body = template.read().decode('utf-8')
            if type not in templates:
                templates.update({
                    type: { language: html_body }
                })
            else:
                templates[type].update({ language: html_body })
        
        invalid_templates = []

        for type, template in templates.items():
            notification_templates = NotificationTemplate.objects.filter(type=type)

            if not notification_templates.exists():
                invalid_templates.append(type)
                continue

            for notification_template in notification_templates:
                for language, html_body in template.items():
                    notification_template.set_current_language(language)
                    notification_template.html_body = html_body
                notification_template.save()


        if invalid_templates:
            msg = _('Some notification templates have missing entries')
        else:
            msg = _('Notification templates imported')


        self.set_session_context(request, redirect_message={
            'message': msg,
            'type': 'success' if not invalid_templates else 'error'
        })


        return redirect('respa_admin:ra-notifications')



class NotificationTemplateListView(
    NotificationTemplateBaseView, TemplateView):
    template_name = 'respa_admin/page_notification_templates.html'


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['notifications'] = NotificationTemplate.objects.all().distinct()
        return context

class NotificationTemplateManagementView(NotificationTemplateBaseView, TemplateView):
    template_name = 'respa_admin/notifications/_manage_notification_template.html'
    pk_url_kwarg = 'notification_id'

    class Meta:
        fields = (
            'type', 'name',
            'is_default_template'
        )
        required_fields = (
            'type',
            'subject'
        )
        translated_fields = (
            'subject',
            'body',
            'html_body',
            'short_message'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['instance'] = self.object
        context['NOTIFICATION_TYPES'] = NotificationTemplate.NOTIFICATION_TYPE_CHOICES
        context['DEFAULT_LANG'] = DEFAULT_LANG
        return context
    
    def validate(self, attr):
        for field in self.Meta.required_fields:
            value = attr.get(field)
            if not isinstance(value, dict):
                if not value:
                    raise NotificationTemplateValidationError('Field: %s is required' % field)
            else:
                for lang in LANGUAGES:
                    if not value.get(lang):
                        raise NotificationTemplateValidationError('Translated field: %s: "%s" is required.' % (field, lang))
            

    def get_fields(self, data):
        translated = {}
        normals = {}
        for lang in LANGUAGES:
            for field in self.Meta.translated_fields:
                if field not in translated:
                    translated[field] = {}
                translated[field].update({ lang: data.get('%s_%s' % (field, lang))})
        
        for field in self.Meta.fields:
            normals.update({ field: data.get(field) })

        return {**normals, **translated}

    def post(self, request, *args, **kwargs):
        self.process_request(request, *args, **kwargs)
        payload = self.get_fields(request.POST)
        try:
            self.validate(payload)
        except NotificationTemplateValidationError as exc:
            self.set_session_context(request, redirect_message={
                'message': '%(message)s %(extra)s' % {
                    'message': _('Failed to create notification template') if not self.object else  _('Failed to update notification template'),
                    'extra': str(exc)
                },
                'type':'error'
            })
            if self.object:
                return redirect('respa_admin:ra-notifications-edit', notification_id = self.object.pk)
            else:
                return redirect('respa_admin:ra-notifications-create')

        payload['is_default_template'] = bool(payload['is_default_template'])
        
        try:
            notification_template = self.object or NotificationTemplate()

            for field in self.Meta.fields:
                value = payload[field]
                if isinstance(value, str):
                    value = value.strip()
                setattr(notification_template, field, value)

            
            for language in LANGUAGES:
                notification_template.set_current_language(language)
                for field in self.Meta.translated_fields:
                    translated_field = payload.get(field)
                    setattr(notification_template, field, translated_field.get(language).strip())
            
            notification_template.save()
            self.set_session_context(request, redirect_message={
                'message': _('Notification template created') if not self.object else _('Notification template updated'),
                'type':'success'
            })
            return redirect('respa_admin:ra-notifications-edit', notification_id = notification_template.pk)
        except:
            self.set_session_context(request, redirect_message={
                'message': _('Failed to create notification template') if not self.object else  _('Failed to update notification template'),
                'type':'error'
            })
            if self.object:
                return redirect('respa_admin:ra-notifications-edit', notification_id = self.object.pk)
            return redirect('respa_admin:ra-notifications-create')


class NotificationTemplateRemoveView(NotificationTemplateBaseView):
    pk_url_kwarg = 'notification_id'

    def post(self, request, *args, **kwargs):
        self.process_request(request, *args, **kwargs)
        instance = self.get_object()

        if not is_superuser(self.user):
            self.set_session_context(request, redirect_message={
                'message':_('You must be a superuser to delete notification template.'),
                'type':'error'
            })
        else:
            instance.delete()
            self.set_session_context(request, redirect_message={
                'message': _('Notification template removed'),
                'type':'success'
            })
        return redirect('respa_admin:ra-notifications')