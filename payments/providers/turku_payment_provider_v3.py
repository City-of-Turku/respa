from decimal import Decimal
from enum import Enum
import logging
import uuid
from requests.exceptions import RequestException
from django.http import HttpResponse
import requests
import json
from hashlib import sha256
from datetime import datetime
import pytz

from django.utils.translation import gettext_lazy as _

from ..models import Order, OrderLine
from ..utils import is_free, round_price

from .base import PaymentProvider
logger = logging.getLogger(__name__)

from ..exceptions import (
    DuplicateOrderError, OrderStateTransitionError, PayloadValidationError, ServiceUnavailableError,
    UnknownReturnCodeError
)

from resources.timmi import TimmiManager, MissingSapUnitError, MissingSapCodeError
from resources.models import TimmiPayload

# Keys the provider expects to find in the config
RESPA_PAYMENTS_TURKU_API_URL = 'RESPA_PAYMENTS_TURKU_API_URL'
RESPA_PAYMENTS_TURKU_API_KEY = 'RESPA_PAYMENTS_TURKU_API_KEY'
RESPA_PAYMENTS_TURKU_API_APP_NAME = 'RESPA_PAYMENTS_TURKU_API_APP_NAME'
RESPA_PAYMENTS_TURKU_SAP_SALES_ORGANIZATION = 'RESPA_PAYMENTS_TURKU_SAP_SALES_ORGANIZATION' # 4 chars
RESPA_PAYMENTS_TURKU_SAP_DISTRIBUTION_CHANNEL = 'RESPA_PAYMENTS_TURKU_SAP_DISTRIBUTION_CHANNEL' # 2 chars
RESPA_PAYMENTS_TURKU_SAP_SECTOR = 'RESPA_PAYMENTS_TURKU_SAP_SECTOR' # 2 chars


class RequestTypes(Enum):
    CALLBACK = 1
    REDIRECT = 2


