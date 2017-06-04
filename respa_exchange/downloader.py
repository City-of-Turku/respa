"""
Download Exchange events into Respa as reservations.
"""
import datetime
import logging

import iso8601
from django.db.transaction import atomic
from django.utils.timezone import now

from resources.models.reservation import Reservation
from respa_exchange.ews.calendar import GetCalendarItemsRequest, FindCalendarItemsRequest
from respa_exchange.ews.user import ResolveNamesRequest
from respa_exchange.ews.objs import ItemID
from respa_exchange.ews.xml import NAMESPACES
from respa_exchange.models import ExchangeReservation

log = logging.getLogger(__name__)


def _populate_reservation(reservation, ex_resource, item_props):
    """
    Populate a Reservation instance based on Exchange data

    :type reservation: resources.models.Reservation
    :type ex_resource: respa_exchange.models.ExchangeResource
    :type item_props: dict
    :return:
    """
    comment_text = "%s\nSynchronized from Exchange %s" % (item_props["subject"], ex_resource.exchange)
    reservation.begin = item_props["start"]
    reservation.end = item_props["end"]
    reservation.comments = comment_text
    reservation._from_exchange = True  # Set a flag to prevent immediate re-upload
    return reservation


def _update_reservation_from_exchange(item_id, ex_reservation, ex_resource, item_props):
    reservation = ex_reservation.reservation
    _populate_reservation(reservation, ex_resource, item_props)
    reservation.save()
    ex_reservation.item_id = item_id
    ex_reservation.organizer_email = item_props.get("organizer_email")
    ex_reservation.save()

    log.info("Updated: %s", ex_reservation)


def _create_reservation_from_exchange(item_id, ex_resource, item_props):
    reservation = Reservation(resource=ex_resource.resource)
    _populate_reservation(reservation, ex_resource, item_props)
    reservation.save()
    ex_reservation = ExchangeReservation(
        exchange=ex_resource.exchange,
        principal_email=ex_resource.principal_email,
        reservation=reservation,
        managed_in_exchange=True,
    )
    ex_reservation.item_id = item_id
    ex_reservation.organizer_email = item_props.get("organizer_email")
    ex_reservation.save()

    log.info("Created: %s", ex_reservation)
    return ex_reservation


def _resolve_user_email(ex_resource, name):
    req = ResolveNamesRequest([name], principal=ex_resource.principal_email)
    resolutions = req.send(ex_resource.exchange.get_ews_session())
    for res in resolutions:
        mb = res.find("t:Mailbox", namespaces=NAMESPACES)
        if mb is None:
            continue
        routing_type = mb.find("t:RoutingType", namespaces=NAMESPACES).text
        assert routing_type == "SMTP"
        email = mb.find("t:EmailAddress", namespaces=NAMESPACES).text
        break
    else:
        email = ""
    return email


def _determine_organizer(ex_resource, organizer):
    mailbox = organizer.find("t:Mailbox", namespaces=NAMESPACES)
    routing_type = mailbox.find("t:RoutingType", namespaces=NAMESPACES).text
    email_address = mailbox.find("t:EmailAddress", namespaces=NAMESPACES).text
    if routing_type == "SMTP":
        return email_address.lower()
    if routing_type == "EX":
        return _resolve_user_email(ex_resource, email_address).lower()
    raise Exception("Unknown routing type %s" % routing_type)


def _parse_item_props(ex_resource, item):
    item_props = dict(
        start=iso8601.parse_date(item.find("t:Start", namespaces=NAMESPACES).text),
        end=iso8601.parse_date(item.find("t:End", namespaces=NAMESPACES).text),
        subject=item.find("t:Subject", namespaces=NAMESPACES).text,
    )
    organizer = item.find("t:Organizer", namespaces=NAMESPACES)
    if organizer is not None:
        item_props["organizer_email"] = _determine_organizer(ex_resource, organizer)
    return item_props


@atomic
def sync_from_exchange(ex_resource, future_days=365):
    """
    Synchronize from Exchange to Respa

    Synchronizes current and future events for the given Exchange resource into
    the relevant Respa resource as reservations.

    :param ex_resource: The Exchange resource to sync
    :type ex_resource: respa_exchange.models.ExchangeResource
    :param future_days: How many days into the future to look
    :type future_days: int
    """
    if not ex_resource.sync_to_respa:
        return
    start_date = now()
    end_date = start_date + datetime.timedelta(days=future_days)

    log.info(
        "%s: Requesting items between (%s..%s)",
        ex_resource.principal_email,
        start_date,
        end_date
    )
    gcir = FindCalendarItemsRequest(
        principal=ex_resource.principal_email,
        start_date=start_date,
        end_date=end_date
    )
    session = ex_resource.exchange.get_ews_session()
    calendar_items = {}
    for item in gcir.send(session):
        calendar_items[ItemID.from_tree(item)] = item

    hashes = set(item_id.hash for item_id in calendar_items.keys())

    log.info(
        "%s: Received %d items",
        ex_resource.principal_email,
        len(calendar_items)
    )
    # First handle deletions . . .

    items_to_delete = ExchangeReservation.objects.select_related("reservation").filter(
        managed_in_exchange=True,  # Reservations we've downloaded ...
        reservation__begin__gte=start_date.replace(hour=0, minute=0, second=0),  # that are in ...
        reservation__end__lte=end_date.replace(hour=23, minute=59, second=59),  # ... our get items range ...
        reservation__resource__exchange_resource=ex_resource,  # and belong to this resource,
    ).exclude(item_id_hash__in=hashes)  # but aren't ones we're going to mangle

    for ex_reservation in items_to_delete:
        log.info("Deleting: %s", ex_reservation)
        reservation = ex_reservation.reservation
        ex_reservation.delete()
        reservation.delete()

    # And then creations/additions

    extant_exchange_reservations = {
        ex_reservation.item_id_hash: ex_reservation
        for ex_reservation
        in ExchangeReservation.objects.select_related("reservation").filter(item_id_hash__in=hashes)
    }

    for item_id, item in calendar_items.items():
        ex_reservation = extant_exchange_reservations.get(item_id.hash)
        item_props = _parse_item_props(ex_resource, item)

        if not ex_reservation:  # It's a new one!
            ex_reservation = _create_reservation_from_exchange(item_id, ex_resource, item_props)
        else:
            if ex_reservation._change_key != item_id.change_key:
                # Things changed, so edit the reservation
                _update_reservation_from_exchange(item_id, ex_reservation, ex_resource, item_props)

    log.info("%s: download processing complete", ex_resource.principal_email)
