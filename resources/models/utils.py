import base64
import datetime
from decimal import Decimal, ROUND_HALF_UP
import struct
import time
import io
import logging
from munigeo.models import Municipality
import pytz

import arrow
from django.conf import settings
from django.utils import formats
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.contrib.sites.models import Site
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, ContentType
from django.utils.translation import gettext, ngettext, gettext_lazy as _
from django.utils.text import format_lazy
from django.utils import timezone
from django.utils.timezone import localtime
from rest_framework.reverse import reverse
from icalendar import Calendar, Event, vDatetime, vText, vGeo, vCalAddress
from modeltranslation.translator import NotRegistered, translator

import xlsxwriter


class RespaNotificationAction:
    EMAIL = 'EMAIL'
    SMS = 'SMS'
    NONE = None

DEFAULT_LANG = settings.LANGUAGES[0][0]


def save_dt(obj, attr, dt, orig_tz="UTC"):
    """
    Sets given field in an object to a DateTime object with or without
    a time zone converted into UTC time zone from given time zone

    If there is no time zone on the given DateTime, orig_tz will be used
    """
    if dt.tzinfo:
        arr = arrow.get(dt).to("UTC")
    else:
        arr = arrow.get(dt, orig_tz).to("UTC")
    setattr(obj, attr, arr.datetime)


def get_dt(obj, attr, tz):
    return arrow.get(getattr(obj, attr)).to(tz).datetime


def get_translated(obj, attr):
    key = "%s_%s" % (attr, DEFAULT_LANG)
    val = getattr(obj, key, None)
    if not val:
        val = getattr(obj, attr)
    return val


# Needed for slug fields populating
def get_translated_name(obj):
    return get_translated(obj, 'name')


def generate_id():
    t = time.time() * 1000000
    b = base64.b32encode(struct.pack(">Q", int(t)).lstrip(b'\x00')).strip(b'=').lower()
    return b.decode('utf8')


def time_to_dtz(time, date=None, arr=None):
    tz = timezone.get_current_timezone()
    if time:
        if date:
            return tz.localize(datetime.datetime.combine(date, time))
        elif arr:
            return tz.localize(datetime.datetime(arr.year, arr.month, arr.day, time.hour, time.minute))
    else:
        return None


def is_valid_time_slot(time, time_slot_duration, opening_time):
    """
    Check if given time is correctly aligned with time slots.

    :type time: datetime.datetime
    :type time_slot_duration: datetime.timedelta
    :type opening_time: datetime.datetime
    :rtype: bool
    """
    return not ((time - opening_time) % time_slot_duration)


def humanize_duration(duration):
    """
    Return the given duration in a localized humanized form.

    Examples: "2 hours 30 minutes", "1 hour", "30 minutes"

    :type duration: datetime.timedelta
    :rtype: str
    """
    hours = duration.days * 24 + duration.seconds // 3600
    mins = duration.seconds // 60 % 60
    hours_string = ngettext('%(count)d hour', '%(count)d hours', hours) % {'count': hours} if hours else None
    mins_string = ngettext('%(count)d minute', '%(count)d minutes', mins) % {'count': mins} if mins else None
    return ' '.join(filter(None, (hours_string, mins_string)))


notification_logger = logging.getLogger('respa.notifications')


def send_respa_mail(email_address, subject, body, html_body=None, attachments=None) -> RespaNotificationAction:
    if not getattr(settings, 'RESPA_MAILS_ENABLED', False):
        notification_logger.info('Respa mail is not enabled.')
    try:
        from_address = (getattr(settings, 'RESPA_MAILS_FROM_ADDRESS', None) or
                        'noreply@%s' % Site.objects.get_current().domain)

        text_content = body
        msg = EmailMultiAlternatives(subject, text_content, from_address, [email_address], attachments=attachments)
        if html_body:
            msg.attach_alternative(html_body, 'text/html')
        msg.send()
        return RespaNotificationAction.EMAIL
    except Exception as exc:
        notification_logger.error('Respa mail error %s', exc)


def send_respa_sms(phone_number, subject, short_message) -> RespaNotificationAction:
    if not getattr(settings, 'RESPA_SMS_ENABLED', False):
        notification_logger.info('Respa SMS is not enabled.')
    try:
        from_address = (getattr(settings, 'RESPA_MAILS_FROM_ADDRESS', None) or
                        'noreply@%s' % Site.objects.get_current().domain)
        sms = EmailMultiAlternatives(subject, short_message, from_address, [f'{phone_number}@{settings.GSM_NOTIFICATION_ADDRESS}'])
        sms.send()
        return RespaNotificationAction.SMS
    except Exception as exc:
        notification_logger.error('Respa SMS error %s', exc)


