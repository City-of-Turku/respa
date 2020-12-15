import json
import logging
from datetime import datetime, timezone
from functools import reduce

import pytz
from django.conf import settings
from requests_oauthlib import OAuth2Session

from respa_o365.reservation_sync_operations import ChangeType

logger = logging.getLogger(__name__)


class Event:
    begin = datetime.now()
    end = datetime.now()
    created_at = datetime.now()
    modified_at = datetime.now()
    subject = "Event"
    body = ""


    def __str__(self):
        return "{} -- {} {}: {}".format(self.begin, self.end, self.subject, self.body)

UTC = pytz.timezone("UTC")
time_format = '%Y-%m-%dT%H:%M:%S.%f%z'

class O365Calendar:
    def __init__(self,  calendar_id, microsoft_api):
        self._calendar_id = calendar_id
        self._api = microsoft_api

    def _parse_outlook_timestamp(self, ts):
        # 2017-08-29T04:00:00.0000000 is too long format. Shorten it to 26 characters, drop last number.
        timestamp_str = ts.get("dateTime")[:26]
        timezone_str = ts.get("timeZone")
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%f")
        return pytz.timezone(timezone_str).localize(timestamp)

    def get_events(self):
        url = self._get_events_url()
        result = {}
        while url is not None:
            logger.info("Retrieving events from calendar at {}".format(url))
            json = self._api.get(url)
            url = json.get('@odata.nextLink')
            events = json.get('value')
            for event in events:
                event_id = event.get("id")
                e = self.json_to_event(event)
                result[event_id] = e
        return result

    def json_to_event(self, event):
        subject = event.get("subject")
        body = event.get("body").get("content")
        start = self._parse_outlook_timestamp(event.get("start"))
        end = self._parse_outlook_timestamp(event.get("end"))
        created = datetime.strptime(event.get("createdDateTime").strip("Z")[:26], "%Y-%m-%dT%H:%M:%S.%f")
        created = UTC.localize(created)
        modified = datetime.strptime(event.get("lastModifiedDateTime").strip("Z")[:26], "%Y-%m-%dT%H:%M:%S.%f")
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
        url = self._get_events_url(event_id)
        json = self._api.get(url)
        if not json:
            return None
        return self.json_to_event(json)

    def create_event(self, event):
        begin = event.begin.isoformat()
        end = event.end.isoformat()
        subject = event.subject
        body = event.body
        url = self._get_events_url()
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
            change_key = res.get('changeKey')
            return exchange_id, change_key

        raise O365CalendarError(response.text)

    def remove_event(self, event_id):
        url = self._get_events_url(event_id)
        self._api.delete(url)

    def update_event(self, event_id, event):
        url = self._get_events_url(event_id)
        begin = event.begin.isoformat()
        end = event.end.isoformat()
        subject = event.subject
        body = event.body
        response = self._api.patch(
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
        res = response.json()
        return res.get('changeKey')

    def get_changes(self, memento=None):
        if memento:
            time = datetime.strptime(memento, time_format)
        else:
            time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        events = self.get_events()
        new_memento = reduce(lambda a, b: max(a, b.modified_at), events.values(), time)
        return {id: (status(r, time), "") for id, r in events.items()}, new_memento.strftime(time_format)

    def get_changes_by_id(self, item_ids, memento=None):
        if memento:
            time = datetime.strptime(memento, time_format)
        else:
            time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        events = self.get_events()
        new_memento = reduce(lambda a, b: max(a, b.modified_at), events.values(), time)
        return {id: (status(r, time), "") for id, r in events.items() if id in item_ids}, new_memento.strftime(time_format)

    def _get_events_url(self, event_id=None):
        if event_id is None:
            return 'me/calendars/{}/events?$top=50'.format(self._calendar_id)
        else:
            return 'me/calendars/{}/events/{}'.format(self._calendar_id, event_id)

def status(reservation, time):
    if reservation.modified_at <= time:
        return ChangeType.NO_CHANGE
#    if reservation.state in [Reservation.CANCELLED, Reservation.DENIED]:
#        return ChangeType.DELETED
    if reservation.created_at > time:
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


def urljoin(*args):
    def join_slash(a, b):
        return a.rstrip('/') + '/' + b.lstrip('/')
    return reduce(join_slash, args) if args else ''


class O365CalendarError(Exception):
    pass
