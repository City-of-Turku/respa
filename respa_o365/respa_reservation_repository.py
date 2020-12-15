from datetime import datetime, timezone, timedelta
from functools import reduce

from resources.models import Reservation
from respa_o365.reservation_sync_item import model_to_item
from respa_o365.reservation_sync_operations import ChangeType


time_format = '%Y-%m-%dT%H:%M:%S.%f%z'


class RespaReservations:
    # TODO Do not consider old items (e.g. items that ended over week ago)
    # TODO Implement change key calculations
    def __init__(self, resource_id):
        self.__resource_id = resource_id

    def create_item(self, item):
        reservation = Reservation.objects.create(
            resource=self.__resource_id,
            begin=item.begin,
            end=item.end,
            reserver_name=item.reserver_name,
            reserver_phone_number=item.reserver_phone_number,
            reserver_email_address=item.reserver_email_address,
            state=Reservation.CONFIRMED
        )
        return reservation.id, ""

    def set_item(self, item_id, item):
        reservation = Reservation.objects.filter(id=item_id).first()
        # TODO Check if name can actually be altered
        reservation.reserver_email_address = item.reserver_email_address
        reservation.reserver_phone_number = item.reserver_phone_number
        reservation.reserver_name = item.reserver_name
        reservation.begin = item.begin
        reservation.end = item.end
        reservation.save()
        return ""

    def get_item(self, item_id):
        reservation = Reservation.objects.filter(id=item_id)
        return model_to_item(reservation.first())

    def remove_item(self, item_id):
        pass

    def get_changes(self, memento=None):
        if memento:
            time = datetime.strptime(memento, time_format)
        else:
            time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        reservations = Reservation.objects.filter(resource=self.__resource_id, modified_at__gt=time)
        new_memento = reduce(lambda a, b: max(a, b.modified_at), reservations, time)
        return {r.id: (status(r, time), "") for r in reservations}, new_memento.strftime(time_format)

    def get_changes_by_id(self, item_ids, memento=None):
        reservations = Reservation.objects.filter(id__in=item_ids)
        if memento:
            time = datetime.strptime(memento, time_format)
        else:
            time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        new_memento = reduce(lambda a, b: max(a, b.modified_at), reservations, time)
        return {r.id: (status(r, time), "") for r in reservations}, new_memento.strftime(time_format)

def status(reservation, time):
    if reservation.modified_at <= time:
        return ChangeType.NO_CHANGE
    if reservation.state in [Reservation.CANCELLED, Reservation.DENIED]:
        return ChangeType.DELETED
    if reservation.created_at > time:
        return ChangeType.CREATED
    return ChangeType.UPDATED
