import logging
import json
from respa_o365.respa_availabilility_repository import RespaAvailabilityRepository
from respa_o365.o365_availability_repository import O365AvailabilityRepository
import string
import random

from django.conf import settings
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission, IsAuthenticated
from requests_oauthlib import OAuth2Session
from urllib.parse import urlparse, parse_qs
from resources.models import Resource, Reservation
from .id_mapper import IdMapper
from .models import OutlookCalendarLink, OutlookCalendarReservation, OutlookCalendarAvailability
from .o365_calendar import O365Calendar, MicrosoftApi
from .o365_notifications import O365Notifications
from .o365_reservation_repository import O365ReservationRepository
from .reservation_sync import ReservationSync
from .respa_reservation_repository import RespaReservations
from respa_o365.sync_operations import reservationSyncActions, availabilitySyncActions

logger = logging.getLogger(__name__)

class SyncHelper:
    @staticmethod
    def copy_outlook_reservation_to_respa(calendar_link, o365_reservation):
        begin = O365Calendar.parse_outlook_datetime(o365_reservation.get('start'))
        end = O365Calendar.parse_outlook_datetime(o365_reservation.get('end'))
        exchange_id = o365_reservation.get('id')
        exchange_change_key = o365_reservation.get('changeKey')
        respa_reservation = Reservation.objects.create(
            resource=calendar_link.resource,
            begin = begin,
            end = end,
            state = Reservation.CONFIRMED
        )

        OutlookCalendarReservation.objects.create(
                            calendar_link=calendar_link,
                            reservation=respa_reservation,
                            exchange_id=exchange_id,
                            exchange_change_key=exchange_change_key,
                            respa_change_key=SyncHelper.get_respa_change_key(respa_reservation)
                        )

    @staticmethod
    def update_respa_reservation(outlook_calendar_reservation, o365_reservation):
        respa_reservation = outlook_calendar_reservation.reservation
        respa_reservation.begin = O365Calendar.parse_outlook_datetime(o365_reservation.get('start'))
        respa_reservation.end = O365Calendar.parse_outlook_datetime(o365_reservation.get('end'))
        respa_reservation.save()
        outlook_calendar_reservation.exchange_change_key = o365_reservation.get('changeKey')
        outlook_calendar_reservation.respa_change_key = SyncHelper.get_respa_change_key(respa_reservation)
        outlook_calendar_reservation.save()


    @staticmethod
    def get_respa_change_key(reservation):
        m = str(reservation.modified_at.timestamp())
        b = str(reservation.begin.timestamp())
        e = str(reservation.end.timestamp())
        s = reservation.state
        return m + b + e + s

class CanSyncCalendars(BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Resource):
            return obj.unit.is_manager(request.user)
        return False


def perform_sync_to_exchange(link, func):
    # Sync reservations
    _perform_sync(link=link, func=func, respa_memento_field='respa_reservation_sync_memento',
        o365_memento_field='exchange_reservation_sync_memento', outlook_model=OutlookCalendarReservation,
        outlook_model_event_id_property='reservation_id', respa_repo=RespaReservations, o365_repo=O365ReservationRepository, 
        event_prefix=settings.O365_CALENDAR_RESERVATION_EVENT_PREFIX, sync_actions=reservationSyncActions)

    # Sync availability / periods
    _perform_sync(link=link, func=func, respa_memento_field='respa_availability_sync_memento', 
        o365_memento_field='exchange_availability_sync_memento', outlook_model=OutlookCalendarAvailability,
        outlook_model_event_id_property='period_id', respa_repo=RespaAvailabilityRepository, o365_repo=O365AvailabilityRepository,
        event_prefix=settings.O365_CALENDAR_AVAILABILITY_EVENT_PREFIX, sync_actions=availabilitySyncActions)