def generate_reservation_xlsx(reservations, **kwargs):
    """
    Return reservations in Excel xlsx format

    The parameter is expected to be a list of dicts with fields:
      * unit: unit name str
      * resource: resource name str
      * begin: begin time datetime
      * end: end time datetime
      * staff_event: is staff event bool
      * user: user email str (optional)
      * comments: comments str (optional)
      * all of RESERVATION_EXTRA_FIELDS are optional as well

    :rtype: bytes
    """
    from resources.models import Resource, Reservation, RESERVATION_EXTRA_FIELDS
    def clean(string):
        if not string:
            return ''

        if isinstance(string, dict):
            string = next(iter(string.items()))[1]

        if not isinstance(string, str):
            return string

        unallowed_characters = ['=', '+', '-', '"', '@']
        if string[0] in unallowed_characters:
            string = string[1:]
        return string

    request = kwargs.get('request', None)
    weekdays = kwargs.get('weekdays', None)
    include_block_reservations = kwargs.get('include_block_reservations', False)
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    sheet_name = format_lazy('{} {}', _('Reservation'), _('Reports'))
    worksheet = workbook.add_worksheet(str(sheet_name).capitalize())

    global row_cursor
    row_cursor = 0

    title_format = workbook.add_format()
    title_format.set_bg_color('black')
    title_format.set_font_color('white')
    title_format.set_bold()


    def set_title(title, *, headers = [], use_extra_fields = True):
        global row_cursor
        if not headers: # Default header values.
            headers = [
                ('Unit', 45), ('Resource', 35),
                ('Begin time', 25), ('End time', 25),
                ('Created at', 45), ('User', 45),
                ('Comments', 30), ('Staff event', 25),
            ]

        if use_extra_fields:
            for field in RESERVATION_EXTRA_FIELDS:
                field_name = Reservation._meta.get_field(field).verbose_name
                headers.append((field_name, len(field_name) + 10))

        for col, header in enumerate(headers):
            if col > 0:
                worksheet.write(row_cursor, col, '', title_format)
            else:
                worksheet.write(row_cursor, col, title, title_format)
            worksheet.set_column(col, col, header[1])

        row_cursor += 1
        header_format = workbook.add_format({'bold': True})
        for column, header in enumerate(headers):
            worksheet.write(row_cursor, column, str(_(header[0])), header_format)
        row_cursor += 1

    opening_hours = {}
    resource_usage_info = {}

    if request:
        query_start = datetime \
            .datetime \
            .strptime(request.query_params.get('start', '1970-01-01'), '%Y-%m-%d') \
            .replace(hour=0, minute=0, second=0)
        query_end = datetime\
            .datetime\
            .strptime(request.query_params.get('end', '1970-01-01'), '%Y-%m-%d') \
            .replace(hour=23, minute=59, second=59)


        try:
            resources = request.query_params.get('resource').split(',')
        except:
            resources = []

        opening_hours = {
            resource:resource.get_opening_hours(query_start, query_end) \
            for resource in Resource.objects.filter(id__in=resources)
        }

    for resource in opening_hours:
        for date, time_range in opening_hours[resource].items():
            for time_slot in time_range:
                opens, closes = time_slot.items()
                if not opens[1] or not closes[1]:
                    continue

                if weekdays and opens[1].weekday() not in weekdays:
                    continue

                if resource not in resource_usage_info:
                    resource_usage_info[resource] = {'total_opening_hours': 0, 'total_normal_reservation_hours': 0, 'total_block_reservation_hours': 0}
                resource_usage_info[resource]['total_opening_hours'] += (closes[1] - opens[1]).total_seconds() / 3600

    date_format = workbook.add_format({'num_format': 'dd.mm.yyyy hh:mm', 'align': 'left'})
    total_normal_reservation_hours = 0
    total_block_reservation_hours = 0

    normal_reservations = [
        reservation for reservation in reservations \
            if reservation['type'] == Reservation.TYPE_NORMAL
    ]
    block_reservations = [
        reservation for reservation in reservations \
            if reservation['type'] == Reservation.TYPE_BLOCKED
    ]

    if normal_reservations:
        set_title(gettext('Normal reservations'))
        for row, reservation in enumerate(normal_reservations, row_cursor):
            for key in reservation: reservation[key] = clean(reservation[key])
            obj = Reservation.objects.get(pk=reservation['id'])
            usage_info = resource_usage_info.get(obj.resource, None)
            begin = localtime(reservation['begin']).replace(tzinfo=None)
            end = localtime(reservation['end']).replace(tzinfo=None)
            worksheet.write(row, 0, reservation['unit'])
            worksheet.write(row, 1, reservation['resource'])
            worksheet.write(row, 2, begin, date_format)
            worksheet.write(row, 3, end, date_format)
            worksheet.write(row, 4, localtime(reservation['created_at']).replace(tzinfo=None), date_format)
            if 'user' in reservation:
                worksheet.write(row, 5, reservation['user'])
            if 'comments' in reservation:
                worksheet.write(row, 6, reservation['comments'])
            worksheet.write(row, 7, reservation['staff_event'])
            for i, field in enumerate(RESERVATION_EXTRA_FIELDS, 8):
                if field in reservation:
                    if isinstance(reservation[field], dict):
                        try:
                            reservation[field] = next(iter(reservation[field].items()))[1]
                        except:
                            continue
                    worksheet.write(row, i, reservation[field])
            total_normal_reservation_hours += (end-begin).total_seconds() # Overall total
            if usage_info:
                usage_info['total_normal_reservation_hours'] += (end-begin).total_seconds() / 3600 # Resource specific total
            row_cursor += 1

        row_cursor += 1
        col_format = workbook.add_format({'color': 'red'})
        col_format.set_bold()
        worksheet.write(row_cursor, 0, gettext('Normal reservation hours total'), col_format)
        worksheet.write(row_cursor, 1, gettext('%(hours)s hours') % ({'hours': int((total_normal_reservation_hours / 60) / 60)}), col_format)
        row_cursor += 2

    if block_reservations and include_block_reservations:
        set_title(gettext('Block reservations'))
        for row, reservation in enumerate(block_reservations, row_cursor):
            for key in reservation: reservation[key] = clean(reservation[key])
            obj = Reservation.objects.get(pk=reservation['id'])
            usage_info = resource_usage_info.get(obj.resource, None)
            begin = localtime(reservation['begin']).replace(tzinfo=None)
            end = localtime(reservation['end']).replace(tzinfo=None)
            worksheet.write(row, 0, reservation['unit'])
            worksheet.write(row, 1, reservation['resource'])
            worksheet.write(row, 2, begin, date_format)
            worksheet.write(row, 3, end, date_format)
            worksheet.write(row, 4, localtime(reservation['created_at']).replace(tzinfo=None), date_format)
            if 'user' in reservation:
                worksheet.write(row, 5, reservation['user'])
            if 'comments' in reservation:
                worksheet.write(row, 6, reservation['comments'])
            worksheet.write(row, 7, reservation['staff_event'])
            for i, field in enumerate(RESERVATION_EXTRA_FIELDS, 8):
                if field in reservation:
                    if isinstance(reservation[field], dict):
                        try:
                            reservation[field] = next(iter(reservation[field].items()))[1]
                        except:
                            continue
                    worksheet.write(row, i, reservation[field])
            total_block_reservation_hours += (end-begin).total_seconds() # Overall total
            if usage_info:
                usage_info['total_block_reservation_hours'] += (end-begin).total_seconds() / 3600 # Resource specific total
            row_cursor += 1

        row_cursor += 1
        col_format = workbook.add_format({'color': 'red'})
        col_format.set_bold()
        worksheet.write(row_cursor, 0, gettext('Block reservation hours total'), col_format)
        worksheet.write(row_cursor, 1, gettext('%(hours)s hours') % ({'hours': int((total_block_reservation_hours / 60) / 60)}), col_format)
        row_cursor += 2


    row_cursor += 2
    headers = [
        ('Unit', 45),
        ('Resource', 40),
        ('Resource utilization', 25),
        ('Opening hours total', 25),
        ('Normal reservation hours total', 42),
        ('Block reservation hours total', 40),
    ]
    if request:
        set_title(gettext('Resource utilization for period %(start)s - %(end)s %(extra)s') % ({
            'start': query_start.date(),
            'end': query_end.date(),
            'extra': f"({gettext('Selected days: %(selected)s') % ({'selected': _build_weekday_string(weekdays)})})" if weekdays else ''
        }), headers=headers, use_extra_fields=False)
    else:
        set_title(gettext('Resource utilization'), headers=headers, use_extra_fields=False)

    for row, resource_info in enumerate(resource_usage_info.items(), row_cursor):
        resource, info = resource_info
        resource_utilization = float((info.get('total_normal_reservation_hours') / info.get('total_opening_hours')) * 100)
        worksheet.write(row, 0, resource.unit.name) # Column: Unit
        worksheet.write(row, 1, resource.name) # Column: Resource
        worksheet.write(row, 2, "%.2f%%" % resource_utilization) # Column: Resource utilization
        worksheet.write(row, 3, "%sh" % info.get('total_opening_hours')) # Column: Opening hours total
        worksheet.write(row, 4, "%sh" % info.get('total_normal_reservation_hours')) # Column: Normal reservation hours total
        worksheet.write(row, 5, "%sh" % info.get('total_block_reservation_hours')) # Column: Block reservation hours total
    workbook.close()
    return output.getvalue()

