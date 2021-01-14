import logging

from django.db import transaction

from resources.models import Reservation
from respa_o365.calendar_sync import perform_sync_to_exchange
from respa_o365.models import OutlookCalendarReservation, OutlookCalendarLink
from respa_o365.reservation_sync_operations import ChangeType

logger = logging.getLogger(__name__)


def handle_reservation_save(instance, **kwargs):
    if getattr(instance, "_from_o365_sync", False):
        return
    links = OutlookCalendarLink.objects.select_for_update().filter(resource=instance.resource)
    for link in links:
        logger.info("Save of reservation {} launch sync of {}".format(instance.id, link.id))
        perform_sync_to_exchange(link, lambda s: s.sync_all())
