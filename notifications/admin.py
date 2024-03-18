import logging
import json
from parler.admin import TranslatableAdmin
from parler.forms import TranslatableModelForm
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django import forms
from django.contrib import admin
from django.contrib.admin import site as admin_site
from django.utils.translation import gettext_lazy as _
from django.urls import path, reverse
from django.shortcuts import render
from django.http import HttpResponseRedirect, HttpResponse
from .models import NotificationTemplate, NotificationTemplateGroup
from resources.admin.base import PopulateCreatedAndModifiedMixin, CommonExcludeMixin

logger = logging.getLogger(__name__)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result


class HtmlTemplateUpdateForm(forms.Form):
    html_files = MultipleFileField(label=_('HTML files'))


class NotificationTemplateForm(TranslatableModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class NotificationGroupForm(forms.ModelForm):
    class Meta:
        model = NotificationTemplateGroup
        fields = ['identifier', 'name', 'templates']

    def clean(self):
        # Raise ValidationError if one tries to add a notification template to a group that already contains a template of that type.
        # A template group cannot contain multiples of one type.
        all_new_templates = self.cleaned_data['templates'].values_list('type', flat=True)
        distinct_new_templates = all_new_templates.distinct()
        if all_new_templates.count() != distinct_new_templates.count():
            logger.info("Attempted to add a notification template to template group that already contains a template of that type.")
            raise ValidationError('Template group cannot contain multiple templates of the same type.')


class NotificationGroupAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin,
                             admin.ModelAdmin):
    form = NotificationGroupForm


class NotificationTemplateAdmin(TranslatableAdmin):
    #
    # When attempting to save, validate Jinja templates based on
    # example data. Possible to get an exception if unknown context
    # variables are accessed?
    #
    form = NotificationTemplateForm
    change_form_template = 'admin/html_preview.html'
    actions = ['update_notification_html_templates']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('update_notification_html_templates/', self.admin_site.admin_view(self.update_notification_html_templates_view),
                 name='update_notification_html_templates'),
        ]
        return custom_urls + urls

    def update_notification_html_templates_view(self, request):
        if request.method == 'POST':
            form = HtmlTemplateUpdateForm(request.POST, files=request.FILES)
            if form.is_valid():
                html_files = form.cleaned_data['html_files']
                queryset_data = request.POST.get('queryset_data', '[]')
                template_object_ids = json.loads(queryset_data)
                call_command('upload_html_templates', template_object_ids=template_object_ids,
                             html_files=html_files, stdout=HttpResponse())
                self.message_user(request, _("HTML templates updated for selected notifications."))
                return HttpResponseRedirect(reverse('admin:notifications_notificationtemplate_changelist'))
        else:
            form = HtmlTemplateUpdateForm()

        queryset_data = request.GET.get('queryset_data', '[]')
        initial_queryset = json.loads(queryset_data)
        context = self.admin_site.each_context(request)
        context['form'] = form
        context['initial_queryset'] = initial_queryset
        return render(request, 'admin/update_notification_html_form.html', context)

    def update_notification_html_templates(self, request, queryset):
        serialized_queryset = self.serialize_queryset(queryset)
        redirect_url = reverse('admin:update_notification_html_templates') + f'?queryset_data={serialized_queryset}'
        return HttpResponseRedirect(redirect_url)

    def serialize_queryset(self, queryset):
        return json.dumps(list(queryset.values_list('pk', flat=True)))

    update_notification_html_templates.short_description = _('Update notification HTML templates')


admin_site.register(NotificationTemplateGroup, NotificationGroupAdmin)
admin_site.register(NotificationTemplate, NotificationTemplateAdmin)
