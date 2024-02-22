# -*- coding: utf-8 -*-
import logging
import datetime
import pytz

from django.utils import timezone
import django.contrib.postgres.fields as pgfields
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.gis.db import models
from django.utils import translation
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db.models import Q
from psycopg2.extras import DateTimeTZRange

from notifications.models import NotificationTemplate, NotificationTemplateException, NotificationType, NotificationTemplateGroup
from resources.signals import (
    reservation_modified, reservation_confirmed, reservation_cancelled
)
from .base import ModifiableModel, NameIdentifiedModel
from .resource import generate_access_code, validate_access_code
from .resource import Resource
from .utils import (
    get_dt, save_dt, is_valid_time_slot, humanize_duration, send_respa_mail, send_respa_sms,
    DEFAULT_LANG, localize_datetime, format_dt_range, format_dt_range_alt, build_reservations_ical_file,
    get_order_quantity, get_order_tax_price, get_order_pretax_price, get_payment_requested_waiting_time,
    calculate_final_product_sums, calculate_final_order_sums
)

from random import sample

DEFAULT_TZ = pytz.timezone(settings.TIME_ZONE)

logger = logging.getLogger(__name__)

RESERVATION_BILLING_FIELDS = ('billing_first_name', 'billing_last_name', 'billing_phone_number',
                            'billing_email_address', 'billing_address_street', 'billing_address_zip',
                            'billing_address_city')

RESERVATION_EXTRA_FIELDS = ('reserver_name', 'reserver_phone_number', 'reserver_address_street', 'reserver_address_zip',
                            'reserver_address_city', 'company', 'event_description', 'event_subject', 'reserver_id',
                            'number_of_participants', 'participants', 'reserver_email_address', 'require_assistance',
                            'require_workstation', 'private_event', 'host_name', 'reservation_extra_questions', 'home_municipality'
                            ) + RESERVATION_BILLING_FIELDS


class ReservationQuerySet(models.QuerySet):
    def current(self):
        return self.exclude(state__in=(Reservation.CANCELLED, Reservation.DENIED))

    def active(self):
        return self.filter(end__gte=timezone.now()).current()

    def overlaps(self, begin, end):
        qs = Q(begin__lt=end) & Q(end__gt=begin)
        return self.filter(qs)

    def for_date(self, date):
        if isinstance(date, str):
            date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
        else:
            assert isinstance(date, datetime.date)
        dt = datetime.datetime.combine(date, datetime.datetime.min.time())
        start_dt = DEFAULT_TZ.localize(dt)
        end_dt = start_dt + datetime.timedelta(days=1)
        return self.overlaps(start_dt, end_dt)

    def extra_fields_visible(self, user):
        # the following logic is also implemented in Reservation.are_extra_fields_visible()
        # so if this is changed that probably needs to be changed as well

        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self

        allowed_resources = Resource.objects.with_perm('can_view_reservation_extra_fields', user)
        return self.filter(Q(user=user) | Q(resource__in=allowed_resources))

    def catering_orders_visible(self, user):
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self

        allowed_resources = Resource.objects.with_perm('can_view_reservation_catering_orders', user)
        return self.filter(Q(user=user) | Q(resource__in=allowed_resources))

    def cancel(self, user):
        for reservation in self:
            reservation.set_state(Reservation.CANCELLED, user)
            if reservation.has_order():
                order = reservation.get_order()
                order.set_state('cancelled', 'Order reservation was cancelled.')
class ReservationBulkQuerySet(models.QuerySet):
    def current(self):
        return self

class ReservationBulk(ModifiableModel):
    bucket = models.ManyToManyField('Reservation', related_name='reservationbulks', db_index=True)
    objects = ReservationBulkQuerySet.as_manager()

    def __str__(self):
        return "Reservation Bulk"

