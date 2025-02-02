import re

from django.conf import settings
from django.contrib.gis.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from .utils import generate_id


class AutoIdentifiedModel(models.Model):

    def save(self, *args, **kwargs):
        pk_type = self._meta.pk.get_internal_type()
        if pk_type == 'CharField':
            if not self.pk:
                self.pk = generate_id()
        elif pk_type == 'AutoField':
            pass
        else:
            raise Exception('Unsupported primary key field: %s' % pk_type)
        super().save(*args, **kwargs)

    class Meta:
        abstract = True


class NameIdentifiedModel(models.Model):

    def save(self, *args, **kwargs):
        pk_type = self._meta.pk.get_internal_type()
        if pk_type == 'CharField':
            if not self.pk:
                if self.name_en:
                    self.pk = slugify(self.name_en)
                else:
                    self.pk = slugify(self.name_fi)
        elif pk_type == 'AutoField':
            pass
        else:
            raise Exception('Unsupported primary key field: %s' % pk_type)
        super().save(*args, **kwargs)

    class Meta:
        abstract = True


class ModifiableModel(models.Model):
    created_at = models.DateTimeField(verbose_name=_('Time of creation'), default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('Created by'),
                                   null=True, blank=True, related_name="%(class)s_created",
                                   on_delete=models.SET_NULL)
    modified_at = models.DateTimeField(verbose_name=_('Time of modification'), default=timezone.now)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('Modified by'),
                                    null=True, blank=True, related_name="%(class)s_modified",
                                    on_delete=models.SET_NULL)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """ Updated modified timestamp on save"""
        self.modified_at = timezone.now()
        return super(ModifiableModel, self).save(*args, **kwargs)


class ValidatedIdentifier(models.Model):
    class Meta:
        abstract = True


    def clean(self):
        pk_type = self._meta.pk.get_internal_type()
        if pk_type == 'CharField' and self.pk:
            self.validate_id()

    def validate_id(self):
        if len(self.id) <= 5:
            raise ValidationError({
                'id': _('Id must be longer than 5 letters')
            })

        if re.search(r'[^0-9a-zA-Z_]+', self.id):
            raise ValidationError({
                'id': _('Invalid characters in id')
            })

        if self.id[0].isdigit():
            raise ValidationError({
                'id': _('Id cannot start with a number')
            })
        if self.id.startswith('_'):
            raise ValidationError({
                'id': _('Id cannot start with an underscore')
            })

        if re.search(r'_{2,}', self.id):
            raise ValidationError({
                'id': _('Consecutive underscore characters is not allowed')
            })
