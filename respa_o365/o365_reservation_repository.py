from bs4 import BeautifulSoup
from soupsieve.css_parser import COMMENTS
from django.conf import settings
from respa_o365.o365_calendar import Event
from respa_o365.reservation_sync import SyncItemRepository
from respa_o365.reservation_sync_item import ReservationSyncItem

class O365ReservationRepository(SyncItemRepository):
    def __init__(self, o365_calendar):
        self._o365_calendar = o365_calendar

    def create_item(self, item):
        e = Event()
        e.begin = item.begin
        e.end = item.end
        e.subject = settings.O365_CALENDAR_RESERVATION_EVENT_PREFIX
        e.body = format_reserver_info(item)
        return self._o365_calendar.create_event(e)

    def set_item(self, item_id, item):
        e = self._o365_calendar.get_event(item_id)
        e.begin = item.begin
        e.end = item.end
        e.subject = settings.O365_CALENDAR_RESERVATION_EVENT_PREFIX
        e.body = format_reserver_info(item)
        return self._o365_calendar.update_event(item_id, e)

    def get_item(self, item_id):
        e = self._o365_calendar.get_event(item_id)
        if not e:
            return None
        item = ReservationSyncItem()
        item.begin = e.begin
        item.end = e.end
        reserver_info = parse_reserver_info(e.body)
        item.reserver_name = reserver_info.get('name', '')
        item.reserver_phone_number = reserver_info.get('phone_number', '')
        item.reserver_email_address = reserver_info.get('email_address', '')
        return item

    def remove_item(self, item_id):
        self._o365_calendar.remove_event(item_id)

    def get_changes(self, memento=None):
        return self._o365_calendar.get_changes(memento)

    def get_changes_by_ids(self, item_ids, memento=None):
        return self._o365_calendar.get_changes_by_ids(item_ids, memento)

def parse_reserver_info(event_body):
    reserver_info = {}
    soup = BeautifulSoup(event_body, 'html.parser')
    next = None
    for string in soup.stripped_strings:
        if next == 'name':
            reserver_info['name'] = string
            next = 'email'
            continue
        elif next == 'email':
            reserver_info['email_address'] = string
            next = 'phone'
            continue
        elif next == 'phone':
            reserver_info['phone_number'] = string
            next = 'done'
            continue
        elif next == 'done':
            # TODO: ability to add comments
            continue
        if string == "Varaaja:":
            next = 'name'

    return reserver_info

def format_reserver_info(sync_item):
    return (f"<div>Varaaja:<br></div>"
            f"<div>{sync_item.reserver_name}</div>"
            f"<div>{sync_item.reserver_email_address}</div>"
            f"<div>{sync_item.reserver_phone_number}</div>")
