import pytz
import requests
import json

from django.conf import settings
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta

from resources.models import Reservation


tz = pytz.timezone(settings.TIME_ZONE)

headers = {
  'User-Agent': 'Respa API',
  'Accept': 'application/json',
  'Content-Type': 'application/json',
  'From': settings.SERVER_EMAIL
}
class TimmiManager:
    def __init__(self):
        self.auth = HTTPBasicAuth(settings.TIMMI_USERNAME, settings.TIMMI_PASSWORD)
        self.config = self.get_config()

    def get_config(self):
        return {
            'BOOKING_ENDPOINT': '{api_base}/bookings/{admin_id}'.format(api_base=settings.TIMMI_API_URL, admin_id=settings.TIMMI_ADMIN_ID),
            'NEW_RESERVATION_ENDPOINT': '{api_base}/cashreceipts/{admin_id}'.format(api_base=settings.TIMMI_API_URL, admin_id=settings.TIMMI_ADMIN_ID),
            'AVAILABLE_TIMES_ENDPOINT': '{api_base}/cashregisters/{admin_id}'.format(api_base=settings.TIMMI_API_URL, admin_id=settings.TIMMI_ADMIN_ID)
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
        slots = self.get_available_slots(reservation.resource, reservation.begin.isoformat(), reservation.end.isoformat())
        if not slots:
            return {}
        for slot in slots:
            slot['booking'].update({
                'bookingCustomer': {
                    'identityCode': '61089',
                    'firstName': 'Nordea',
                    'familyName': 'Demo',
                    'postalAddress': 'Mansikkatie 11',
                    'postalZipCode': '20006',
                    'postalCity': 'TURKU'
                }
            })
            """
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
            """

        payload = {
            'paymentType': 'E',
            'cashProduct': slots
        }
        response = requests.post(endpoint, headers=headers, timeout=settings.TIMMI_TIMEOUT, auth=self.auth, json=payload)
        if response.status_code == 201:
            data = json.loads(response.content.decode())
            return data
        return {}

    def confirm_reservation(self, reservation, payload, **kwargs):
        """Confirm reservation with Timmi after the payment.

        Args:
            reservation ([Reservation]): [Reservation instance.]
            payload ([dict]): [Request response from Timmi.]

        Returns:
            [dict]: [{
                'reservation': Reservation instance,
                'status_code': Request response status code
            }]
        """

        endpoint = self.config['NEW_RESERVATION_ENDPOINT']
        payload['paymentType'] = 'W'
        response = requests.post(endpoint, headers=headers, timeout=settings.TIMMI_TIMEOUT, auth=self.auth, json=payload)
        if response.status_code == 201:
            data = json.loads(response.content.decode())
            reservation.timmi_id = data['id']
            reservation.timmi_receipt = data['formattedReceipt']
        return {
            'reservation': reservation,
            'status_code': response.status_code
        }

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

        endpoint = self.config['BOOKING_ENDPOINT']
        response = requests.get(endpoint, headers=headers, timeout=settings.TIMMI_TIMEOUT, auth=self.auth, params={
            'roomPartId': resource.timmi_room_id,
            'startTime': self.ts_past(1).isoformat() if not begin else begin.isoformat(),
            'endTime': self.ts_future(30).isoformat() if not end else end.isoformat()
        })
        if response.status_code == 200:
            data = json.loads(response.content.decode())
            ret = []
            for booking in data['list']:
                ret.append(self._clean(booking))
            return ret
        return []
    
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
            'startTime': begin,
            'endTime': end,
            'duration': resource.min_period.seconds // 60
        })
        if response.status_code == 200:
            data = json.loads(response.content.decode())
            return data['cashProduct']
        return []

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