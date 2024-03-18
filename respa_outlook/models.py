from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from respa_outlook.manager import store, ToEWSDateTime

from exchangelib import CalendarItem, Mailbox, Attendee, EWSTimeZone
from exchangelib.properties import Mailbox
from exchangelib.version import EXCHANGE_2016
from os.path import abspath, join
from datetime import datetime, timedelta


import time

from resources.models import Reservation
from resources.models.utils import send_respa_mail


from copy import copy

import pytz

class RespaOutlookConfigurationQuerySet(models.QuerySet):
    pass

class RespaOutlookConfiguration(models.Model):
    name = models.CharField(verbose_name=_("Configuration name"), max_length=255)
    resource = models.ForeignKey('resources.Resource', verbose_name=_('Resource'), related_name='_Resources',
                                    blank=True, null=True, on_delete=models.CASCADE)

    email = models.CharField(verbose_name=_('Email'), max_length=255)
    password = models.CharField(verbose_name=_('Password'), max_length=255)


    objects = RespaOutlookConfigurationQuerySet.as_manager()

    class Meta:
        verbose_name = _("Outlook configuration")
        verbose_name_plural = _("Outlook configurations")

    def __str__(self):
        try:
            return '%s (%s) [%s]' % (self.name, self.resource.name, self.email)
        except:
            return self.name

    def handle_create(self, reservation):
        if not reservation.reserver_email_address:
            return
        if not reservation.reserver_email_address.endswith(settings.OUTLOOK_EMAIL_DOMAIN):
            return

        unit_address = reservation.resource.unit.address_postal_full if reservation.resource.unit.address_postal_full else reservation.resource.unit.street_address

        manager = store.items.get(self.id)

        appointment = CalendarItem(
            account=manager.account,
            folder=manager.calendar,
            subject = 'Reservation created',
            body = 'You have created an reservation',
            start=ToEWSDateTime(reservation.begin),
            end=ToEWSDateTime(reservation.end),
            categories=[],
            location=unit_address,
            required_attendees=[
                Attendee(
                    mailbox=Mailbox(email_address=reservation.reserver_email_address),
                    response_type='Accept'
                )
            ]
        )
        Mailbox.get_field_by_fieldname('routing_type').supported_from = EXCHANGE_2016
        appointment.save()
        self.create_respa_outlook_reservation(appointment=appointment, reservation=reservation,
                                              email=reservation.reserver_email_address)


    def handle_modify(self, reservation, appointment=None):
        manager = store.items.get(self.id)
        outlook = RespaOutlookReservation.objects.get(reservation_id=reservation.id)

        if appointment:
            cache = copy(reservation)
            if reservation.begin != appointment.start:
                reservation.begin = appointment.start
            if reservation.end != appointment.end:
                reservation.end = appointment.end
            try:
                reservation.clean()
                reservation.save()
            except ValidationError:
                appointment.start = cache.begin
                appointment.end = cache.end
                appointment.required_attendees[0] = \
                    Attendee(
                        mailbox=Mailbox(email_address=cache.reserver_email_address),
                        response_type='Accept'
                    )
                appointment.save()
        else:
            appointment = manager.calendar.get(id=outlook.exchange_id)
            appointment.start = ToEWSDateTime(reservation.begin)
            appointment.end = ToEWSDateTime(reservation.end)

            appointment.required_attendees[0] = \
                     Attendee(
                        mailbox=Mailbox(email_address=reservation.reserver_email_address),
                        response_type='Accept'
                    )
            appointment.save()
        outlook.modified = datetime.now() + timedelta(minutes=2)
        outlook.save()



    def create_respa_outlook_reservation(self, appointment, reservation, email):
        if not appointment:
            return
        if not reservation:
            if not email:
                return
            reservation = Reservation(
                resource = self.resource,
                begin = appointment.start,
                end = appointment.end,
                reserver_email_address = email,
                state = Reservation.CONFIRMED
            )
            reservation.clean()
            reservation.save()
            send_respa_mail(
                email_address=email,
                subject="Reservation created",
                body="Reservation via outlook created"
            )

        RespaOutlookReservation(
            name = '%s (%s)' % (reservation.reserver_email_address, self.resource.name),
            exchange_id = appointment.id,
            exchange_changekey = appointment.changekey,
            reservation = reservation
        ).save()



class RespaOutlookReservationQuerySet(models.QuerySet):
    pass

class RespaOutlookReservation(models.Model):
    name = models.CharField(verbose_name=_("Reserver name & Resource"), max_length=255)

    reservation = models.ForeignKey('resources.Reservation', verbose_name=_('Reservation'), related_name='OutlookReservations',
                                    blank=True, null=True, on_delete=models.CASCADE)

    exchange_id = models.CharField(verbose_name=_("Exchange ID"), max_length=255)
    exchange_changekey = models.CharField(verbose_name=_("Exchange Key"), max_length=255)

    modified = models.DateTimeField(verbose_name=_('Modified'), blank=True, null=True)

    objects = RespaOutlookReservationQuerySet.as_manager()

    class Meta:
        verbose_name = _("Outlook reservation")
        verbose_name_plural = _("Outlook reservations")


    def __str__(self):
        try:
            return '%s [%s-%s]' % (self.name, self.reservation.begin, self.reservation.end)
        except:
            return self.name


    def get_modified_timestamp(self):
        if self.modified:
            return int((self.modified.replace(tzinfo=pytz.timezone('Europe/Helsinki')) - datetime(year=1970, month=1, day=1, hour=0, minute=0, second=0).replace(tzinfo=pytz.timezone('Europe/Helsinki'))).total_seconds())

        #return int(time.time())
        return int((datetime.now().replace(tzinfo=None) - datetime(year=1970, month=1, day=1, hour=0, minute=0, second=0).replace(tzinfo=None)).total_seconds())

