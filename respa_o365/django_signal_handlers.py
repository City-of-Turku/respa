import logging

from django.db import transaction

from resources.models import Reservation
from respa_o365.calendar_sync import perform_sync_to_exchange
from respa_o365.models import OutlookCalendarReservation
from respa_o365.reservation_sync_operations import ChangeType

logger = logging.getLogger(__name__)


def handle_reservation_save(instance, **kwargs):
    if getattr(instance, "_from_o365_sync", False):
        return

    with transaction.atomic():
        mappings = OutlookCalendarReservation.objects.filter(reservation_id=instance.id)
        for mapping in mappings:
            link = mapping.calendar_link
            logger.info("Save of reservation {} launch sync of {}", instance.id, link.id)
            if instance.state == Reservation.CANCELLED:
                perform_sync_to_exchange(link, lambda s: s.sync({instance.id: ChangeType.DELETED}, {}))
            else:
                perform_sync_to_exchange(link, lambda s: s.sync({instance.id: ChangeType.UPDATED}, {}))
