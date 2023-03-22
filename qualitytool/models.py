from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django_jsonform.models.fields import ArrayField
from django.utils.functional import lazy
from solo.models import SingletonModel
from qualitytool.manager import qt_manager
from respa_admin.models import ChoiceArrayField


def get_form_defaults():
    return [lang for lang, _ in settings.LANGUAGES]

class ResourceQualityToolQuerySet(models.QuerySet):
    def filter(self, *args, **kwargs):
        return super(ResourceQualityToolQuerySet, self).filter(*args, **kwargs).distinct()
    def all(self):
        return super(ResourceQualityToolQuerySet, self).all().distinct()

class ResourceQualityTool(models.Model):
    name = models.CharField(verbose_name=_('Name'), max_length=255)
    target_id = models.UUIDField(verbose_name=_('Target ID'), unique=True, primary_key=True)
    resources = models.ManyToManyField('resources.Resource', verbose_name=_('Resources'), related_name='qualitytool')
    emails = ArrayField(
        models.EmailField(verbose_name=_('Email'), max_length=255),
        null=True, blank=True
    )
    objects = ResourceQualityToolQuerySet.as_manager()

    class Meta:
        verbose_name = _('resource quality tool')
        verbose_name_plural = _('resource quality tools')

    def __str__(self):
        return '(%s) %s - %s' % (self.resources.count(), self.name, self.target_id)

    def get_unit(self):
        return self.resources.first().unit


class QualityToolFormLanguageOptions(SingletonModel):
    options = ChoiceArrayField(
        models.CharField(choices=settings.LANGUAGES, max_length=255), 
        verbose_name=_('Form options'), default=get_form_defaults,
        override_choices = lambda: qt_manager.get_form_languages()
    )


    def __init__(self, *args, **kwargs):
        super(QualityToolFormLanguageOptions, self).__init__(*args, **kwargs)



    def __str__(self):
        return _('Quality tool form options configuration.')

    class Meta:
        verbose_name = _('Quality tool form configuration')
