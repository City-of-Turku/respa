from datetime import datetime, timezone, timedelta
from functools import reduce
from django.conf import settings

from resources.models import Reservation
from respa_o365.reservation_sync_item import model_to_item
from respa_o365.sync_operations import ChangeType


time_format = '%Y-%m-%dT%H:%M:%S.%f%z'


class RespaReservations:
    def __init__(self, resource_id):
        self.__resource_id = resource_id
        self._start_date = (datetime.now(tz=timezone.utc) - timedelta(days=settings.O365_SYNC_DAYS_BACK)).replace(microsecond=0)
        self._end_date = (datetime.now(tz=timezone.utc) + timedelta(days=settings.O365_SYNC_DAYS_FORWARD)).replace(microsecond=0)

    def create_item(self, item):
        reservation = Reservation()
        reservation.resource_id = self.__resource_id
        reservation.state = Reservation.CONFIRMED
        reservation.reserver_email_address = item.reserver_email_address
        reservation.reserver_phone_number = item.reserver_phone_number
        reservation.reserver_name = item.reserver_name
        reservation.begin = item.begin
        reservation.end = item.end
        reservation._from_o365_sync = True
        reservation.save()
        return reservation.id, reservation_change_key(item)

    def set_item(self, item_id, item):
        reservation = Reservation.objects.filter(id=item_id).first()
        reservation.reserver_email_address = item.reserver_email_address
        reservation.reserver_phone_number = item.reserver_phone_number
        reservation.reserver_name = item.reserver_name
        reservation.begin = item.begin
        reservation.end = item.end
        reservation._from_o365_sync = True
        reservation.save()
        return reservation_change_key(item)

    def get_item(self, item_id):
        reservation = Reservation.objects.filter(id=item_id)
        return model_to_item(reservation.first())

    def remove_item(self, item_id):
        reservation = Reservation.objects.filter(id=item_id).first()
        if not Reservation:
            return
        reservation.state = Reservation.CANCELLED
        reservation._from_o365_sync = True
        reservation.save()

    def get_changes(self, memento=None):
        if memento:
            time = datetime.strptime(memento, time_format)
        else:
            time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        reservations = Reservation.objects.filter(resource_id=self.__resource_id, modified_at__gt=time)
        reservations = reservations.filter(begin__range=(self._start_date, self._end_date))
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
    if reservation.modified_at <= time:
        return ChangeType.NO_CHANGE
    if reservation.state in [Reservation.CANCELLED, Reservation.DENIED]:
        return ChangeType.DELETED
    if reservation.created_at > time:
        return ChangeType.CREATED
    return ChangeType.UPDATED


def reservation_change_key(item):
    h = hash(item.reserver_name) ^ 3 * hash(item.reserver_email_address) ^ 7 * hash(item.reserver_phone_number)
    h = h ^ 11 * hash(item.begin.timestamp())
    h = h ^ 13 * hash(item.end.timestamp())
    return str(h)
