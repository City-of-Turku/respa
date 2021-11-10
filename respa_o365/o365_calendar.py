import json
import logging
import re
from copy import copy
from datetime import datetime, timezone, timedelta
from functools import reduce
from urllib import parse
import pytz
from django.conf import settings
from requests_oauthlib import OAuth2Session

from respa_o365.sync_operations import ChangeType

logger = logging.getLogger(__name__)


class Event:

    def __init__(self):
        self.begin = datetime.now()
        self.end = datetime.now()
        self.created_at = datetime.now()
        self. modified_at = datetime.now()
        self.subject = "Event"
        self.body = ""

    def __str__(self):
        return "{} -- {} {}: {}".format(self.begin, self.end, self.subject, self.body)

    def __eq__(self, other):
        return self.begin == other.begin \
               and self.end == other.end \
               and self.subject == other.subject \
               and self.body == other.body


    def change_key(self):
        h = hash(self.subject) ^ 3 * hash(self.body) ^ 7
        h = h ^ 11 * hash(self.begin.timestamp())
        h = h ^ 13 * hash(self.end.timestamp())
        return str(h)

UTC = pytz.timezone("UTC")
local_tz = pytz.timezone(settings.TIME_ZONE)
time_format = '%Y-%m-%dT%H:%M:%S.%f%z'

class O365Calendar:
    def __init__(self,  microsoft_api, known_events={}, calendar_id=None, event_prefix=None):
        self._calendar_id = calendar_id
        self._api = microsoft_api
        self._known_events = known_events
        self._event_prefix = event_prefix
        self._start_date = (datetime.now(tz=timezone.utc) - timedelta(days=settings.O365_SYNC_DAYS_BACK)).replace(microsecond=0)
        self._end_date = (datetime.now(tz=timezone.utc) + timedelta(days=settings.O365_SYNC_DAYS_FORWARD)).replace(microsecond=0)

    def _parse_outlook_timestamp(self, ts):
        # 2017-08-29T04:00:00.0000000 is too long format. Shorten it to 26 characters, drop last number.
        timestamp_str = ts.get("dateTime")[:26]
        timezone_str = ts.get("timeZone")
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%f")
        return pytz.timezone(timezone_str).localize(timestamp)

    def event_prefix_matches(self, s):
        return self._event_prefix is None or s is not None and re.match(self._event_prefix, s, re.I)

    def get_events(self):
        url = self._get_events_list_url()
        result = {}
        while url is not None:
            logger.info("Retrieving events from calendar at {}".format(url))
            try:
                json = self._api.get(url)
            except MicrosoftApiError:
                return result
            url = json.get('@odata.nextLink')
            events = json.get('value')
            for event in events:
                event_id = event.get("id")
                e = self.json_to_event(event)
                if self.event_prefix_matches(e.subject):
                    result[event_id] = e
        return result

    def json_to_event(self, json):
        subject = json.get("subject")
        body = json.get("body").get("content")
        start = self._parse_outlook_timestamp(json.get("start"))
        end = self._parse_outlook_timestamp(json.get("end"))
        created = datetime.strptime(json.get("createdDateTime").strip("Z")[:26], "%Y-%m-%dT%H:%M:%S.%f")
        created = UTC.localize(created)
        modified = datetime.strptime(json.get("lastModifiedDateTime").strip("Z")[:26], "%Y-%m-%dT%H:%M:%S.%f")
        modified = UTC.localize(modified)
        e = Event()
        e.begin = start
        e.end = end
        e.subject = subject
        e.body = body
        e.created_at = created
        e.modified_at = modified
        return e

    def get_event(self, event_id):
        url = self._get_single_event_url(event_id)
        try:
            json = self._api.get(url)
        except MicrosoftApiError:
            return None
        if not json:
            return None
        event = self.json_to_event(json)
        if self.event_prefix_matches(event.subject):
            return event
        else:
            return None

    def create_event(self, event):
        begin = event.begin.astimezone(local_tz).isoformat()
        end = event.end.astimezone(local_tz).isoformat()
        subject = event.subject
        body = event.body
        url = self._get_create_event_url()
        response = self._api.post(
            url,
            json={
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body
                },
                "start": {
                    "dateTime": begin,
                    "timeZone": "FLE Standard Time"

                },
                "end": {
                    "dateTime": end,
                    "timeZone": "FLE Standard Time"
                },
                "location":{
                    "displayName": "Varaamo"
                },
                "allowNewTimeProposals": "false",
            }
        )
        if response.ok:
            res = response.json()
            exchange_id = res.get('id')
            return exchange_id, event.change_key()

        raise O365CalendarError(response.text)

    def remove_event(self, event_id):
        url = self._get_single_event_url(event_id)
        self._api.delete(url)

    def update_event(self, event_id, event):
        url = self._get_single_event_url(event_id)
        begin = event.begin.astimezone(local_tz).isoformat()
        end = event.end.astimezone(local_tz).isoformat()
        subject = event.subject
        body = event.body
        self._api.patch(
            url,
            json={
                "start": {
                    "dateTime": begin,
                    "timeZone": "FLE Standard Time"
                },
                "end": {
                    "dateTime": end,
                    "timeZone": "FLE Standard Time"
                },
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body
                },
            }
        )
        return event.change_key()

    def get_changes(self, memento=None):
        # Microsoft API does not provide general API to fetch changes.
        # There is delta for primary calendar, but this does not work in cases
        # where calendar id needs to be defined. Thus this method is not
        # able to return whole status as memento. Items seen during last
        # call is used to detect deleted items between calls.
        # Method is not immutable against memento as it should.
        if memento:
            time = datetime.strptime(memento, time_format)
        else:
            time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        events = self.get_events()
        deleted = set(self._known_events).difference(events.keys())
        self._known_events = {k for k in events.keys()}
        events = {i: e for i, e in events.items() if e.modified_at > time}
        new_memento = reduce(lambda a, b: max(a, b.modified_at), events.values(), time)
        result = {id: (status(r, time), r.change_key()) for id, r in events.items()}
        for i in deleted:
            result[i] = (ChangeType.DELETED, "")
        return result, new_memento.strftime(time_format)

    def get_changes_by_ids(self, item_ids, memento=None):
        changes, new_memento = self.get_changes(memento)
        return {i: changes.get(i, (ChangeType.NO_CHANGE, "")) for i in item_ids}, new_memento

    def _get_events_list_url(self):
        qs = 'startDateTime={}&endDateTime={}&$top=50'.format(parse.quote_plus(self._start_date.isoformat()), parse.quote_plus(self._end_date.isoformat()))
        if self._calendar_id is not None:
            return 'me/calendars/{}/calendarView?{}'.format(self._calendar_id, qs)

        return 'me/calendar/calendarView?{}'.format(qs)

    def _get_single_event_url(self, event_id):
        if self._calendar_id is not None:
            return 'me/calendars/{}/events/{}'.format(self._calendar_id, event_id)
        
        return 'me/events/{}'.format(event_id)

    def _get_create_event_url(self):
        if self._calendar_id is not None:
            return 'me/calendars/{}/events'.format(self._calendar_id)
        
        return 'me/events'

    

