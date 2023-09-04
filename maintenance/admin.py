from django import forms
from django.contrib import admin
from django.db.models import Q
from django.contrib.admin import site as admin_site
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from modeltranslation.admin import TranslationAdmin


from .models import MaintenanceMessage, MaintenanceMode


class MaintenanceModeAdmin(admin.ModelAdmin):
    pass

class MaintenanceModeInline(admin.TabularInline):
    model = MaintenanceMode
    fields = ('start', 'end', )
    verbose_name = _('maintenance mode')
    verbose_name_plural = _('maintenance modes')
    extra = 0


class MaintenanceMessageAdminForm(forms.ModelForm):
    class Meta:
        model = MaintenanceMessage
        fields = ('start', 'end', 'message', )

    def clean(self):
        start = self.cleaned_data['start']
        end = self.cleaned_data['end']
        query = Q(end__gt=start, start__lt=end)
        if self.instance and self.instance.pk:
            query &= ~Q(pk=self.instance.pk)
        collision = MaintenanceMessage.objects.filter(query)
        if collision.exists():
            raise ValidationError(_('maintenance message already exists.'))

class MaintenanceMessageAdmin(TranslationAdmin):
    form = MaintenanceMessageAdminForm
    inlines = ( MaintenanceModeInline, )
    fieldsets = (
        (_('General'), {
            'fields': (
                'start',
                'end',
                'message'
            ),
        }),
    )


admin_site.register(MaintenanceMessage, MaintenanceMessageAdmin)
admin_site.register(MaintenanceMode, MaintenanceModeAdmin)