def _build_weekday_string(weekdays):
    from resources.models import Day
    return ', '.join(str(Day.DAYS_OF_WEEK[weekday][1]).capitalize() for weekday in weekdays)

def get_object_or_none(cls, **kwargs):
    try:
        return cls.objects.get(**kwargs)
    except cls.DoesNotExist:
        return None


def create_datetime_days_from_now(days_from_now):
    if days_from_now is None:
        return None

    dt = timezone.localtime(timezone.now()) + datetime.timedelta(days=days_from_now)
    dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)

    return dt


def localize_datetime(dt):
    return formats.date_format(timezone.localtime(dt), 'DATETIME_FORMAT')


def format_dt_range(language, begin, end):
    if language == 'fi':
        # ma 1.1.2017 klo 12.00
        begin_format = r'D j.n.Y \k\l\o G.i'
        if begin.date() == end.date():
            end_format = 'G.i'
            sep = '–'
        else:
            end_format = begin_format
            sep = ' – '

        res = sep.join([formats.date_format(begin, begin_format), formats.date_format(end, end_format)])
    else:
        # default to English
        begin_format = r'D j/n/Y G:i'
        if begin.date() == end.date():
            end_format = 'G:i'
            sep = '–'
        else:
            end_format = begin_format
            sep = ' – '

        res = sep.join([formats.date_format(begin, begin_format), formats.date_format(end, end_format)])

    return res


