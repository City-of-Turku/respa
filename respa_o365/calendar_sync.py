import logging
import json
from django.conf import settings
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission, IsAuthenticated
from requests_oauthlib import OAuth2Session
from urllib.parse import urlparse, parse_qs
from resources.models import Resource, Reservation
from .models import OutlookCalendarLink, OutlookCalendarReservation

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

class EventSync(APIView):
    permission_classes = [IsAuthenticated, CanSyncCalendars]

    def get(self, request):
        resource_id = request.query_params.get('resource')
        calendar_links = OutlookCalendarLink.objects.filter(resource=resource_id)
        for calendar_link in calendar_links:
            o365_calendar = O365Calendar(calendar_link)
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

class O365Calendar:
    def __init__(self, calendar_link): 
        self._calendar_link = calendar_link
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
