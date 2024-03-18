import datetime


from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


from resources.models.base import ModifiableModel


class MaintenanceMessageQuerySet(models.QuerySet):
    def active(self):
        return self.filter(start__lt=timezone.now(), end__gt=timezone.now())

class MaintenanceMessage(ModifiableModel):
    message = models.TextField(verbose_name=_('Message'), null=False, blank=False)
    start = models.DateTimeField(verbose_name=_('Begin time'), null=False, blank=False)
    end = models.DateTimeField(verbose_name=_('End time'), null=False, blank=False)


    objects = MaintenanceMessageQuerySet.as_manager()
    class Meta:
        verbose_name = _('maintenance message')
        verbose_name_plural = _('maintenance messages')
        ordering = ('start', )


    def __str__(self):
        return f"{_('maintenance message')} \
                {timezone.localtime(self.start).replace(tzinfo=None)} - \
                {timezone.localtime(self.end).replace(tzinfo=None)}" \
                .capitalize()


    def clean(self):
        super().clean()
        if self.end <= self.start:
            raise ValidationError(_("Invalid start or end time"))

class MaintenanceModeQuerySet(models.QuerySet):
    def active(self):
        return self.filter(start__lt=timezone.now(), end__gt=timezone.now())


class MaintenanceMode(ModifiableModel):
    start = models.DateTimeField(verbose_name=_('Begin time'), null=False, blank=False)
    end = models.DateTimeField(verbose_name=_('End time'), null=False, blank=False)
    maintenance_message = models.ForeignKey(MaintenanceMessage, on_delete=models.CASCADE, null=True, blank=True)

    objects = MaintenanceModeQuerySet.as_manager()

    class Meta:
        verbose_name = _('maintenance mode')
        verbose_name_plural = _('maintenance modes')
        ordering = ('start', )

    def clean(self):
        super().clean()
        if self.end <= self.start:
            raise ValidationError(_("Invalid start or end time"))
