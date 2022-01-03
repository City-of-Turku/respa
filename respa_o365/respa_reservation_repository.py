import hashlib
import logging
from datetime import datetime, timezone, timedelta
from functools import reduce
from django.conf import settings
from django.contrib.auth import get_user_model

from resources.models import Reservation
from respa_o365.reservation_sync_item import model_to_item
from respa_o365.sync_operations import ChangeType

User = get_user_model()

logger = logging.getLogger(__name__)
time_format = '%Y-%m-%dT%H:%M:%S.%f%z'


class RespaReservations:
    def __init__(self, resource_id):
        self.__resource_id = resource_id
        self._start_date = (datetime.now(tz=timezone.utc) - timedelta(days=settings.O365_SYNC_DAYS_BACK)).replace(microsecond=0)
        self._end_date = (datetime.now(tz=timezone.utc) + timedelta(days=settings.O365_SYNC_DAYS_FORWARD)).replace(microsecond=0)

    def create_item(self, item):
        # Temporary logging code
        logger.info("Creating respa reservation in resource {} - email: {}, phone: {}, name: {}, begin: {}, end: {}, comments: {}".format(self.__resource_id, item.reserver_email_address, item.reserver_phone_number, item.reserver_name, item.begin, item.end, item.comments))
        reservation = Reservation()
        reservation.resource_id = self.__resource_id
        reservation.reserver_email_address = item.reserver_email_address
        reservation.reserver_phone_number = item.reserver_phone_number
        reservation.reserver_name = item.reserver_name
        reservation.comments = item.comments
        reservation.begin = item.begin
        reservation.end = item.end
        reservation._from_o365_sync = True
        reservation.set_state(Reservation.CONFIRMED, None)
        reservation.save()
        return reservation.id, reservation_change_key(item)

    def set_item(self, item_id, item):
        reservation = Reservation.objects.filter(id=item_id).first()
        # Temporary logging code
        logger.info("Updating respa reservation in resource {} ({})".format(reservation.resource.name, reservation.resource_id))
        logger.info("Before - email: {}, phone: {}, name: {}, begin: {}, end: {}, comments: {}".format(reservation.reserver_email_address, reservation.reserver_phone_number, reservation.reserver_name, reservation.begin, reservation.end, reservation.comments))
        logger.info("After  - email: {}, phone: {}, name: {}, begin: {}, end: {}, comments: {}".format(item.reserver_email_address, item.reserver_phone_number, item.reserver_name, item.begin, item.end, item.comments))
        reservation.reserver_email_address = item.reserver_email_address
        reservation.reserver_phone_number = item.reserver_phone_number
        reservation.reserver_name = item.reserver_name
        reservation.comments = item.comments
        reservation.begin = item.begin
        reservation.end = item.end
        reservation._from_o365_sync = True
        reservation.save()
        return reservation_change_key(item)

    def get_item(self, item_id):
        reservation = Reservation.objects.filter(id=item_id)
        return model_to_item(reservation.first())

    def remove_item(self, item_id):
        try:
            reservation = Reservation.objects.filter(id=item_id).first()
            # Temporary logging code
            logger.info("Removing respa reservation starting at {} in resource {} ({})".format(reservation.begin, reservation.resource.name, reservation.resource_id))
            reservation._from_o365_sync = True
            if reservation.state is not Reservation.CANCELLED:
                reservation.state = Reservation.CANCELLED
                reservation.send_reservation_cancelled_mail(action_by_official=True)
            reservation.save()
        except Exception:
            logger.error("Unable to cancel reservation {}".format(item_id), exc_info=True)

    def get_changes(self, memento=None):
        if memento:
            time = datetime.strptime(memento, time_format)
        else:
            time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        reservations = Reservation.objects.filter(resource_id=self.__resource_id, modified_at__gt=time)
        reservations = reservations.filter(end__range=(self._start_date, self._end_date))
        new_memento = reduce(lambda a, b: max(a, b.modified_at), reservations, time)
        return {r.id: (status(r, time), reservation_change_key(r)) for r in reservations}, new_memento.strftime(time_format)

    def get_changes_by_ids(self, item_ids, memento=None):
        reservations = Reservation.objects.filter(id__in=item_ids)
        if memento:
            time = datetime.strptime(memento, time_format)
        else:
            time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        new_memento = reduce(lambda a, b: max(a, b.modified_at), reservations, time)
        return {r.id: (status(r, time), reservation_change_key(r)) for r in reservations}, new_memento.strftime(time_format)


def status(reservation, time):
    # XXX: This method is debug code for logging purposes
    status = _status(reservation, time)
    logger.info("Respa reservation starting at {} in resource {} ({}) has status {} since {}. Last modified at {}".format(reservation.begin, reservation.resource.name, reservation.resource.id, status, time, reservation.modified_at))
    return status

def _status(reservation, time):
    if reservation.modified_at <= time:
        return ChangeType.NO_CHANGE
    if reservation.state in [Reservation.CANCELLED, Reservation.DENIED]:
        return ChangeType.DELETED
    if reservation.created_at > time:
        return ChangeType.CREATED
    return ChangeType.UPDATED


def reservation_change_key(item):
    s = "{} -- {} name: {} email: {} phone: {}".format(
        item.begin,
        item.end,
        item.reserver_name,
        item.reserver_email_address,
        item.reserver_phone_number)
    return hashlib.md5(s.encode("utf-8")).hexdigest()