def format_dt_range_alt(language: str, begin, end) -> str:
    if language == 'fi':
        # 1.11.2023 klo 12.00-13.00
        begin_format = r'j.n.Y \k\l\o G.i'
        if begin.date() == end.date():
            end_format = 'G.i'
            sep = '–'
        else:
            end_format = begin_format
            sep = ' – '

        res = sep.join([formats.date_format(begin, begin_format), formats.date_format(end, end_format)])
    elif language == 'sv':
        # 1.11.2023 kl 12.00-13.00
        begin_format = r'j.n.Y \k\l G.i'
        if begin.date() == end.date():
            end_format = 'G.i'
            sep = '–'
        else:
            end_format = begin_format
            sep = ' – '

        res = sep.join([formats.date_format(begin, begin_format), formats.date_format(end, end_format)])
    else:
        # default to English
        # 1.11.2023 12:00-13:00
        begin_format = r'j.n.Y G:i'
        if begin.date() == end.date():
            end_format = 'G:i'
            sep = '–'
        else:
            end_format = begin_format
            sep = ' – '

        res = sep.join([formats.date_format(begin, begin_format), formats.date_format(end, end_format)])

    return res


def build_reservations_ical_file(reservations):
    """
    Return iCalendar file containing given reservations
    """

    cal = Calendar()
    cal.add('prodid', '-//Varaamo Turku//')
    cal.add('version', '2.0')
    for reservation in reservations:
        event = Event()
        begin_utc = timezone.localtime(reservation.begin, timezone.utc)
        end_utc = timezone.localtime(reservation.end, timezone.utc)
        event['uid'] = 'respa_reservation_{}'.format(reservation.id)
        event['dtstart'] = vDatetime(begin_utc)
        event['dtend'] = vDatetime(end_utc)
        if reservation.created_at:
            event['dtstamp'] = vDatetime(reservation.created_at)

        event['summary'] = vText(reservation.resource.name)

        if reservation.reserver_email_address:
            attendee = vCalAddress(f'MAILTO:{reservation.reserver_email_address}')
            attendee.params['cn'] = vText(reservation.reserver_name)
            event.add('attendee', attendee, encode=0)

        cal.add_component(event)
    return cal.to_ical()


