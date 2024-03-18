from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .base import AutoIdentifiedModel, ModifiableModel

# Types that are currently supported.
TYPE_CHOICES = (('Select','Select'),)

class UniversalFormFieldType(ModifiableModel, AutoIdentifiedModel):
    id = models.CharField(primary_key=True, max_length=100)
    type = models.CharField(verbose_name=_('Type'), max_length=200, choices=TYPE_CHOICES)

    class Meta:
        verbose_name = _('universal form field type')
        verbose_name_plural =_('universal form field types')
    
    def __str__(self):
        return self.type
