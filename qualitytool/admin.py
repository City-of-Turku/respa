from django import forms
from django.contrib import admin
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from modeltranslation.admin import TranslationAdmin
from solo.admin import SingletonModelAdmin
from qualitytool.models import ResourceQualityTool, QualityToolFormLanguageOptions


class ResourceQualityToolAdminForm(forms.ModelForm):
    class Meta:
        model = ResourceQualityTool
        fields = ( 'name', 'target_id', 'resources', 'emails', )

    def clean_resources(self):
        resources = self.cleaned_data.get('resources', [])
        if not resources:
            return []
        query = Q(resources__in=resources)
        if self.instance and self.instance.pk:
            query &= ~Q(pk=self.instance.pk)  # Exclude ourselves from the query
        duplicates = ResourceQualityTool.objects.filter(query).distinct()

        if duplicates.exists():
            msg = []
            for duplicate in duplicates:
                resources = [resource for resource in duplicate.resources.all() if resource in resources]
                if resources:
                    msg.append('<br/>'.join([resource.name for resource in resources]))
            raise ValidationError(
                mark_safe('Duplicates found:<br/>%(duplicate)s<br/><br/>Found in set(s):<br/>%(set)s' % ({
                'duplicate': ''.join(msg),
                'set': '<br/>'.join([duplicate.name for duplicate in duplicates])
            })))
        return resources

class ResourceQualityToolAdmin(TranslationAdmin):
    form = ResourceQualityToolAdminForm
    list_display = ( 'name' , 'count', 'target_id')
    filter_horizontal = ( 'resources', )

    fieldsets = (
        (_('General'), {
            'fields': (
                'name',
                'target_id',
                'emails',
            ),
        }),
        (_('Resources'), {
            'fields': (
                'resources',
            ),
        }),
    )

    def count(self, obj):
        return obj.resources.count()
    count.verbose_name = _('Count')


class QualityToolFormLanguageOptionsAdmin(SingletonModelAdmin):
    pass




admin.site.register(QualityToolFormLanguageOptions,
    QualityToolFormLanguageOptionsAdmin)
admin.site.register(ResourceQualityTool, ResourceQualityToolAdmin)