class Reservation(ModifiableModel):
    CREATED = 'created'
    CANCELLED = 'cancelled'
    CONFIRMED = 'confirmed'
    DENIED = 'denied'
    REQUESTED = 'requested'
    WAITING_FOR_PAYMENT = 'waiting_for_payment'
    READY_FOR_PAYMENT = 'ready_for_payment'
    WAITING_FOR_CASH_PAYMENT = 'waiting_for_cash_payment'
    STATE_CHOICES = (
        (CREATED, _('created')),
        (CANCELLED, _('cancelled')),
        (CONFIRMED, _('confirmed')),
        (DENIED, _('denied')),
        (REQUESTED, _('requested')),
        (WAITING_FOR_PAYMENT, _('waiting for payment')),
        (READY_FOR_PAYMENT, _('ready for payment')),
        (WAITING_FOR_CASH_PAYMENT, _('waiting for cash payment')),
    )

    TYPE_NORMAL = 'normal'
    TYPE_BLOCKED = 'blocked'
    TYPE_CHOICES = (
        (TYPE_NORMAL, _('Normal reservation')),
        (TYPE_BLOCKED, _('Resource blocked')),
    )

    resource = models.ForeignKey('Resource', verbose_name=_('Resource'), db_index=True, related_name='reservations',
                                 on_delete=models.PROTECT)
    begin = models.DateTimeField(verbose_name=_('Begin time'))
    end = models.DateTimeField(verbose_name=_('End time'))
    duration = pgfields.DateTimeRangeField(verbose_name=_('Length of reservation'), null=True,
                                           blank=True, db_index=True)
    comments = models.TextField(null=True, blank=True, verbose_name=_('Comments'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('User'), null=True,
                             blank=True, db_index=True, on_delete=models.PROTECT)

    preferred_language = models.CharField(choices=settings.LANGUAGES, verbose_name='Preferred Language', null=True, default=settings.LANGUAGES[0][0], max_length=8)

    state = models.CharField(max_length=32, choices=STATE_CHOICES, verbose_name=_('State'), default=CREATED)
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('Approver'),
                                 related_name='approved_reservations', null=True, blank=True,
                                 on_delete=models.SET_NULL)
    staff_event = models.BooleanField(verbose_name=_('Is staff event'), default=False)
    type = models.CharField(
        blank=False, verbose_name=_('Type'), max_length=32, choices=TYPE_CHOICES, default=TYPE_NORMAL)

    has_arrived = models.BooleanField(verbose_name=_('Has arrived'), default=False)
    takes_place_virtually = models.BooleanField(verbose_name=_('Takes place virtually'), default=False)
    virtual_address = models.TextField(verbose_name=_('Virtual address'), blank=True)

    # access-related fields
    access_code = models.CharField(verbose_name=_('Access code'), max_length=32, null=True, blank=True)

    # EXTRA FIELDS START HERE

    event_subject = models.CharField(max_length=200, verbose_name=_('Event subject'), blank=True)
    event_description = models.TextField(verbose_name=_('Event description'), blank=True)
    number_of_participants = models.PositiveSmallIntegerField(verbose_name=_('Number of participants'), blank=True,
                                                              null=True, default=1)
    participants = models.TextField(verbose_name=_('Participants'), blank=True)
    host_name = models.CharField(verbose_name=_('Host name'), max_length=100, blank=True)
    require_assistance = models.BooleanField(verbose_name=_('Require assistance'), default=False)
    require_workstation = models.BooleanField(verbose_name=_('Require workstation'), default=False)
    private_event = models.BooleanField(verbose_name=_('Private event'), default=False)
    home_municipality = models.ForeignKey('ReservationHomeMunicipalityField', verbose_name=_('Home municipality'),
                                            null=True, blank=True, on_delete=models.SET_NULL)
    universal_data = models.JSONField(verbose_name=_('Data'), null=True, blank=True)
    # extra detail fields for manually confirmed reservations

    reserver_name = models.CharField(verbose_name=_('Reserver name'), max_length=100, blank=True)
    reserver_id = models.CharField(verbose_name=_('Reserver ID (business)'), max_length=30, blank=True)
    reserver_email_address = models.EmailField(verbose_name=_('Reserver email address'), blank=True)
    reserver_phone_number = models.CharField(verbose_name=_('Reserver phone number'), max_length=30, blank=True)
    reserver_address_street = models.CharField(verbose_name=_('Reserver address street'), max_length=100, blank=True)
    reserver_address_zip = models.CharField(verbose_name=_('Reserver address zip'), max_length=30, blank=True)
    reserver_address_city = models.CharField(verbose_name=_('Reserver address city'), max_length=100, blank=True)
    reservation_extra_questions = models.TextField(verbose_name=_('Reservation extra questions'), blank=True)

    company = models.CharField(verbose_name=_('Company'), max_length=100, blank=True)
    billing_first_name = models.CharField(verbose_name=_('Billing first name'), max_length=100, blank=True)
    billing_last_name = models.CharField(verbose_name=_('Billing last name'), max_length=100, blank=True)
    billing_email_address = models.EmailField(verbose_name=_('Billing email address'), blank=True)
    billing_phone_number = models.CharField(verbose_name=_('Billing phone number'), max_length=30, blank=True)
    billing_address_street = models.CharField(verbose_name=_('Billing address street'), max_length=100, blank=True)
    billing_address_zip = models.CharField(verbose_name=_('Billing address zip'), max_length=30, blank=True)
    billing_address_city = models.CharField(verbose_name=_('Billing address city'), max_length=100, blank=True)

    # If the reservation was imported from another system, you can store the original ID in the field below.
    origin_id = models.CharField(verbose_name=_('Original ID'), max_length=50, editable=False, null=True)


    reminder = models.ForeignKey('ReservationReminder', verbose_name=_('Reservation Reminder'), db_index=True, related_name='ReservationReminders',
                                on_delete=models.SET_NULL, null=True, blank=True)

    timmi_id = models.PositiveIntegerField(verbose_name=_('Timmi ID'), null=True, blank=True)
    timmi_receipt = models.TextField(verbose_name=_('Timmi receipt'), null=True, blank=True, max_length=2000)

    objects = ReservationQuerySet.as_manager()

    class Meta:
        verbose_name = _("reservation")
        verbose_name_plural = _("reservations")
        ordering = ('id',)

    def _save_dt(self, attr, dt):
        """
        Any DateTime object is converted to UTC time zone aware DateTime
        before save

        If there is no time zone on the object, resource's time zone will
        be assumed through its unit's time zone
        """
        save_dt(self, attr, dt, self.resource.unit.time_zone)

    def _get_dt(self, attr, tz):
        return get_dt(self, attr, tz)

    @property
    def begin_tz(self):
        return self.begin

    @begin_tz.setter
    def begin_tz(self, dt):
        self._save_dt('begin', dt)

    def get_begin_tz(self, tz):
        return self._get_dt("begin", tz)

    @property
    def end_tz(self):
        return self.end

    @end_tz.setter
    def end_tz(self, dt):
        """
        Any DateTime object is converted to UTC time zone aware DateTime
        before save

        If there is no time zone on the object, resource's time zone will
        be assumed through its unit's time zone
        """
        self._save_dt('end', dt)

    def get_end_tz(self, tz):
        return self._get_dt("end", tz)

    def is_active(self):
        return self.end + self.resource.cooldown >= timezone.now() and self.state not in (Reservation.CANCELLED, Reservation.DENIED)

    def is_own(self, user):
        if not (user and user.is_authenticated):
            return False
        return user == self.user

    def need_manual_confirmation(self):
        return self.resource.need_manual_confirmation

    def are_extra_fields_visible(self, user):
        # the following logic is used also implemented in ReservationQuerySet
        # so if this is changed that probably needs to be changed as well

        if self.is_own(user):
            return True
        return self.resource.can_view_reservation_extra_fields(user)

    def can_view_access_code(self, user):
        if self.is_own(user):
            return True
        return self.resource.can_view_reservation_access_code(user)

    def set_state(self, new_state, user):
        # Make sure it is a known state
        assert new_state in (
            Reservation.REQUESTED, Reservation.CONFIRMED, Reservation.DENIED,
            Reservation.CANCELLED, Reservation.WAITING_FOR_PAYMENT,
            Reservation.READY_FOR_PAYMENT, Reservation.WAITING_FOR_CASH_PAYMENT
        )
        if new_state == self.state and self.state in (Reservation.CONFIRMED, Reservation.REQUESTED):
            reservation_modified.send(sender=self.__class__, instance=self, user=user)
            return
        elif new_state == Reservation.CONFIRMED:
            self.approver = user if user and user.is_authenticated else None
            if user or self.resource.authentication == 'unauthenticated':
                reservation_confirmed.send(sender=self.__class__, instance=self, user=user)
        elif new_state == Reservation.CANCELLED:
            reservation_cancelled.send(sender=self.__class__, instance=self, user=user)
        elif self.state == Reservation.CONFIRMED:
            self.approver = None
        old_state = self.state
        self.state = new_state
        self.save()
        self.handle_notification(new_state, user, old_state)

    def handle_notification(self, state, user, old_state):
        obj_user_is_staff = bool(self.user and self.user.is_staff)
        action_by_official = obj_user_is_staff and self.reserver_email_address != self.user.email

        # only true for reservations that weren't previously waiting for cash payment.
        reservation_is_confirmed = state == Reservation.CONFIRMED and old_state != Reservation.WAITING_FOR_CASH_PAYMENT

        if state == Reservation.REQUESTED:
            self.send_reservation_requested_mail(action_by_official=action_by_official)
            if not action_by_official:
                self.notify_staff_about_reservation(NotificationType.RESERVATION_REQUESTED_OFFICIAL)
        elif reservation_is_confirmed or state == Reservation.WAITING_FOR_CASH_PAYMENT:
            if self.need_manual_confirmation():
                self.send_reservation_confirmed_mail()
            elif self.access_code:
                self.send_reservation_created_with_access_code_mail(action_by_official=action_by_official)
                if not action_by_official:
                    self.notify_staff_about_reservation(NotificationType.RESERVATION_CREATED_WITH_ACCESS_CODE_OFFICIAL)
            else:
                self.send_reservation_created_mail(action_by_official=action_by_official)
                self.notify_staff_about_reservation(NotificationType.RESERVATION_CREATED_OFFICIAL)
        elif state == Reservation.DENIED:
            self.send_reservation_denied_mail()
        elif state == Reservation.CANCELLED and self.user:
            action_by_official = bool(user and user.is_staff and user.email != self.user.email)
            order = self.get_order()
            if not order or order and order.state in (order.CANCELLED, order.EXPIRED):
                self.send_reservation_cancelled_mail(action_by_official=action_by_official)
                if not action_by_official:
                    self.notify_staff_about_reservation(NotificationType.RESERVATION_CANCELLED_OFFICIAL)
        elif state == Reservation.READY_FOR_PAYMENT:
            order = self.get_order()
            if order:
                order.set_confirmed_by_staff()
                # dont resend mail if already ready for payment e.g. when adding comments
                if old_state != Reservation.READY_FOR_PAYMENT:
                    self.send_reservation_waiting_for_payment_mail()


    def can_modify(self, user):
        if not user:
            return False

        if self.state == Reservation.WAITING_FOR_PAYMENT:
            return False

        if self.get_order():
            return self.resource.can_modify_paid_reservations(user) or (
                self.user == user and self.state in (Reservation.READY_FOR_PAYMENT, Reservation.REQUESTED)
            )

        # reservations that need manual confirmation and are confirmed cannot be
        # modified or cancelled without reservation approve permission
        cannot_approve = not self.resource.can_approve_reservations(user)
        if self.need_manual_confirmation() and self.state == Reservation.CONFIRMED and cannot_approve:
            return False

        return self.user == user or self.resource.can_modify_reservations(user)

    def can_add_comment(self, user):
        if self.is_own(user):
            return True
        return self.resource.can_access_reservation_comments(user)

    def can_view_field(self, user, field):
        if field not in RESERVATION_EXTRA_FIELDS:
            return True
        if self.is_own(user):
            return True
        return self.resource.can_view_reservation_extra_fields(user)

    def can_view_catering_orders(self, user):
        if self.is_own(user):
            return True
        return self.resource.can_view_reservation_catering_orders(user)

    def can_add_product_order(self, user):
        return self.is_own(user)

    def can_view_product_orders(self, user):
        if self.is_own(user):
            return True
        return self.resource.can_view_reservation_product_orders(user)

    def get_order(self):
        return getattr(self, 'order', None)

    def has_order(self):
        return hasattr(self, 'order')

    def format_time(self):
        tz = self.resource.unit.get_tz()
        begin = self.begin.astimezone(tz)
        end = self.end.astimezone(tz)
        return format_dt_range(translation.get_language(), begin, end)

    def format_time_alt(self):
        tz = self.resource.unit.get_tz()
        begin = self.begin.astimezone(tz)
        end = self.end.astimezone(tz)
        return format_dt_range_alt(translation.get_language(), begin, end)

    def create_reminder(self):
        r_date = self.begin - datetime.timedelta(hours=int(self.resource.unit.sms_reminder_delay))
        reminder = ReservationReminder()
        reminder.reservation = self
        reminder.reminder_date = r_date
        reminder.save()
        self.reminder = reminder

    def modify_reminder(self):
        if not self.reminder:
            return
        r_date = self.begin - datetime.timedelta(hours=int(self.resource.unit.sms_reminder_delay))
        self.reminder.reminder_date = r_date
        self.reminder.save()

    def __str__(self):
        if self.state != Reservation.CONFIRMED:
            state_str = ' (%s)' % self.state
        else:
            state_str = ''
        return "%s: %s%s" % (self.format_time(), self.resource, state_str)

    def clean(self, **kwargs):
        """
        Check restrictions that are common to all reservations.

        If this reservation isn't yet saved and it will modify an existing reservation,
        the original reservation need to be provided in kwargs as 'original_reservation', so
        that it can be excluded when checking if the resource is available.
        """

        if 'user' in kwargs:
            user = kwargs['user']
        else:
            user = self.user

        user_is_admin = user and self.resource.is_admin(user)

        if self.end <= self.begin:
            raise ValidationError(_("You must end the reservation after it has begun"))

        # Check that begin and end times are on valid time slots.
        opening_hours = self.resource.get_opening_hours(self.begin.date(), self.end.date())
        for dt in (self.begin, self.end):
            days = opening_hours.get(dt.date(), [])
            day = next((day for day in days if day['opens'] is not None and day['opens'] <= dt <= day['closes']), None)
            if day and not is_valid_time_slot(dt, self.resource.slot_size, day['opens']):
                raise ValidationError(_("Begin and end time must match time slots"), code='invalid_time_slot')

        # Check if Unit has disallow_overlapping_reservations value of True
        if (
            self.resource.unit.disallow_overlapping_reservations and not
            self.resource.can_create_overlapping_reservations(user) and not
            isinstance(user, AnonymousUser)
        ):
            if self.resource.unit.disallow_overlapping_reservations_per_user:
                reservations_for_same_unit = Reservation.objects.filter(user=user, resource__unit=self.resource.unit)
            else:
                reservations_for_same_unit = Reservation.objects.filter(resource__unit=self.resource.unit)

            original = kwargs.get('original_reservation', None)
            if original:
                reservations_for_same_unit = reservations_for_same_unit.exclude(id=original.id)

            valid_reservations_for_same_unit = reservations_for_same_unit.exclude(state=Reservation.CANCELLED)
            user_has_conflicting_reservations = valid_reservations_for_same_unit.filter(
                Q(begin__gt=self.begin, begin__lt=self.end)
                | Q(begin__lt=self.begin, end__gt=self.begin)
                | Q(begin__gte=self.begin, end__lte=self.end)
                | Q(begin__lte=self.begin, end__gt=self.end)
            )

            if user_has_conflicting_reservations:
                raise ValidationError(
                    _('This unit does not allow overlapping reservations for its resources'),
                    code='conflicting_reservation'
                )

        original_reservation = self if self.pk else kwargs.get('original_reservation', None)
        if self.resource.check_reservation_collision(self.begin, self.end, original_reservation):
            raise ValidationError({'period': _("The resource is already reserved for some of the period")}, code='invalid_period_range')

        if not user_is_admin:
            if (self.end - self.begin) < self.resource.min_period:
                raise ValidationError(_("The minimum reservation length is %(min_period)s") %
                                      {'min_period': humanize_duration(self.resource.min_period)})
        else:
            if not (self.end - self.begin) % self.resource.slot_size == datetime.timedelta(0):
                raise ValidationError(_("The minimum reservation length is %(slot_size)s") %
                                      {'slot_size': humanize_duration(self.resource.slot_size)})

        if self.access_code:
            validate_access_code(self.access_code, self.resource.access_code_type)

        if self.resource.people_capacity:
            if (self.number_of_participants > self.resource.people_capacity):
                raise ValidationError(_("This resource has people capacity limit of %s" % self.resource.people_capacity))

    def get_notification_context(self, language_code, user=None, notification_type=None, extra_context={}):
        if not user:
            user = self.user
        with translation.override(language_code):
            reserver_home_municipality = self.home_municipality_id
            for municipality in self.resource.get_included_home_municipality_names():
                if municipality['id'] == self.home_municipality_id:
                    reserver_home_municipality = municipality['name'].get(language_code, None)
                    break

            reserver_name = self.reserver_name
            reserver_email_address = self.reserver_email_address
            if not reserver_name and self.user and self.user.get_display_name():
                reserver_name = self.user.get_display_name()
            if not reserver_email_address and user and user.email:
                reserver_email_address = user.email
            context = {
                'resource': self.resource.name,
                'begin': localize_datetime(self.begin),
                'end': localize_datetime(self.end),
                'begin_dt': self.begin,
                'end_dt': self.end,
                'time_range': self.format_time(),
                'time_range_alt': self.format_time_alt(),
                'reserver_name': reserver_name,
                'reserver_email_address': reserver_email_address,
                'require_assistance': self.require_assistance,
                'require_workstation': self.require_workstation,
                'private_event': self.private_event,
                'extra_question': self.reservation_extra_questions,
                'home_municipality_id': reserver_home_municipality,
                'takes_place_virtually': self.takes_place_virtually
            }
            directly_included_fields = (
                'number_of_participants',
                'host_name',
                'event_subject',
                'event_description',
                'reserver_phone_number',
                'billing_first_name',
                'billing_last_name',
                'billing_email_address',
                'billing_phone_number',
                'billing_address_street',
                'billing_address_zip',
                'billing_address_city'
            )
            for field in directly_included_fields:
                context[field] = getattr(self, field)
            if self.resource.unit:
                context['unit'] = self.resource.unit.name
                if self.resource.unit.address_postal_full:
                    context['unit_address'] = self.resource.unit.address_postal_full
                context['unit_id'] = self.resource.unit.id
                if self.resource.unit.map_service_id:
                    context['unit_map_service_id'] = self.resource.unit.map_service_id
            if self.can_view_access_code(user) and self.access_code:
                context['access_code'] = self.access_code

            if self.user and self.user.is_staff:
                context['staff_name'] = self.user.get_display_name()

            if self.virtual_address:
                context['virtual_address'] = self.virtual_address

            # Comments should only be added to notifications that are sent to staff.
            if notification_type in [NotificationType.RESERVATION_CREATED_OFFICIAL] and self.comments:
                context['comments'] = self.comments

            # Generic 'additional information' value
            if self.resource.reservation_additional_information:
                context['additional_information'] = self.resource.reservation_additional_information

            if notification_type in [NotificationType.RESERVATION_CONFIRMED, NotificationType.RESERVATION_CREATED]:
                if self.resource.reservation_confirmed_notification_extra:
                    context['extra_content'] = self.resource.reservation_confirmed_notification_extra
            elif notification_type == NotificationType.RESERVATION_REQUESTED:
                if self.resource.reservation_requested_notification_extra:
                    context['extra_content'] = self.resource.reservation_requested_notification_extra
            elif notification_type in [NotificationType.RESERVATION_WAITING_FOR_PAYMENT]:
                context['payment_url'] = self.order.payment_url

            # Get last main and ground plan images. Normally there shouldn't be more than one of each
            # of those images.
            images = self.resource.images.filter(type__in=('main', 'ground_plan')).order_by('-sort_order')
            main_image = next((i for i in images if i.type == 'main'), None)
            ground_plan_image = next((i for i in images if i.type == 'ground_plan'), None)

            if main_image:
                main_image_url = main_image.get_full_url()
                if main_image_url:
                    context['resource_main_image_url'] = main_image_url
            if ground_plan_image:
                ground_plan_image_url = ground_plan_image.get_full_url()
                if ground_plan_image_url:
                    context['resource_ground_plan_image_url'] = ground_plan_image_url

            universal_data = getattr(self, 'universal_data', None)
            if universal_data:
                # reservation contains universal_data
                selected_option = universal_data.get('selected_option')
                universal_field =universal_data.get('field')
                if selected_option and universal_field:
                    selected_values = [x['text'] for x in universal_field.get('options') if x['id'] == int(selected_option)]
                    context['universal_data'] = {
                        'label': universal_field.get('label'),
                        'selected_value': selected_values[0]
                        }

            order = getattr(self, 'order', None)
            if order:
                '''
                'RESERVATION_WAITING_FOR_PAYMENT' notifications required payment due date so it's calculated and added to context.
                e.g. datetime when order was confirmed + RESPA_PAYMENTS_PAYMENT_REQUESTED_WAITING_TIME = payment due date.
                20.01.2022 15:30:00 + 48 = 22.01.2022 15:30:00.
                '''
                if notification_type in [NotificationType.RESERVATION_WAITING_FOR_PAYMENT]:
                    context['payment_due_date'] = get_payment_requested_waiting_time(self)

                context['order'] = order.get_notification_context(language_code)

                all_products = []
                # Iterate through each order/product in order_lines.
                # Each order/product is appended to a list that is then set as the value of context['order'].
                for item in context["order"]["order_lines"]:
                    product = {}
                    product_fields = (
                        'id', 'created_at', 'reservation_name',
                        'name', 'quantity', 'price',
                        'unit_price', 'unit_price_num', 'tax_percentage',
                        'price_type', 'price_period', 'order_number',
                        'decimal_hours', 'pretax_price', 'pretax_price_num',
                        'tax_price', 'tax_price_num', 'detailed_price'
                    )
                    '''
                    product_values

                    These keys are used in the email template to display order/payment information.

                    id                  -   id of this order
                    created_at          -   creation date of the parent order
                    reservation_name    -   name of resource
                    name                -   name of this product
                    quantity            -   quantity of products, see function comments for explanation.
                    price               -   single unit price of this product
                    unit_price          -   total price of this product, string e.g. 75,00
                    unit_price_num      -   total price of this product, float e.g. 75.00
                    tax_percentage      -   tax percentage of this product
                    price_type          -   price type of product, per period / fixed
                    price_period        -   price period of product if type=per period, e.g. 00:30:00 for 30min
                    order_number        -   id of parent order
                    pretax_price        -   price amount without tax, string e.g. 6,05 if total price is 7,5 with 24% vat
                    pretax_price_num    -   price amount without tax, float e.g. 6.05. See function comments for further explanation.
                    tax_price           -   tax amount, string e.g. 1,45 if total price is 7,5 with 24% vat
                    tax_price_num       -   tax amount, float e.g. 1.45. See function comments for further explanation.
                    detailed price      -   contains detailed price info, timeslot specific prices used etc
                    '''
                    product_values = {
                        'id': item["product"]["id"],
                        'created_at': self.created_at.astimezone(self.resource.unit.get_tz()).strftime('%d.%m.%Y %H:%M:%S'),
                        'reservation_name': context["resource"],
                        'name': item["product"]["name"],
                        'quantity': get_order_quantity(item),
                        'price': item["product"]["price"],
                        'unit_price': item["unit_price"],
                        'unit_price_num': float(item["unit_price"].replace(',','.')),
                        'tax_percentage': item["product"]["tax_percentage"],
                        'price_type': item["product"]["price_type"],
                        'price_period': item["product"]["price_period"],
                        'order_number': context["order"]["id"],
                        'pretax_price': item["product"]["pretax_price"],
                        'pretax_price_num': get_order_pretax_price(item),
                        'tax_price': item["product"]["tax_price"],
                        'tax_price_num': get_order_tax_price(item),
                        'detailed_price': item["detailed_price"],
                    }

                    for field in product_fields:
                        if field == 'decimal_hours':
                            # price_period is None if price_type is 'fixed'
                            if item["product"]["price_period"] is not None:
                                # list of integers based on price_period string values, e.g. string '01:30:00' --> list [1,30,0]
                                price_unit_time = [int(x) for x in item["product"]["price_period"].split(':')]
                                # calculate decimal time from list integers e.g. based on previous values, ((1*60) + 30) / 60 = 1.5
                                decimal_hours = ((price_unit_time[0] * 60) + price_unit_time[1]) / 60
                                product[field] = decimal_hours
                            else:
                                # price_type is 'fixed'
                                product[field] = 1
                        elif field == 'detailed_price':
                            product[field] = product_values[field]
                            conditional_quantity = 1
                            if item['product']['price_type'] == 'per_period':
                                product_quantity = list(set([x['quantity'] for x in item['detailed_price'].values() if 'quantity' in x]))
                                # product_quantity is only truthy if there are 2 or more of the product.
                                if len(product_quantity) > 0:
                                    product['product_quantity'] = float(product_quantity[0])
                                    conditional_quantity = product_quantity[0]
                                else:
                                    # only 1 of the product
                                    product['product_quantity'] = float(1)

                            values = calculate_final_product_sums(product=item, quantity=conditional_quantity)
                            product['product_taxfree_total'] = values['product_taxfree_total']
                            product['product_tax_total'] = values['product_tax_total']

                        else:
                            product[field] = product_values[field]

                    all_products.append(product)

                order_sums = calculate_final_order_sums(all_products)

                context['order_details'] = all_products
                context['order_taxfree_total'] = order_sums['final_order_totals']['order_taxfree_total']
                context['order_total'] = order_sums['final_order_totals']['order_total']
                context['detailed_tax_sums'] = order_sums['final_order_totals']['order_tax_total']

        if extra_context:
            context.update({
                'bulk_email_context': {
                    **extra_context
                }
            })
        return context

    def get_notification_template(self, notification_type):
        try: # Search fallback for the default template of this type.
            fallback_template = NotificationTemplate.objects.get(type=notification_type, groups=None, is_default_template=True)
        except NotificationTemplate.DoesNotExist:
            fallback_template = None

        # Check if resource's unit has a template group and if that group contains a notification template with correct notification type.
        if self.resource.unit.notification_template_group_id:
            try: # Check if template group contains a notification template with correct notification type.
                unit_template_group = NotificationTemplateGroup.objects.get(id=self.resource.unit.notification_template_group_id)
                return unit_template_group.templates.get(type=notification_type)
            except (NotificationTemplateGroup.DoesNotExist, NotificationTemplate.DoesNotExist):
                return fallback_template
            except NotificationTemplate.MultipleObjectsReturned:
                logger.error(f"Template group: {unit_template_group.name} contains multiple templates of type: {notification_type}.")
                return fallback_template
        return fallback_template


    def get_email_address(self, user=None):
        """
        Stuff common to all reservation related mails.
        """
        if getattr(self, 'order', None) and self.billing_email_address:
            return self.billing_email_address
        elif self.reserver_email_address:
            return self.reserver_email_address
        elif user:
            return user.email

    def send_reservation_mail(self, notification_type,
                              user=None, attachments=None,
                              staff_email=None,
                              extra_context={}, is_reminder = False):
        if self.type == Reservation.TYPE_BLOCKED:
            return

        notification_template = self.get_notification_template(notification_type)
        if self.user and not user: # If user isn't given use self.user.
            user = self.user

        # Use reservation's preferred_language if it exists
        # else if user is defined and user.is_staff or staff_email is given, use default lang
        language = DEFAULT_LANG \
            if ((user and user.is_staff) or staff_email) \
                else getattr(self, 'preferred_language', DEFAULT_LANG)

        context = self.get_notification_context(language, notification_type=notification_type, extra_context=extra_context)
        try:
            if not notification_template:
                raise NotificationTemplateException("Failed to get template from %s" % notification_type)
            rendered_notification = notification_template.render(context, language)
        except NotificationTemplateException as exc:
            return logger.error(exc, exc_info=True, extra={ 'user': user.uuid if user else None })


        if self.reserver_phone_number:
            if is_reminder:
                return send_respa_sms(self.reserver_phone_number,
                    rendered_notification['subject'], rendered_notification['short_message'])

            if self.resource.send_sms_notification and not staff_email: # Don't send sms when notifying staff.
                send_respa_sms(self.reserver_phone_number,
                    rendered_notification['subject'], rendered_notification['short_message'])

        # Use staff email if given, else get the provided email address
        email_address = staff_email if staff_email \
            else self.get_email_address(user)

        if email_address:
            send_respa_mail(email_address, rendered_notification['subject'],
                rendered_notification['body'], rendered_notification['html_body'], attachments)


    def notify_staff_about_reservation(self, notification):
        if self.resource.resource_staff_emails:
            attachment = ('reservation.ics', build_reservations_ical_file([self]), 'text/calendar')
            for email in self.resource.resource_staff_emails:
                self.send_reservation_mail(notification, staff_email=email, attachments=[attachment])
        else:
            notify_users = self.resource.get_users_with_perm('can_approve_reservation')
            if len(notify_users) > 100:
                raise Exception("Refusing to notify more than 100 users (%s)" % self)
            for user in notify_users:
                self.send_reservation_mail(notification, user=user, staff_email=user.email)

    def send_reservation_requested_mail(self, action_by_official=False):
        notification = NotificationType.RESERVATION_REQUESTED_BY_OFFICIAL \
            if action_by_official else NotificationType.RESERVATION_REQUESTED
        self.send_reservation_mail(notification)

    def send_reservation_modified_mail(self, action_by_official=False):
        notification = NotificationType.RESERVATION_MODIFIED_BY_OFFICIAL \
            if action_by_official else NotificationType.RESERVATION_MODIFIED
        self.send_reservation_mail(notification)
        if action_by_official: # staff should also get notification with the updated reservations details.
            self.notify_staff_about_reservation(NotificationType.RESERVATION_MODIFIED_OFFICIAL)

    def send_reservation_denied_mail(self):
        self.send_reservation_mail(NotificationType.RESERVATION_DENIED)

    def send_reservation_confirmed_mail(self):
        attachment = 'reservation.ics', build_reservations_ical_file([self]), 'text/calendar'
        self.send_reservation_mail(NotificationType.RESERVATION_CONFIRMED,
                                   attachments=[attachment])

    def send_reservation_cancelled_mail(self, action_by_official=False):
        notification = NotificationType.RESERVATION_CANCELLED_BY_OFFICIAL \
            if action_by_official else NotificationType.RESERVATION_CANCELLED
        self.send_reservation_mail(notification)

    def send_reservation_created_mail(self, action_by_official=False):
        attachment = 'reservation.ics', build_reservations_ical_file([self]), 'text/calendar'
        notification = NotificationType.RESERVATION_CREATED_BY_OFFICIAL \
            if action_by_official else NotificationType.RESERVATION_CREATED
        self.send_reservation_mail(notification,
                                   attachments=[attachment])

    def send_reservation_created_with_access_code_mail(self, action_by_official=False):
        attachment = 'reservation.ics', build_reservations_ical_file([self]), 'text/calendar'
        notification = NotificationType.RESERVATION_CREATED_WITH_ACCESS_CODE_OFFICIAL_BY_OFFICIAL \
            if action_by_official else NotificationType.RESERVATION_CREATED_WITH_ACCESS_CODE
        self.send_reservation_mail(notification,
                                   attachments=[attachment])

    def send_reservation_waiting_for_payment_mail(self):
        self.send_reservation_mail(NotificationType.RESERVATION_WAITING_FOR_PAYMENT,
                                   attachments=[])

    def send_access_code_created_mail(self):
        self.send_reservation_mail(NotificationType.RESERVATION_ACCESS_CODE_CREATED)

    def save(self, *args, **kwargs):
        self.duration = DateTimeTZRange(self.begin, self.end, '[)')

        if not self.access_code:
            access_code_type = self.resource.access_code_type
            if self.resource.is_access_code_enabled() and self.resource.generate_access_codes:
                self.access_code = generate_access_code(access_code_type)

        return super().save(*args, **kwargs)