def status(item, time):
    # Temporary logging method
    status = _status(item, time)
    logger.info("Outlook event starting at {} has status {} since {}. Last modified at {}".format(item.begin, status, time, item.modified_at))
    return status

def _status(item, time):
    if item.modified_at <= time:
        return ChangeType.NO_CHANGE
#    if reservation.state in [Reservation.CANCELLED, Reservation.DENIED]:
#        return ChangeType.DELETED
    if item.created_at > time:
        return ChangeType.CREATED
    return ChangeType.UPDATED


class MicrosoftApi:

    def __init__(self, token,
                 client_id=settings.O365_CLIENT_ID,
                 client_secret=settings.O365_CLIENT_SECRET,
                 api_url=settings.O365_API_URL,
                 token_url=settings.O365_TOKEN_URL):
        self._api_url = api_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._token = token
        self._msgraph_session = None

    def get(self, path):
        session = self._get_session()
        response = session.get(self._url_for(path))
        if response.status_code == 400:
            logger.error("Microsoft API Error for GET {path}: {response.text}")
            raise MicrosoftApiError("Microsoft API Error for GET {path}: {response.text}")
        if response.status_code == 404:
            # Item is not available
            return None
        return response.json()

    def post(self, path, json=None):
        session = self._get_session()
        response = session.post(self._url_for(path), json=json)
        return response

    def patch(self, path, json=None):
        session = self._get_session()
        response = session.patch(self._url_for(path), json=json)
        return response

    def delete(self, path, json=None):
        session = self._get_session()
        response = session.delete(self._url_for(path), json=json)
        return response

    def _get_session(self):
        if self._msgraph_session is not None:
            return self._msgraph_session

        token = json.loads(self._token)

        extra = {
        'client_id': self._client_id,
        'client_secret': self._client_secret,
        }

        def token_updater(new_token):
            self._token = json.dumps(new_token)

        msgraph = OAuth2Session(self._client_id,
                            token=token,
                            auto_refresh_kwargs=extra,
                            auto_refresh_url=self._token_url,
                            token_updater=token_updater)

        self._msgraph_session = msgraph

        return self._msgraph_session

    def _url_for(self, path):
        def remove_prefix(text, prefix):
            if text.startswith(prefix):
                return text[len(prefix):]
            return text
        return urljoin(self._api_url, remove_prefix(path, self._api_url))

    def current_token(self):
        return self._token


def urljoin(*args):
    def join_slash(a, b):
        return a.rstrip('/') + '/' + b.lstrip('/')
    return reduce(join_slash, args) if args else ''


class O365CalendarError(Exception):
    pass

class MicrosoftApiError(Exception):
    pass