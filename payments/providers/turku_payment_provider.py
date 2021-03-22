import logging
from requests.exceptions import RequestException
from django.http import HttpResponse
import requests
import json
from hashlib import sha256, md5
from datetime import datetime
import pytz

from django.utils.translation import gettext_lazy as _

from ..models import Order, OrderLine
from ..utils import round_price

from .base import PaymentProvider
logger = logging.getLogger(__name__)

from ..exceptions import (
    DuplicateOrderError, OrderStateTransitionError, PayloadValidationError, ServiceUnavailableError,
    UnknownReturnCodeError
)

from resources.timmi import TimmiManager
from resources.models import TimmiPayload

# Keys the provider expects to find in the config
RESPA_PAYMENTS_TURKU_API_URL = 'RESPA_PAYMENTS_TURKU_API_URL'
RESPA_PAYMENTS_TURKU_API_KEY = 'RESPA_PAYMENTS_TURKU_API_KEY'
RESPA_PAYMENTS_TURKU_API_APP_NAME = 'RESPA_PAYMENTS_TURKU_API_APP_NAME'

class TurkuPaymentProvider(PaymentProvider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.url_payment_api = self.config.get(RESPA_PAYMENTS_TURKU_API_URL)

    @staticmethod
    def get_config_template() -> dict:
        """Keys and value types that MaksuPalvelu requires from environment"""
        return {
            RESPA_PAYMENTS_TURKU_API_URL: str,
            RESPA_PAYMENTS_TURKU_API_KEY: str,
            RESPA_PAYMENTS_TURKU_API_APP_NAME: str,
        }

    def initiate_payment(self, order) -> str:
        """Initiate payment by constructing the payload with necessary items"""
        if order.reservation.resource.timmi_resource:
            logger.debug("Creating reservation with Timmi API")
            timmi_payload = TimmiManager().create_reservation(order.reservation)
            timmi = TimmiPayload(order=order)
            timmi.save(payload=timmi_payload)

        payload = {
            'orderNumber': str(order.order_number),
            'currency': 'EUR',
            'locale': self.get_order_locale(order),
            'urlSet': {
                'success': self.get_success_url(),
                'failure': self.get_failure_url(),
                'pending': '',
                'notification': self.get_notify_url()
            },
            'orderDetails': {
                'includeVat': '0',
            }
        }
        self.payload_add_customer(payload, order)
        self.payload_add_products(payload, order)

        timezone = pytz.timezone('UTC')
        timestamp = str(datetime.now(tz=timezone).strftime('%Y-%m-%dT%H:%M:%SZ'))
        user_oid = order.reservation.user.oid

        headers = {
            'X-TURKU-SP': self.config.get(RESPA_PAYMENTS_TURKU_API_APP_NAME),
            'X-TURKU-TS': timestamp,
            'X-TURKU-OID': '%s' % user_oid,
            'X-MERCHANT-ID': 'TURKU',
            'Authorization': self.create_auth_header(timestamp, payload)
        }

        try:
            r = requests.post(self.url_payment_api, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            return self.handle_initiate_payment(r.json())
        except RequestException as e:
            logger.warning("Payment service is unreachable: %s" % e)
            raise ServiceUnavailableError(_("Payment service is unreachable")) from e

    def get_order_locale(self, order) -> str:
        if hasattr(order.reservation, 'preferred_language'):
            locale = order.reservation.preferred_language
            if locale == 'sv':
                return 'sv_SE'
            elif locale == 'en':
                return 'en_US'

        return 'fi_FI'

    def create_auth_header(self, timestamp, payload):
        auth = b'%s' % self.config.get(RESPA_PAYMENTS_TURKU_API_APP_NAME).encode()
        auth += b'%s' % timestamp.encode()
        auth += b'%s' % json.dumps(payload).encode()
        auth += b'%s'% self.config.get(RESPA_PAYMENTS_TURKU_API_KEY).encode()
        m = sha256()
        m.update(auth)
        return m.hexdigest()


    def handle_initiate_payment(self, response) -> str:
        """Handling the payment response"""
        errors = response.get('errors')

        if response.get('url'):
            return response.get('url')
        elif errors:
            error_list = []
            for error in errors:
                error_list.append(str(error.get('message', 'Unknown error')))
            logger.warning("Payment payload data validation failed: %s" % ", ".join(error_list))
            raise PayloadValidationError(_("Failed to initiate payment process"))
        else:
            logger.warning("Unknown error occurred during payment processing")
            raise UnknownReturnCodeError(_("Failed to initiate payment process"))

    def payload_add_customer(self, payload, order):
        """Attach customer data to payload"""
        reservation = order.reservation
        contact = {
            'telephone': reservation.billing_phone_number,
            'mobile': reservation.billing_phone_number,
            'email': reservation.billing_email_address,
            'firstName': reservation.billing_first_name,
            'lastName': reservation.billing_last_name,
            'companyName': '',
            'address': {
                'street': reservation.billing_address_street,
                'postalCode': reservation.billing_address_zip,
                'postalOffice': reservation.billing_address_city,
                'country': 'FI'
            }
        }
        payload['orderDetails']['contact'] = contact

    def payload_add_products(self, payload, order):
        """Attach info of bought products to payload

        Order lines that contain bought products are retrieved through order"""
        reservation = order.reservation
        order_lines = OrderLine.objects.filter(order=order.id)
        items = []
        for order_line in order_lines:
            product = order_line.product
            int_tax = int(product.tax_percentage)
            assert int_tax == product.tax_percentage
            items.append({
                'title': product.name,
                'code': product.sku,
                'sapCode': product.sap_code,
                'amount': str(order_line.quantity),
                'price':  str(round_price(product.get_pretax_price_for_reservation(reservation))),
                'vat': str(int_tax),
                'discount': '0.00',
                'type': '1'
            })
        payload['orderDetails']['products'] = items


    def handle_success_request(self):  # noqa: C901
        """Handle the MaksuPalvelu response after user has completed the payment successfully"""
        request = self.request
        logger.debug('Handling MaksuPalvelu user return request, params: {}.'.format(request.GET))

        if not self.check_new_payment_authcode(request):
            return self.ui_redirect_failure()

        try:
            order = Order.objects.get(order_number=request.GET['ORDER_NUMBER'])
        except Order.DoesNotExist:
            logger.warning('Order does not exist.')
            return self.ui_redirect_failure()

        logger.debug('Payment completed successfully.')

        try:
            order.set_state(Order.CONFIRMED, 'Payment succeeded in MaksuPalvelu success request.')
            if order.reservation.resource.timmi_resource:
                timmi_payload = TimmiPayload.objects.get(order=order)
                logger.debug('Confirming reservation with Timmi API.')
                TimmiManager().confirm_reservation(order.reservation, timmi_payload.payload).save()
                timmi_payload.delete()
            return self.ui_redirect_success(order)
        except OrderStateTransitionError as oste:
            logger.warning(oste)
            order.create_log_entry('Payment succeeded in MaksuPalvelu success request.')
            return self.ui_redirect_failure(order)

    def handle_failure_request(self):
        """Handle the MaksuPalvelu response after user payment has failed"""
        request = self.request
        logger.debug('Handling MaksuPalvelu user return payment failed request, params: {}.'.format(request.GET))

        if not self.check_new_payment_authcode(request):
            return self.ui_redirect_failure()

        try:
            order = Order.objects.get(order_number=request.GET['ORDER_NUMBER'])
        except Order.DoesNotExist:
            logger.warning('Order does not exist.')
            return self.ui_redirect_failure()
        logger.debug('Payment failed')
        try:
            order.set_state(Order.REJECTED, 'Payment rejected in MaksuPalvelu failure request.')
            return self.ui_redirect_failure(order)
        except OrderStateTransitionError as oste:
            logger.warning(oste)
            order.create_log_entry('Payment rejected in MaksuPalvelu failure request.')
            return self.ui_redirect_failure(order)

    def handle_notify_request(self):
        """Handle the MaksuPalvelu asynchronous response"""
        request = self.request
        logger.debug('Handling MaksuPalvelu notify request, params: {}.'.format(request.GET))

        if not self.check_new_payment_authcode(request):
            return HttpResponse(status=200)

        try:
            order = Order.objects.get(order_number=request.GET['ORDER_NUMBER'])
        except Order.DoesNotExist:
            # Target order might be deleted after posting but before the notify arrives
            logger.warning('Notify: Order does not exist.')
            return HttpResponse(status=200)

        if request.GET.get('PAID'):
            logger.debug('Notify: Payment completed successfully.')
            try:
                order.set_state(Order.CONFIRMED, 'Payment succeeded in MaksuPalvelu notify request.')
            except OrderStateTransitionError as oste:
                logger.warning(oste)
        else:
            logger.debug('Notify: Payment failed.')
            try:
                order.set_state(Order.REJECTED, 'Payment rejected in MaksuPalvelu notify request.')
            except OrderStateTransitionError as oste:
                logger.warning(oste)

        return HttpResponse(status=200)


    def check_new_payment_authcode(self, request):
        """Validate that success/failure/notify payload authcode matches"""
        is_valid = True
        auth_code_calculation_values = [
            request.GET[param_name]
            for param_name in ('ORDER_NUMBER', 'TIMESTAMP', 'PAID', 'METHOD')
            if param_name in request.GET
        ]
        correct_auth_code = self.calculate_auth_code('|'.join(auth_code_calculation_values))
        auth_code = request.GET['RETURN_AUTHCODE']
        if auth_code != correct_auth_code:
            logger.warning('Incorrect auth code "{}".'.format(auth_code))
            is_valid = False
        return is_valid


    def calculate_auth_code(self, data) -> str:
        """Calculate an md5 out of some data string"""
        data_with_key = data + "|" + self.config.get(RESPA_PAYMENTS_TURKU_API_KEY)
        return md5(data_with_key.encode('utf-8')).hexdigest().upper()