class ReservationMetadataField(models.Model):
    field_name = models.CharField(max_length=100, verbose_name=_('Field name'), unique=True)

    class Meta:
        verbose_name = _('Reservation metadata field')
        verbose_name_plural = _('Reservation metadata fields')

    def __str__(self):
        return self.field_name


class ReservationMetadataSet(ModifiableModel):
    name = models.CharField(max_length=100, verbose_name=_('Name'), unique=True)
    supported_fields = models.ManyToManyField(ReservationMetadataField, verbose_name=_('Supported fields'),
                                              related_name='metadata_sets_supported')
    required_fields = models.ManyToManyField(ReservationMetadataField, verbose_name=_('Required fields'),
                                             related_name='metadata_sets_required', blank=True)

    class Meta:
        verbose_name = _('Reservation metadata set')
        verbose_name_plural = _('Reservation metadata sets')

    def __str__(self):
        return self.name

    def filter(self, field, value):
        field = getattr(self, field, None)
        if not field:
            return
        return field.filter(field_name=value)

    def add(self, field, value):
        _field = getattr(self, field, None)
        if not _field:
            return
        try:
            obj = ReservationMetadataField.objects.get(field_name=value)
        except ObjectDoesNotExist:
            return
        if field == 'required_fields':
            self.supported_fields.add(obj)
        _field.add(obj)

    def remove(self, field, value):
        _field = getattr(self, field, None)
        if not _field:
            return
        try:
            obj = ReservationMetadataField.objects.get(field_name=value)
        except ObjectDoesNotExist:
            return
        if field == 'supported_fields':
            self.required_fields.remove(obj)
        _field.remove(obj)

    @staticmethod
    def get_supported_fields():
        try:
            return [str(s.field_name) for s in ReservationMetadataField.objects.all()]
        except:
            return []

    @staticmethod
    def get_example():
        try:
            items = [str(s.field_name) for s in ReservationMetadataField.objects.all()]
            if len(items) < 2:
                return ["Example1", "Example2"]
        except:
            return ["Example1", "Example2"]
        return sample(items, 2)