class TurkuPaymentProviderV3(PaymentProvider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.url_payment_api = self.config.get(RESPA_PAYMENTS_TURKU_API_URL)

    @staticmethod
    def get_config_template() -> dict:
        """Keys and value types that MaksuPalvelu V3 requires from environment"""
        return {
            RESPA_PAYMENTS_TURKU_API_URL: str,
            RESPA_PAYMENTS_TURKU_API_KEY: str,
            RESPA_PAYMENTS_TURKU_API_APP_NAME: str,
            RESPA_PAYMENTS_TURKU_SAP_SALES_ORGANIZATION: str,
            RESPA_PAYMENTS_TURKU_SAP_DISTRIBUTION_CHANNEL: str,
            RESPA_PAYMENTS_TURKU_SAP_SECTOR: str,
        }

    def initiate_payment(self, order) -> str:
        """Initiate payment by constructing the payload with necessary items"""
        if order.reservation.resource.timmi_resource:
            logger.debug("Creating reservation with Timmi API")
            timmi_payload = TimmiManager().create_reservation(order.reservation)
            timmi = TimmiPayload(order=order)
            timmi.save(payload=timmi_payload)


        if is_free(order.get_price()):
            # don't update reservation state here, it is handled later
            order.set_state(Order.CONFIRMED, 'Order has no price.', True, False)
            if order.reservation.resource.timmi_resource:
                logger.debug('Confirming reservation with Timmi API.')
                TimmiManager().confirm_reservation(order.reservation, timmi_payload.payload).save()
                timmi_payload.delete()
            return '/reservation-payment-return?payment_status=success&reservation_id={0}'.format(order.reservation.id)


        payload = {
            'stamp': str(uuid.uuid4()),
            'reference': str(order.order_number),
            'amount': self.convert_price_to_cents(round_price(order.get_price())),
            'currency': 'EUR',
            'language': self.get_order_locale(order),
            'redirectUrls': {
                'success': self.get_success_url(),
                'cancel': self.get_failure_url(),
            },
            'callbackUrls': {
                'success': self.get_notify_url(),
                'cancel': self.get_notify_url(),
            },
            'usePricesWithoutVat': False
        }
        self.payload_add_sap_organization_details(payload)
        self.payload_add_customer(payload, order)
        self.payload_add_invoice_address(payload, order)
        self.payload_add_products(payload, order)

        timezone = pytz.timezone('UTC')
        timestamp = str(datetime.now(tz=timezone).strftime('%Y-%m-%dT%H:%M:%SZ'))
        user_oid = order.reservation.user.oid

        headers = {
            'Content-Type': 'application/json',
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
            self.handle_request_errors(r, e)


    def get_order_locale(self, order) -> str:
        if hasattr(order.reservation, 'preferred_language'):
            locale = order.reservation.preferred_language
            if locale == 'sv':
                return 'SV'
            elif locale == 'en':
                return 'EN'
        return 'FI'


    def create_auth_header(self, timestamp, payload):
        auth = b'%s' % self.config.get(RESPA_PAYMENTS_TURKU_API_APP_NAME).encode()
        auth += b'%s' % timestamp.encode()
        auth += b'%s' % json.dumps(payload).encode()
        auth += b'%s'% self.config.get(RESPA_PAYMENTS_TURKU_API_KEY).encode()
        m = sha256()
        m.update(auth)
        return m.hexdigest()


    def handle_request_errors(self, response, error):
        """Handles request errors raised in payment creation"""
        body = response.json()
        body_errors = body.get('errors')
        error_list = []
        if body_errors:
            for body_error in body_errors:
                error_list.append(str(body_error.get('message', 'Unknown error')))

        error_code = error.response.status_code
        if error_code == 400:
            if error_list:
                logger.warning("Payment payload data validation failed: %s" % ", ".join(error_list))
            else:
                logger.warning("Payment payload data validation failed: Unknown error")
            raise PayloadValidationError(_("Failed to initiate payment process"))
        elif error_code == 500:
            if error_list:
                logger.warning("Payment service internal error: %s" % ", ".join(error_list))
            else:
                logger.warning("Payment service internal error: Unknown error")
            raise ServiceUnavailableError(_("Failed to initiate payment process"))
        else:
            logger.warning("Payment service is unreachable: %s" % error)
            raise ServiceUnavailableError(_("Payment service is unreachable"))


    def handle_initiate_payment(self, response) -> str:
        """Handling the payment response"""
        if response.get('href'):
            return response.get('href')
        else:
            logger.warning("Unknown error occurred during payment processing")
            raise UnknownReturnCodeError(_("Failed to initiate payment process"))


    def payload_add_sap_organization_details(self, payload):
        """Attach sap organization data to payload"""
        sap_details = {
            'sapSalesOrganization': self.config.get(RESPA_PAYMENTS_TURKU_SAP_SALES_ORGANIZATION),
            'sapDistributionChannel': self.config.get(RESPA_PAYMENTS_TURKU_SAP_DISTRIBUTION_CHANNEL),
            'sapSector': self.config.get(RESPA_PAYMENTS_TURKU_SAP_SECTOR),
        }
        payload['sapOrganizationDetails'] = sap_details


    def payload_add_customer(self, payload, order):
        """Attach customer data to payload"""
        reservation = order.reservation
        customer = {
            'email': reservation.billing_email_address,
            'firstName': reservation.billing_first_name,
            'lastName': reservation.billing_last_name,
            'phone': reservation.billing_phone_number,
        }
        payload['customer'] = customer


    def payload_add_invoice_address(self, payload, order):
        """Attach invoice address data to payload"""
        reservation = order.reservation
        invoicingAddress = {
            'streetAddress': reservation.billing_address_street,
            'postalCode': reservation.billing_address_zip,
            'city': reservation.billing_address_city,
            'country': 'FI'
        }
        payload['invoicingAddress'] = invoicingAddress


    def payload_add_products(self, payload, order):
        """
        Attach info of bought products to payload.
        Order lines that contain bought products are retrieved through order
        """
        order_lines = OrderLine.objects.filter(order=order.id)
        items = []

        for order_line in order_lines:
            # add customer group id to order if it's not stored yet
            if order.customer_group and not order_line.order.customer_group:
                order_line.order._in_memory_customer_group_id = order.customer_group.id

            product = order_line.product
            product_data = {
                'unitPrice': self.convert_price_to_cents(round_price(order_line.get_unit_price())),
                'units': str(order_line.quantity),
                'vatPercentage': str(product.tax_percentage),
                'productCode': product.sku,
                'description': product.name,
            }
            self.product_add_sap_data(product_data, product, order)
            items.append(product_data)
        payload['items'] = items


    def product_add_sap_data(self, payload, product, order):
        """Attach product sap data to product data"""

        sap_data = {
            'sapCode': product.sap_code, # 18 chars
            'sapOfficeCode': product.sap_office_code, # 4 chars
        }
        # optional sap data
        if product.sap_function_area:
            sap_data['sapFunctionArea'] = product.sap_function_area # 16 chars
        if product.sap_unit:
            sap_data['sapProfitCenter'] = product.sap_unit # 10 numbers

        reservation = order.reservation
        resource = reservation.resource
        if resource.timmi_resource:
            timmi_payload = TimmiPayload.objects.get(order=order)
            try:
                sap_data['sapCode'] = timmi_payload.sap_code
                sap_data['sapProfitCenter'] = timmi_payload.sap_unit
            except (MissingSapUnitError, MissingSapCodeError):
                    return self.ui_redirect_failure()
        payload['sapProduct'] = sap_data


    def handle_success_request(self):  # noqa: C901
        """Handle the MaksuPalvelu response after user has completed the payment successfully"""
        request = self.request
        logger.debug('Handling MaksuPalvelu user return request, params: {}.'.format(request.GET))
        if not self.check_new_payment_authcode(request, RequestTypes.REDIRECT):
            return self.ui_redirect_failure()

        try:
            order = Order.objects.get(order_number=request.GET['checkout-reference'])
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

        if not self.check_new_payment_authcode(request, RequestTypes.REDIRECT):
            return self.ui_redirect_failure()

        try:
            order = Order.objects.get(order_number=request.GET['checkout-reference'])
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
        logger.debug('Handling MaksuPalvelu notify request, body params: {}.'.format(request.body))

        if not self.check_new_payment_authcode(request, RequestTypes.CALLBACK):
            return HttpResponse(status=200)

        request_body_data = json.loads(request.body)

        try:
            order_number = request_body_data.get('checkout-reference', '')
            order = Order.objects.get(order_number=order_number)
        except Order.DoesNotExist:
            # Target order might be deleted after posting but before the notify arrives
            logger.warning('Notify: Order does not exist.')
            return HttpResponse(status=200)

        if request_body_data.get('checkout-status') == 'ok':
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


    def check_new_payment_authcode(self, request, request_type):
        """Validate that success/failure/notify payload authcode matches"""
        is_valid = True
        auth_data = ''
        given_auth_code = ''
        ts = ''
        if request_type == RequestTypes.REDIRECT:
            # redirects have their data in url params
            query_checkout_fields = [
                f'{param_name}:{request.GET.get(param_name)}'
                for param_name in ('checkout-amount', 'checkout-provider', 'checkout-reference',
                'checkout-stamp', 'checkout-status', 'checkout-transaction-id')
                if param_name in request.GET
            ]
            auth_data = '\n'.join(query_checkout_fields)+'\n'
            given_auth_code = request.GET.get('Authorization', '')
            ts = request.GET.get('X-TURKU-TS', '')
        else:
            # callbacks have their data in request body as json
            auth_data = request.body.decode('utf-8')
            given_auth_code = request.headers.get('Authorization', '')
            ts = request.headers.get('X-TURKU-TS', '')

        correct_auth_code = self.calculate_auth_code(f'{ts}{auth_data}')

        if given_auth_code != correct_auth_code:
            logger.warning('Incorrect auth code "{}".'.format(given_auth_code))
            is_valid = False
        return is_valid


    def calculate_auth_code(self, data) -> str:
        """Calculate a sha256 auth code for given data string"""
        auth = b'%s' % self.config.get(RESPA_PAYMENTS_TURKU_API_APP_NAME).encode()
        auth += b'%s' % data.encode()
        auth += b'%s'% self.config.get(RESPA_PAYMENTS_TURKU_API_KEY).encode()
        m = sha256()
        m.update(auth)
        return m.hexdigest()


    def convert_price_to_cents(self, price: Decimal) -> int:
        """Converts a price given in euros to cents"""
        return int(price*100)