def _perform_sync(link, func, respa_memento_field, o365_memento_field, outlook_model, outlook_model_event_id_property,
        event_prefix, sync_actions, o365_repo, respa_repo):
    token = link.token
    respa_memento = getattr(link, respa_memento_field)
    o365_memento = getattr(link, o365_memento_field)
    id_mappings = {}
    reservation_item_data = {}
    known_exchange_items = set()
    respa_change_keys = {}
    exchange_change_keys = {}
    for res in outlook_model.objects.filter(calendar_link=link):
        event_id = getattr(res, outlook_model_event_id_property)
        id_mappings[event_id] = res.exchange_id
        reservation_item_data[event_id] = res
        known_exchange_items.add(res.exchange_id)
        respa_change_keys[event_id] = res.respa_change_key
        exchange_change_keys[res.exchange_id] = res.exchange_change_key
    # Initialise components
    mapper = IdMapper(id_mappings)
    api = MicrosoftApi(token)
    cal = O365Calendar(microsoft_api=api, known_events=known_exchange_items, event_prefix=event_prefix)
    o365 = o365_repo(cal)
    respa = respa_repo(resource_id=link.resource.id)
    sync = ReservationSync(respa, o365, id_mapper=mapper, respa_memento=respa_memento, remote_memento=o365_memento,
        respa_change_keys=respa_change_keys, remote_change_keys=exchange_change_keys, sync_actions=sync_actions)
    # Perform synchronisation
    func(sync)
    # Store data back to database
    current_exchange_change_keys = sync.remote_change_keys()
    current_respa_change_keys = sync.respa_change_keys()
    for respa_id, exchange_id in mapper.changes():
        ri = reservation_item_data[respa_id]
        ri.exchange_id = exchange_id
        ri.exchange_change_key = current_exchange_change_keys.pop(exchange_id, ri.exchange_change_key)
        ri.respa_change_key = current_respa_change_keys.pop(respa_id, ri.respa_change_key)
        ri.save()
    for respa_id, exchange_id in mapper.removals():
        reservation_item_data[respa_id].delete()
    for respa_id, exchange_id in mapper.additions():
        exchange_change_key = current_exchange_change_keys.pop(exchange_id, "")
        respa_change_key = current_respa_change_keys.pop(respa_id, "")
        kwargs = {
            outlook_model_event_id_property: respa_id,
        }
        outlook_model.objects.create(
            calendar_link=link,
            exchange_id=exchange_id,
            respa_change_key=respa_change_key,
            exchange_change_key=exchange_change_key,
            **kwargs)
    for exchange_id, current_exchange_change_key in current_exchange_change_keys.items():
        old_exchange_change_key = exchange_change_keys.get(exchange_id, "")
        if current_exchange_change_key != old_exchange_change_key:
            respa_id = mapper.reverse.get(exchange_id)
            ri = reservation_item_data.get(respa_id, None)
            if ri:
                ri.exchange_change_key = current_exchange_change_key
                ri.respa_change_key = current_respa_change_keys.pop(respa_id, ri.respa_change_key)
                ri.save()
    for respa_id, current_respa_change_key in current_respa_change_keys.items():
        old_respa_change_key = respa_change_keys.get(respa_id, "")
        if current_respa_change_key != old_respa_change_key:
            exchange_id = mapper.get(respa_id)
            ri = reservation_item_data.get(respa_id, None)
            if ri:
                ri.respa_change_key = current_respa_change_key
                ri.exchange_change_key = current_exchange_change_keys.pop(exchange_id, ri.exchange_change_key)
                ri.save()
    setattr(link, o365_memento_field, sync.remote_memento())
    setattr(link, respa_memento_field, sync.respa_memento())
    link.token = api.current_token()
    link.save()

def ensure_notification(link):
    url = getattr(settings, "O365_NOTIFICATION_URL", None)
    if not url:
        return
    api = MicrosoftApi(link.token)
    subscriptions = O365Notifications(api)
    random_secret = ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(10))
    sub_id, created = subscriptions.ensureNotifications(notification_url=url,
                                                        resource="/me/events",
                                                        events=["updated", "deleted", "created"],
                                                        client_state=random_secret
                                                        )
    if created:
        link.exchange_subscription_id = sub_id
        link.exchange_subscription_secret = random_secret
        link.save()