class ReservationHomeMunicipalityField(NameIdentifiedModel):
    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(max_length=100, verbose_name=_('Name'), unique=True)

    class Meta:
        verbose_name = _('Reservation home municipality field')
        verbose_name_plural = _('Reservation home municipality fields')
        ordering = ('name',)

    def __str__(self):
        return self.name


class ReservationHomeMunicipalitySet(ModifiableModel):
    name = models.CharField(max_length=100, verbose_name=_('Name'), unique=True)
    included_municipalities = models.ManyToManyField(ReservationHomeMunicipalityField,
        verbose_name=_('Included municipalities'), related_name='home_municipality_included_set')

    class Meta:
        verbose_name = _('Reservation home municipality set')
        verbose_name_plural = _('Reservation home municipality sets')

    def __str__(self):
        return self.name

    def add(self, value):
        try:
            obj = ReservationHomeMunicipalityField.objects.get(name=value)
        except ObjectDoesNotExist:
            return
        self.included_municipalities.add(obj)

    def filter(self, value):
        return self.included_municipalities.filter(name=value)

    def remove(self, value):
        try:
            obj = ReservationHomeMunicipalityField.objects.get(name=value)
        except ObjectDoesNotExist:
            return
        self.included_municipalities.remove(obj)

    @staticmethod
    def get_supported_fields():
        try:
            return [str(s.name) for s in ReservationHomeMunicipalityField.objects.all()]
        except:
            return []

    @staticmethod
    def get_example():
        try:
            items = [str(s.name) for s in ReservationHomeMunicipalityField.objects.all()]
            if len(items) < 2:
                return ["Example1", "Example2"]
        except:
            return ["Example1", "Example2"]
        return sample(items, 2)
class ReservationReminderQuerySet(models.QuerySet):
    pass

class ReservationReminder(models.Model):
    reservation = models.ForeignKey('Reservation', verbose_name=_('Reservation'), db_index=True, related_name='Reservations',
                                 on_delete=models.CASCADE)
    reminder_date = models.DateTimeField(verbose_name=_('Reminder Date'))


    objects = ReservationReminderQuerySet.as_manager()

    def get_unix_timestamp(self):
        unix_epoch = datetime.datetime(year=1970, month=1, day=1, hour=0, minute=0, second=0)
        time_diff = self.reminder_date.replace(tzinfo=pytz.timezone('Europe/Helsinki')) - unix_epoch.replace(tzinfo=pytz.timezone('Europe/Helsinki'))
        return int(time_diff.total_seconds())


    def remind(self):
        self.reservation.send_reservation_mail(
            notification_type = NotificationType.RESERVATION_REMINDER,
            user = self.reservation.user,
            is_reminder = True
        )

    def __str__(self):
        return '%s - %s' % (self.reservation, self.reservation.reserver_email_address)