def build_ical_feed_url(ical_token, request):
    """
    Return iCal feed url for given token without query parameters
    """

    url = reverse('ical-feed', kwargs={'ical_token': ical_token}, request=request)
    return url[:url.find('?')]


def get_municipality_help_options():
    try:
        return list(Municipality.objects.all().values_list('pk', flat=True))
    except:
        return []


def get_order_quantity(item):
    '''
    Return the quantity of products based on the item['product']['price_type'].

    If price_type is 'per_period' -> quantity = total price of product / single unit price of product
    otherwise return item['quantity'].

    e.g. 2 hour reservation with 10euro per 30min price period, 40 / 10 = 4.
    '''

    price = item["product"]["price"].replace(',','.')

    if Decimal(price) == Decimal('0.00'):
        return float(item["quantity"])

    if item["product"]["price_type"] == 'per_period':
        if item["product"]["type"] != "rent":
            '''
            This is for product's that have price_type == 'per_period' but type is something other than 'rent'.
            The order's quantity is used instead of calculating one based on prices.
            '''
            return float(item["quantity"])

        # Quantity is calculated from the total unit price / single product price.
        quantity = float(item["unit_price"].replace(',','.')) / float(item["product"]["price"].replace(',','.'))
        if quantity < 1:
            '''
            If for example the price_period of the product was 1h30min with a price of 9 euros and
            the actual reservation is only 30min, then the unit_price would  3 euros.

            3 / 9 = ~0.333 so we just return a 1 instead.
            '''
            return float(1)

        return float(quantity)

    return float(item["quantity"])


def get_order_tax_price(item):
    '''
    Returns the correct tax price/amount for this item.
    '''
    price = item["product"]["price"].replace(',','.')

    if Decimal(price) == Decimal('0.00'):
        return float(price)


    if item["product"]["price_type"] == 'per_period':
        if item["product"]["type"] != "rent":
            # Use the precalculated tax price if type is not 'rent'
            return float(item["reservation_tax_price"])

        quantity = float(item["unit_price"].replace(',','.')) / float(item["product"]["price"].replace(',','.'))
        if quantity > 1:
            return float(item["product"]["tax_price"].replace(',','.'))

    return float(item["reservation_tax_price"])


def get_order_pretax_price(item):
    '''
    Returns the correct tax-free price for this item.
    '''

    price = item["product"]["price"].replace(',','.')

    if Decimal(price) == Decimal('0.00'):
        return float(price)

    if item["product"]["price_type"] == 'per_period':
        quantity = float(item["unit_price"].replace(',','.')) / float(item["product"]["price"].replace(',','.'))
        if quantity < 1 or item["product"]["type"] != "rent":
            return float(item['reservation_pretax_price'])

        return float(item["product"]["pretax_price"].replace(',','.'))

    return float(item['reservation_pretax_price'])


def log_entry(instance, user, *, is_edit, message : str):
    content_type = ContentType.objects.get_for_model(instance)
    LogEntry.objects.log_action(
        user.id, content_type.id,
        instance.id, repr(instance),
        CHANGE if is_edit else ADDITION,
        message
    )

def get_translated_fields(instance, use_field_name=False):
    translated = {}
    try:
        translation_options = translator.get_options_for_model(instance.__class__)
        for field_name in translation_options.fields.keys():
            for lang in [x[0] for x in settings.LANGUAGES]:
                field = getattr(instance, '%s_%s' % (field_name, lang), None)
                if not field:
                    continue

                if not use_field_name:
                    translated[lang] = field
                    continue
                if field_name not in translated:
                    translated[field_name] = {}
                translated[field_name][lang] = field
        return translated
    except NotRegistered:
        return None

