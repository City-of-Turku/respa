from django import forms
from django.db.models import Q
from django.contrib import admin
from django.contrib.admin import site as admin_site
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

from respa_admin.forms import ResourceForm
from respa_admin.models import DisabledFieldsSet


class DisabledFieldsForm(forms.ModelForm):
    class Meta:
        model = DisabledFieldsSet
        fields = ('name', 'resources', 'units', 'disabled_fields', )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['disabled_fields'].choices = sorted([(field, field) for field in ResourceForm.Meta.fields + ['groups', 'periods', 'images', 'free_of_charge']])
        self.fields['units'].queryset = self._get_unit_queryset()


    def _get_unit_queryset(self):
        return self.fields['units'].queryset.distinct()

    def clean_resources(self):
        resources = self.cleaned_data.get('resources', [])
        if not resources:
            return []
        query = Q(resources__in=resources)
        if self.instance and self.instance.pk:
            query &= ~Q(pk=self.instance.pk)  # Exclude ourselves from the query
        duplicates = DisabledFieldsSet.objects.filter(query).distinct()

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

    def clean_units(self):
        units = self.cleaned_data.get('units', [])
        if not units:
            return []
        query = Q(units__in=units)
        if self.instance and self.instance.pk:
            query &= ~Q(pk=self.instance.pk)  # Exclude ourselves from the query
        duplicates = DisabledFieldsSet.objects.filter(query).distinct()

        if duplicates.exists():
            msg = []
            for duplicate in duplicates:
                units = [unit for unit in duplicate.units.all() if unit in units]
                if units:
                    msg.append('<br/>'.join([unit.name for unit in units]))
            raise ValidationError(
                mark_safe('Duplicates found:<br/>%(duplicate)s<br/><br/>Found in set(s):<br/>%(set)s' % ({
                'duplicate': ''.join(msg),
                'set': '<br/>'.join([duplicate.name for duplicate in duplicates])
            })))
        return units

class DisabledFieldsSetAdmin(admin.ModelAdmin):
    form = DisabledFieldsForm
    fieldsets = (
        (_('General'), {
            'fields': (
                'name',
            )
        }),
        (_('Disabled for'), {
            'fields': (
                'resources',
                'units',
            ),
        }),
        (_('Fields'), {
            'fields': (
                'disabled_fields',
            ),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super(DisabledFieldsSetAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['resources'].widget.can_add_related = False
        form.base_fields['units'].widget.can_add_related = False
        return form




admin_site.register(DisabledFieldsSet, DisabledFieldsSetAdmin)