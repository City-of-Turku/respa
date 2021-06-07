from django.db import models
from django.contrib.postgres.fields import JSONField
from django.utils.translation import ugettext_lazy as _
from resources.models.base import ModifiableModel
import uuid


class ServiceShortage(ModifiableModel):
    system_id = models.UUIDField(default=uuid.uuid4)
    service_requirement = models.ForeignKey('ServiceRequirement', on_delete=models.CASCADE, null=True, related_name='service_shortages')
    service_point = models.ForeignKey('ServicePoint', on_delete=models.CASCADE, null=True, related_name='service_shortages')
    viewpoint = models.PositiveIntegerField()
    shortage = models.CharField(max_length=255)

class ServiceRequirement(ModifiableModel):
    text = models.TextField(null=True, blank=False)
    is_indoor_requirement = models.BooleanField(null=True, blank=False)
    evaluation_zone = models.CharField(max_length=255)

class ServiceEntrance(ModifiableModel):
    system_id = models.UUIDField(default=uuid.uuid4)
    service_point = models.ForeignKey('ServicePoint', on_delete=models.CASCADE, null=True, related_name='service_entrances')
    is_main_entrance = models.BooleanField(default=False)
    location = JSONField(null=True, blank=True)
    name = models.CharField(max_length=255)
    photo_url = models.URLField(max_length=1000, null=True)
    street_view_url = models.URLField(max_length=1000, null=True)

    class Meta:
        ordering = ('id', )

class ServicePoint(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    code = models.PositiveIntegerField()
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ('code', )

class ServiceSentence(ModifiableModel):
    system_id = models.UUIDField(default=uuid.uuid4)
    service_point = models.ForeignKey(ServicePoint, on_delete=models.CASCADE, null=True, related_name='service_sentences')
    service_entrance = models.ForeignKey(ServiceEntrance, on_delete=models.CASCADE, null=True, related_name='service_sentences')
    sentence_group = models.ForeignKey('SentenceGroup', on_delete=models.SET_NULL, null=True, related_name='service_sentences')
    sentence_order_text = models.CharField(max_length=255, null=True, blank=True)



class SentenceGroup(models.Model):
    name = models.CharField(max_length=255)


class Sentence(models.Model):
    sentence = models.TextField()
    group = models.ForeignKey(SentenceGroup, on_delete=models.CASCADE, null=True, related_name='sentences')