def get_payment_requested_waiting_time(reservation):
    '''
    Returns the date and time of when a order should be paid by.
    Time is calculated by adding order.confirmed_by_staff_at datetime + waiting_time,
    after this exact calculation the datetime is rounded down to the nearest hour.

    waiting_time is based on the payment_requested_waiting_time value found in
    the resource or the resources unit, if neither have this value set then the
    env variable RESPA_PAYMENTS_PAYMENT_REQUESTED_WAITING_TIME is used instead.
    '''

    waiting_time = settings.RESPA_PAYMENTS_PAYMENT_REQUESTED_WAITING_TIME
    if getattr(reservation.resource,'payment_requested_waiting_time', None):
        waiting_time = reservation.resource.payment_requested_waiting_time
    elif getattr(reservation.resource.unit, 'payment_requested_waiting_time', None):
        waiting_time = reservation.resource.unit.payment_requested_waiting_time

    exact_value = reservation.order.confirmed_by_staff_at + datetime.timedelta(hours=waiting_time)
    rounded_value = exact_value.replace(microsecond=0, second=0, minute=0)

    return rounded_value.astimezone(reservation.resource.unit.get_tz()).strftime('%d.%m.%Y %H:%M')

def calculate_final_product_sums(product: dict, quantity: int = 1):
    '''
    Calculate and return the following product values:
    product_taxfree_total - sum of all pricings taxfree value
    product_tax_total - sum of all pricings tax value
    '''
    tax_raw = 0
    taxfree_price = 0
    for x in product.values():
        tax_raw += x['tax_total']
        taxfree_price += x['taxfree_price_total']

    tax_total = quantity * tax_raw

    return {
        'product_tax_total': tax_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'product_taxfree_total': taxfree_price * quantity
    }

def calculate_final_order_sums(all_products):
    '''
    Used to calculate and return the following values:
    final_order_totals - dict containing the following:

    order_total     -   the final price of this order
    order_tax_total -   dict containing keys for each VAT % and total tax for each VAT%, eg.
        example order with 3 products that have VAT 24, 14 and 10
        {'24.00':Decimal('3.48'), '14.00':Decimal('0.61'), '10.00':Decimal('1.36')}

    order_taxfree_total -   the final tax free price of this order.
    '''
    # contains order totals using the new taxfree values
    order_totals = {'order_taxfree_total': Decimal('0.0'), 'order_tax_total': {}, 'order_total': Decimal('0.0')}
    # iterate through each unique tax % found
    for perc in list(set(x['tax_percentage'] for x in all_products)):
        # list containing products with tax_percentage == perc
        perc_products = filter(lambda seq: product_has_given_tax_percentage(seq, perc), all_products)
        # total tax free price for products of this specific VAT %.
        perc_taxfree_total = Decimal('0.0')
        for prod in list(perc_products):
            '''
            iterate through all products that have tax_percentage == perc.
            perc_taxfree_total - sum of the tax free total for each product.
            '''
            perc_taxfree_total += prod['product_taxfree_total']

        # add total taxfree price for this VAT% to the orders taxfree total
        order_totals['order_taxfree_total'] += perc_taxfree_total

        # add total taxfree price for this VAT to the orders total
        order_totals['order_total'] += perc_taxfree_total

        # calculate exact vat value for total taxfree price, 36.30 * 24 / 100
        # this contains all of the decimals.
        exact_vat_amount_value = (perc_taxfree_total * perc) / 100

        # rounded version of the VAT total
        rounded_vat_amount_value = exact_vat_amount_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # add the total rounded VAT value to the orders tax_total
        order_totals['order_tax_total'][perc] = rounded_vat_amount_value

        # add total rounded VAT value for this VAT to the orders total.
        order_totals['order_total'] += rounded_vat_amount_value

    return {
        'final_order_totals': order_totals
    }

def product_has_given_tax_percentage(product, percentage):
    '''
    Return True if product['tax_percentage'] is percentage.
    '''
    if product['tax_percentage'] == percentage:
        return True

    return False


def is_reservation_metadata_or_times_different(old_reservation, new_reservation) -> bool:
    '''
    Return True if metadata fields or reservation begin or end changed
    '''
    field_names = new_reservation.resource.get_supported_reservation_extra_field_names()
    for field_name in field_names:
        if hasattr(old_reservation, field_name) and getattr(old_reservation, field_name) != getattr(new_reservation, field_name):
            return True

    if old_reservation.end != new_reservation.end or old_reservation.begin != new_reservation.begin:
        return True

    return False


def has_reservation_data_changed(data, instance) -> bool:
    """
    Returns True when given data has changes compared to reservation instance
    and False when not.
    """
    if instance == None:
        return False

    for field, value in data.items():
        if getattr(instance, field) != value:
            return True

    return False