class EventSync(APIView):

    def get(self, request):
        #url = "https://qe6kl3acqa.execute-api.eu-north-1.amazonaws.com/v1/o365/notification_callback"

        calendar_links = OutlookCalendarLink.objects.select_for_update().all()
        for link in calendar_links:
            logger.info("Synchronising user %d resource %s", link.user_id, link.resource_id)
            perform_sync_to_exchange(link, lambda sync: sync.sync_all())
            ensure_notification(link)

        return Response("OK")


    def get2(self, request):
        resource_id = request.query_params.get('resource')
        # Load state from database
        calendar_links = OutlookCalendarLink.objects.filter(resource=resource_id)
        for calendar_link in calendar_links:
            o365_calendar = O365Calendar2(calendar_link)
            o365_reservations = o365_calendar.get_events()
            checked_o365_ids = []
            respa_reservations = Reservation.objects.filter(resource=resource_id)
            reservation_links = OutlookCalendarReservation.objects.filter(calendar_link=calendar_link)
            for o365_reservation in o365_reservations:
                o365_id = o365_reservation.get('id')
                checked_o365_ids.append(o365_id)
                try:
                    reservation_link = reservation_links.get(exchange_id=o365_id)
                    try:
                        respa_reservation = respa_reservations.get(pk=reservation_link.reservation_id)

                    except Reservation.DoesNotExist:
                        # Respa reservation has been deleted. Remove Outlook reservation and link.
                        # If O365 event also is changed, we still delete it because Respa is the truth
                        logger.info("Deleting outlook reservation {}".format(o365_id))
                        o365_calendar.remove_event(o365_id)
                        reservation_link.delete()
                        continue
                    if reservation_link.respa_change_key != SyncHelper.get_respa_change_key(respa_reservation):
                        # Respa reservation has changed. Update O365 event & reservation link to match
                        logger.info("Updating outlook reservation to match {}".format(respa_reservation))
                        if respa_reservation.state == Reservation.CANCELLED:
                            o365_calendar.remove_event(o365_id)
                            reservation_link.delete()
                        else:
                            print (SyncHelper.get_respa_change_key(respa_reservation) == reservation_link.respa_change_key)
                            change_key = o365_calendar.update_event(o365_id, respa_reservation)
                            reservation_link.exchange_change_key = change_key
                            reservation_link.respa_change_key = SyncHelper.get_respa_change_key(respa_reservation)
                            reservation_link.save()

                    elif o365_reservation.get('changeKey') != reservation_link.exchange_change_key:
                        # O365 reservation has changed. Update respa reservation.
                        logger.info("Updating respa reservation {}".format(reservation_link))
                        SyncHelper.update_respa_reservation(reservation_link, o365_reservation)

                except OutlookCalendarReservation.DoesNotExist:
                    logger.info("New reservation from O365 {}".format(o365_id))
                    # New reservation in O365, copy it to Respa & create reservation link
                    SyncHelper.copy_outlook_reservation_to_respa(calendar_link, o365_reservation)

            # After this we need to check reservation links that had no O365 calendar event.
            # That means those were deleted in O365 calendar.
            remaining_reservation_links = reservation_links.exclude(exchange_id__in=checked_o365_ids)
            for reservation_link in remaining_reservation_links:
                respa_reservation = reservation_link.reservation
                respa_change_key = SyncHelper.get_respa_change_key(respa_reservation)
                if respa_change_key != reservation_link.respa_change_key:
                    # Since the truth resides in Respa, if respa was also updated, we put it back...
                    logger.info("Putting back reservation in calendar {}".format(respa_reservation))
                    result = o365_calendar.create_event(respa_reservation)
                    reservation_link.exchange_id=result.get('exchange_id')
                    reservation_link.exchange_change_key=result.get('change_key')
                    reservation_link.respa_change_key=respa_change_key
                    reservation_link.save()
                else:
                    # Ok, cancel respa reservation for deleted calendar event and delete reservation link
                    logger.info("Canceling respa reservation, because deleted in calendar {}".format(respa_reservation))
                    respa_reservation.state = Reservation.CANCELLED
                    respa_reservation.save()
                    reservation_link.delete()

            # And then check for any new respa reservations. Exclude canceled and denied reservations with .current()
            new_respa_reservations = respa_reservations.exclude(pk__in=reservation_links.values_list('reservation', flat=True)).current()
            for respa_reservation in new_respa_reservations:
                logger.info("Creating new respa reservation {}".format(respa_reservation))
                result = o365_calendar.create_event(respa_reservation)
                OutlookCalendarReservation.objects.create(
                        calendar_link=calendar_link,
                        reservation=respa_reservation,
                        exchange_id=result.get('exchange_id'),
                        exchange_change_key=result.get('change_key'),
                        respa_change_key=SyncHelper.get_respa_change_key(respa_reservation)
                )

        return Response("OK")

