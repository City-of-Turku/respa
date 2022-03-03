import logging
from datetime import date, datetime, timedelta
from functools import reduce
from django.conf import settings
from django.utils import timezone

from resources.models import Period, Day, Resource
from respa_o365.availability_sync_item import period_to_item
from respa_o365.sync_operations import ChangeType

logger = logging.getLogger(__name__)

time_format = '%Y-%m-%dT%H:%M:%S.%f%z'

# We detect period changes only on the Outlook side, so the change key for Respa periods cna always be the same.
period_change_key = '0'

class RespaAvailabilityRepository:

    def __init__(self, resource_id):
        self.__resource_id = resource_id
        self._start_date = (datetime.now(tz=timezone.utc) - timedelta(days=settings.O365_SYNC_DAYS_BACK)).replace(microsecond=0)
        self._end_date = (datetime.now(tz=timezone.utc) + timedelta(days=settings.O365_SYNC_DAYS_FORWARD)).replace(microsecond=0)

    def create_item(self, item):
        period = Period()
        period.resource_id = self.__resource_id
        period.start = naive_date(item.begin)
        period.end = naive_date(item.end)
        period._from_o365_sync = True
        period.save()
        Day.objects.create(closed=False, weekday=item.begin.weekday(), opens=naive_time(item.begin), closes=fixed_end_time(item.end), period=period)
        period.save()
        Resource.objects.get(pk=self.__resource_id).update_opening_hours()
        return period.id, period_change_key

    def set_item(self, item_id, item):
        period = Period.objects.get(id=item_id)
        Day.objects.filter(period=period).delete()
        period.start = naive_date(item.begin)
        period.end = naive_date(item.end)
        period._from_o365_sync = True
        Day.objects.create(closed=False, weekday=item.begin.weekday(), opens=naive_time(item.begin), closes=fixed_end_time(item.end), period=period)
        period.save()
        Resource.objects.get(pk=self.__resource_id).update_opening_hours()
        return period_change_key

    def get_item(self, item_id):
        period = Period.objects.filter(id=item_id)
        return period_to_item(period.first())

    def remove_item(self, item_id):
        try:
            period = Period.objects.get(id=item_id)
            period._from_o365_sync = True
            period.delete()
            Resource.objects.get(pk=self.__resource_id).update_opening_hours()
        except Exception:
            logger.error("Failed deleting period {}".format(item_id), exc_info=True)

    def get_changes(self, memento=None):
        logger.debug("get_changes")
        # Changing periods through other means is prevented when there are calendar links connected to the resource.
        # For this reason, the periods do not change on the Respa side.
        if not memento:
            memento = datetime(1970, 1, 1, tzinfo=timezone.utc).strftime(time_format)
        return {}, memento

    def get_changes_by_ids(self, item_ids, memento=None):
        logger.debug("get_changes_by_ids")
        # Changing periods through other means is prevented when there are calendar links connected to the resource.
        # For this reason, the periods do not change on the Respa side.
        periods = Period.objects.filter(id__in=item_ids)
        if not memento:
            memento = datetime(1970, 1, 1, tzinfo=timezone.utc).strftime(time_format)
        return {p.id: (ChangeType.NO_CHANGE, period_change_key) for p in periods}, memento

def naive_time(datetime):
    return timezone.make_naive(datetime).time()

def naive_date(datetime):
    return timezone.make_naive(datetime).date()

def fixed_end_time(datetime):
    end_time = naive_time(datetime)
    if end_time.hour == 0 and end_time.minute == 0 and end_time.second == 0:
        end_time = naive_time(datetime - timedelta(seconds=1))
    return end_time


