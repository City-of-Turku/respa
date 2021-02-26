from django.conf import settings
from respa_o365.availability_sync_item import AvailabilitySyncItem
from respa_o365.o365_calendar import Event
from respa_o365.reservation_sync import SyncItemRepository

class O365AvailabilityRepository(SyncItemRepository):
    def __init__(self, o365_calendar):
        self._o365_calendar = o365_calendar

    def create_item(self, item):
        e = Event()
        e.begin = item.begin
        e.end = item.end
        e.subject = settings.O365_CALENDAR_AVAILABILITY_EVENT_PREFIX
        e.body = ''
        return self._o365_calendar.create_event(e)

    def set_item(self, item_id, item):
        e = self._o365_calendar.get_event(item_id)
        e.begin = item.begin
        e.end = item.end
        e.subject = settings.O365_CALENDAR_AVAILABILITY_EVENT_PREFIX
        e.body = ''
        return self._o365_calendar.update_event(item_id, e)

    def get_item(self, item_id):
        e = self._o365_calendar.get_event(item_id)
        if not e:
            return None
        item = AvailabilitySyncItem()
        item.begin = e.begin
        item.end = e.end
        return item

    def remove_item(self, item_id):
        self._o365_calendar.remove_event(item_id)

    def get_changes(self, memento=None):
        return self._o365_calendar.get_changes(memento)

    def get_changes_by_ids(self, item_ids, memento=None):
        return self._o365_calendar.get_changes_by_ids(item_ids, memento)