class O365Calendar2:
    def __init__(self, calendar_link):
        self._msgraph_session = None

    @staticmethod
    def parse_outlook_datetime(datetime):
        datetime_str = datetime.get('dateTime')
        tz_str = datetime.get('timeZone')
        return parse_datetime(datetime_str + '+00:00')

    def get_events(self):
        url = self._get_events_url()
        while url is not None:
            logger.info("Retrieving events from calendar at {}".format(url))
            json = self._get(url)
            url = json.get('@odata.nextLink')
            events = json.get('value')
            for event in events:
                yield event

    def get_event(self, event_id):
        url = self._get_events_url(event_id)
        json = self._get(url)
        return json

    def create_event(self, respa_reservation):
        begin = respa_reservation.begin.isoformat()
        end = respa_reservation.end.isoformat()
        return self._create_event(begin, end)

    def _create_event(self, begin, end):
        url = self._get_events_url()

        response = self._post(
                        url,
                        json={
                            "subject": "Varaamo-varaus",
                            "body": {
                                "contentType": "HTML",
                                "content": ""
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
            return {'exchange_id': exchange_id, 'change_key': change_key}

        raise O365CalendarError(response.text)

    def remove_event(self, event_id):
        url = self._get_events_url(event_id)
        self._delete(url)

    def update_event(self, event_id, respa_reservation):
        url = self._get_events_url(event_id)
        begin = respa_reservation.begin.isoformat()
        end = respa_reservation.end.isoformat()
        response = self._patch(
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
            }
        )
        res = response.json()
        return res.get('changeKey')

    def _get_calendar_id(self):
        return self._calendar_link.reservation_calendar_id

    def _get_session(self):
        # Do I need to worry about memory leak / reference counts?
        if (self._msgraph_session is not None):
            return self._msgraph_session
        token = json.loads(self._calendar_link.token)

        extra = {
            'client_id': settings.O365_CLIENT_ID,
            'client_secret': settings.O365_CLIENT_SECRET,
        }

        def token_updater(token):
            self._calendar_link.token = json.dumps(token)
            self._calendar_link.save()

        msgraph = OAuth2Session(settings.O365_CLIENT_ID,
                    token=token,
                    auto_refresh_kwargs=extra,
                    auto_refresh_url=settings.O365_TOKEN_URL,
                    token_updater=token_updater)

        self._msgraph_session = msgraph

        return self._msgraph_session

    def _get_events_url(self, event_id=None):
        base_url = '{}/me/calendars/{}/events'.format(settings.O365_API_URL, self._get_calendar_id())

        if event_id is None:
            return base_url

        return base_url + '/' + event_id

    def _get(self, url):
        session = self._get_session()
        response = session.get(url)
        return response.json()

    def _post(self, url, json=None):
        session = self._get_session()
        response = session.post(url, json=json)
        return response

    def _patch(self, url, json=None):
        session = self._get_session()
        response = session.patch(url, json=json)
        return response

    def _delete(self, url, json=None):
        session = self._get_session()
        response = session.delete(url, json=json)
        return response

class O365CalendarError(Exception):
    pass

class O365AvailabilityCalendar(O365Calendar):
    def _get_calendar_id(self):
        return self._calendar_link.availability_calendar_id
