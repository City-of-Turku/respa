import pytz
import requests
import json

from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
from resources.models import Reservation

from .exceptions import InvalidStatusCodeException

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_CREATED = 201

tz = pytz.timezone(settings.TIME_ZONE)

headers = {
  'User-Agent': 'Respa API',
  'Accept': 'application/json',
  'Content-Type': 'application/json',
  'From': settings.SERVER_EMAIL
}
class TimmiManager:
    def __init__(self, **kwargs):
        self.auth = HTTPBasicAuth(settings.TIMMI_USERNAME, settings.TIMMI_PASSWORD)
        self.config = self.get_config()
        self.request = kwargs.get('request', None)
 
    def get_config(self):
        return {
            'BOOKING_ENDPOINT': '{api_base}/bookings/{admin_id}'.format(api_base=settings.TIMMI_API_URL, admin_id=settings.TIMMI_ADMIN_ID),
            'NEW_RESERVATION_ENDPOINT': '{api_base}/cashreceipts/{admin_id}'.format(api_base=settings.TIMMI_API_URL, admin_id=settings.TIMMI_ADMIN_ID),
            'AVAILABLE_TIMES_ENDPOINT': '{api_base}/cashregisters/{admin_id}'.format(api_base=settings.TIMMI_API_URL, admin_id=settings.TIMMI_ADMIN_ID),
            'ROOMPROFILES_ENDPOINT': '{api_base}/roomprofiles/{admin_id}'.format(api_base=settings.TIMMI_API_URL, admin_id=settings.TIMMI_ADMIN_ID)
        }

    def ts_past(self, days):
        return (datetime.now(tz=tz).replace(minute=0, second=0, microsecond=0) - timedelta(days=days))
    
    def ts_future(self, days):
        return (datetime.now(tz=tz).replace(minute=0, second=0, microsecond=0) + timedelta(days=days))

    def create_reservation(self, reservation: Reservation, **kwargs):
        """Create reservation with Timmi, locking the timeslots.

        Args:
            reservation ([Reservation]): [Reservation instance]

        Returns:
            [dict]: Request response for the confirm_reservation function.
        """

        endpoint = self.config['NEW_RESERVATION_ENDPOINT']
        slots = self.get_available_slots(reservation.resource, reservation.begin, reservation.end)
        if not slots:
            return {}
        for slot in slots:
            slot['booking'].update({
                'bookingCustomer': {
                    'identityCode': reservation.user.oid,
                    'firstName': reservation.billing_first_name,
                    'familyName': reservation.billing_last_name,
                    'postalAddress': reservation.billing_address_street,
                    'postalZipCode': reservation.billing_address_zip,
                    'postalCity': reservation.billing_address_city
                }
            })

        payload = {
            'paymentType': 'E',
            'cashProduct': slots
        }
        response = requests.post(endpoint, headers=headers, timeout=settings.TIMMI_TIMEOUT, auth=self.auth, json=payload)

        if response.status_code != 201:
            raise InvalidStatusCodeException("Invalid status code: %u" % response.status_code)

        data = json.loads(response.content.decode())
        return data

    def confirm_reservation(self, reservation, payload, **kwargs):
        """Confirm reservation with Timmi after the payment.

        Args:
            reservation ([Reservation]): [Reservation instance.]
            payload ([dict]): [Request response from Timmi.]

        Returns:
            [Reservation]: Modified reservation.
        """

        endpoint = self.config['NEW_RESERVATION_ENDPOINT']
        payload['paymentType'] = 'W'
        response = requests.post(endpoint, headers=headers, timeout=settings.TIMMI_TIMEOUT, auth=self.auth, json=payload)

        if response.status_code != 201:
            raise InvalidStatusCodeException("Invalid status code: %u" % response.status_code)

        data = json.loads(response.content.decode())
        reservation.timmi_id = data['id']
        reservation.timmi_receipt = data['formattedReceipt']
        return reservation

    def get_reservations(self, resource, begin=None, end=None):
        """Get reservations from the Timmi API

        Args:
            resource ([Resource]): [Resource instance]
            begin ([datetime], optional): Defaults to None.
            end ([datetime], optional): Defaults to None.

        Returns:
            [list]: [{
                'begin': %Y-%m-%dT%H:%M:%S%z
                'end': %Y-%m-%dT%H:%M:%S%z
            }]
        """

        if self.request:
            begin = self.request.GET.get('start', self.ts_past(1)) if not begin else begin
            end = self.request.GET.get('end', self.ts_future(30)) if not end else end

        endpoint = self.config['BOOKING_ENDPOINT']
        response = requests.get(endpoint, headers=headers, timeout=settings.TIMMI_TIMEOUT, auth=self.auth, params={
            'roomPartId': resource.timmi_room_id,
            'startTime': begin.isoformat() if not isinstance(begin, str) else begin,
            'endTime': end.isoformat() if not isinstance(end, str) else end
        })

        if response.status_code not in (HTTP_OK, HTTP_NOT_FOUND):
            raise InvalidStatusCodeException("Invalid status code: %u" % response.status_code)
        ret = []
        if response.status_code == 200:
            data = json.loads(response.content.decode())
            for booking in data['list']:
                ret.append(self._clean(booking))
        return ret
    
    def _clean(self, booking):
        return {
            'begin': booking['startTime'],
            'end': booking['endTime']
        }

    def get_available_slots(self, resource, begin, end):
        """Get available time slots for the resource, using reservation.begin && reservation.end

        Args:
            resource ([Resource]): [Resource instance]
            begin ([datetime]):
            end ([datetime]):

        Returns:
            [list]
        """

        endpoint = self.config['AVAILABLE_TIMES_ENDPOINT']
        response = requests.get(endpoint, headers=headers, timeout=settings.TIMMI_TIMEOUT, auth=self.auth, params={
            'roomPartId': resource.timmi_room_id,
            'startTime': begin.isoformat(),
            'endTime': end.isoformat(),
            'duration': resource.min_period.seconds // 60
        })
        if response.status_code != 200:
            raise InvalidStatusCodeException("Invalid status code: %u" % response.status_code)

        data = json.loads(response.content.decode())
        return data['cashProduct']

    def bind(self, resource, response):
        """Extend resource api response with Timmi reservations

        Args:
            resource ([Resource]): [Resource instance]
            response ([Response])

        Returns:
            [Response]: [Response with overwritten reservations.]
        """

        if not isinstance(response.data['reservations'], list):
            response.data['reservations'] = []
        response.data['reservations'].extend(self.get_reservations(resource))
        return response

    def get_room_part_id(self, resource):
        if not resource.unit.timmi_profile_id:
            raise ValidationError({
                'timmi_room_id': _('Resource Unit does not have timmi profile id set.')
                })
        endpoint = '%s/%s' % (self.config['ROOMPROFILES_ENDPOINT'], resource.unit.timmi_profile_id)
        response = requests.get(endpoint, headers=headers, timeout=settings.TIMMI_TIMEOUT, auth=self.auth, params={
            'includeRoomParts': True
        })
        if response.status_code != 200:
            raise ValidationError({
                'timmi_room_id': _('Failed to fetch roompart id for resource, returned status: %s' % response.status_code)
            })

        data = json.loads(response.content.decode())
        room = next((x for x in data['roomPart'] if x['name'] == resource.name), None)
        if not room:
            raise ValidationError({
                'timmi_room_id': _('No ID found with resource name, make sure the resource name is identical.')
            })
        resource.timmi_room_id = room['id']