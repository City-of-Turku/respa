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
                                                        client_state=random_secret,
                                                        subscription_id=link.exchange_subscription_id
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
