import re
from bs4 import BeautifulSoup
from soupsieve.css_parser import COMMENTS
from django.conf import settings
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError

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
        e.body = format_event_body(item)
        return self._o365_calendar.create_event(e)

    def set_item(self, item_id, item):
        e = self._o365_calendar.get_event(item_id)
        e.begin = item.begin
        e.end = item.end
        e.subject = settings.O365_CALENDAR_RESERVATION_EVENT_PREFIX
        e.body = format_event_body(item)
        return self._o365_calendar.update_event(item_id, e)

    def get_item(self, item_id):
        e = self._o365_calendar.get_event(item_id)
        if not e:
            return None
        item = ReservationSyncItem()
        item.begin = e.begin
        item.end = e.end
        reservation_info = ReservationBody(e.body)
        item.reserver_name = reservation_info.reserver_name
        item.reserver_phone_number = reservation_info.reserver_phone_number
        item.reserver_email_address = reservation_info.reserver_email_address
        item.comments = reservation_info.comments
        return item

    def remove_item(self, item_id):
        self._o365_calendar.remove_event(item_id)

    def get_changes(self, memento=None):
        return self._o365_calendar.get_changes(memento)

    def get_changes_by_ids(self, item_ids, memento=None):
        return self._o365_calendar.get_changes_by_ids(item_ids, memento)

class ReservationBody:
    def __init__(self, event_body):
        self.reserver_name = ''
        self.reserver_email_address = ''
        self.reserver_phone_number = ''
        self.comments = ''
        self.parse(event_body)

    def parse(self, event_body):
        soup = BeautifulSoup(event_body, 'html.parser')
        strings = list(soup.stripped_strings)

        reserver_info_index = None
        comments_index = None

        # Find start of reserver info and comments
        for index, string in enumerate(strings):
            if re.match(settings.O365_CALENDAR_COMMENTS_MARK, string, re.I):
                comments_index = index + 1
                break # The rest of the message is comments.

            if re.match(settings.O365_CALENDAR_RESERVER_INFO_MARK, string, re.I) and reserver_info_index is None:
                    reserver_info_index = index + 1

        if reserver_info_index is not None:
            for index in range(reserver_info_index, reserver_info_index+3):
                try:
                    string = strings[index]
                except IndexError:
                    break

                if index == reserver_info_index:
                    self.reserver_name = string
                    continue
                elif is_phone_number(string):
                    self.reserver_phone_number = string
                    continue
                elif is_email_address(string):
                   self.reserver_email_address = string

            if comments_index is not None:
                for string in strings[comments_index:]:
                    self.comments = self.comments + string

def format_event_body(sync_item):
    ret = (f"<div>{settings.O365_CALENDAR_RESERVER_INFO_MARK}<br></div>"
           f"<div>{sync_item.reserver_name}</div>"
           f"<div>{sync_item.reserver_email_address}</div>"
           f"<div>{sync_item.reserver_phone_number}</div>")

    if sync_item.comments is not None and len(sync_item.comments) > 0:
        ret = ret + \
            (f"<div>{settings.O365_CALENDAR_COMMENTS_MARK}<br></div>"
             f"<div>{sync_item.comments}</div>")
    
    return ret

def is_email_address(string):
    try:
        validator = EmailValidator()
        validator(string)
    except ValidationError:
        return False

    return True

def is_phone_number(string):
    return re.match('^\+?[0-9]{7,}$', string)
