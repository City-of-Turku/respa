import django.dispatch
from django.dispatch import receiver

reservation_confirmed = django.dispatch.Signal(['instance', 'user'])
reservation_modified = django.dispatch.Signal(['instance', 'user'])
reservation_cancelled = django.dispatch.Signal(['instance', 'user'])





@receiver(reservation_confirmed)
def handle_reservation_confirmed(sender, instance, user, **kwargs):
    if instance.resource.unit.sms_reminder and instance.reserver_phone_number:
        instance.create_reminder()

    if instance.resource.configuration:
        instance.resource.configuration.handle_create(instance)


@receiver(reservation_modified)
def handle_reservation_modified(sender, instance, user, **kwargs):
    if instance.resource.unit.sms_reminder and instance.reserver_phone_number:
        instance.modify_reminder()

    if instance.resource.configuration:
        instance.resource.configuration.handle_modify(instance)
