
from django import forms
from django.db.models import Q
from django.contrib.postgres.fields import ArrayField
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from resources.models.base import AutoIdentifiedModel


class ChoiceArrayField(ArrayField):
    def formfield(self, **kwargs):
        return super(ArrayField, self).formfield(**{
            'form_class': forms.MultipleChoiceField,
            'choices': self.base_field.choices,
            **kwargs
        })


class DisabledFieldsSet(AutoIdentifiedModel):
    name = models.CharField(verbose_name=_('Name'), max_length=255, null=False, blank=False)
    disabled_fields = ChoiceArrayField(
        base_field=models.CharField(max_length=256, choices=[]),
        verbose_name=_('disabled fields'),
        default=list, blank=True, null=True)
    resources = models.ManyToManyField('resources.Resource', blank=True,
        limit_choices_to={'is_external': True},
        related_name='disabled_fields_set',
        verbose_name=_('resources'),
        help_text=_('If selected, fields will be disabled for selected resources only, takes priority over unit.'))
    units = models.ManyToManyField('resources.Unit', blank=True,
        limit_choices_to={'resources__is_external':True},
        related_name='disabled_fields_set',
        verbose_name=_('units'),
        help_text=_('If selected, fields will be disabled for all resources that belong to the selected units.'))

    class Meta:
        verbose_name = _('disabled field set')
        verbose_name_plural = _('disabled fields set')


    def __str__(self):
        return self.name
