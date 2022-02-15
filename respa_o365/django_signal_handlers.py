import logging
from respa_o365.o365_notifications import O365Notifications
from respa_o365.o365_calendar import MicrosoftApi, O365Calendar

from django.db import transaction

from resources.models import Reservation
from respa_o365.calendar_sync import add_to_queue
from respa_o365.models import OutlookCalendarAvailability, OutlookCalendarReservation, OutlookCalendarLink
from respa_o365.sync_operations import ChangeType

logger = logging.getLogger(__name__)


def handle_reservation_save(instance, **kwargs):
    if getattr(instance, "_from_o365_sync", False):
        return
    links = OutlookCalendarLink.objects.filter(resource=instance.resource)
    for link in links:
        logger.info("Save of reservation, add sync of resource {} ({}) to queue".format(link.resource.name, link.resource.id))
        add_to_queue(link)

def handle_period_save(instance, **kwargs):
    if getattr(instance, "_from_o365_sync", False):
        return

    if OutlookCalendarLink.objects.filter(resource=instance.resource).exists():
        raise Exception("Editing the period directly is not allowed when the resource is connected to an Outlook calendar.")

def handle_calendar_link_delete(instance, **kwargs):
    logger.info("Removing calendar link for resource %s and calendar subscription %s", instance.resource_id, instance.exchange_subscription_id)
    # Clear outlook
    token = instance.token
    api = MicrosoftApi(token)
    notifications = O365Notifications(microsoft_api=api)
    notifications.delete(instance.exchange_subscription_id)
    cal = O365Calendar(microsoft_api=api)
    reservation_mappings = OutlookCalendarReservation.objects.filter(calendar_link_id=instance.id)
    for m in reservation_mappings:
        cal.remove_event(m.exchange_id)
    availabiltiy_mappings = OutlookCalendarAvailability.objects.filter(calendar_link_id=instance.id)
    for m in availabiltiy_mappings:
        cal.remove_event(m.exchange_id)
