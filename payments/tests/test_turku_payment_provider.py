from hashlib import md5
import json
from unittest import mock

import pytest
from django.conf import settings
from django.http import HttpResponse, HttpResponseServerError
from django.test.client import RequestFactory
from requests.exceptions import RequestException
from rest_framework.reverse import reverse

from payments.models import Order
from resources.models import Reservation

from payments.providers.turku_payment_provider import (
    RESPA_PAYMENTS_TURKU_API_KEY, TurkuPaymentProvider, DuplicateOrderError, PayloadValidationError,
    ServiceUnavailableError, UnknownReturnCodeError
)

FAKE_TURKU_PAYMENT_API_URL = "https://fake-maksupalvelu-api-url/api"
UI_RETURN_URL = "https://front-end-url.fi"
RESERVATION_LIST_URL = reverse('reservation-list')
PAYMENT_URL = "https://maksupalvelu.payment.com/?params=param"

PAYMENTS_ENABLED = bool(getattr(settings, "RESPA_PAYMENTS_ENABLED", False))

@pytest.fixture(autouse=True)
def auto_use_django_db(db):
    pass


@pytest.fixture()
def provider_base_config():
    return {
        'RESPA_PAYMENTS_TURKU_API_URL': 'https://real-maksupalvelu-api-url/api',
        'RESPA_PAYMENTS_TURKU_API_KEY': 'dummy-key',
        'RESPA_PAYMENTS_TURKU_API_APP_NAME': 'respa-turku',
    }


@pytest.fixture()
def payment_provider(provider_base_config):
    """When it doesn't matter if request is contained within provider the fixture can still be used"""
    return TurkuPaymentProvider(config=provider_base_config)


def create_turku_payment_provider(provider_base_config, request, return_url=None):
    """Helper for creating a new instance of provider with request and optional return_url contained within"""
    return TurkuPaymentProvider(config=provider_base_config,
                                  request=request,
                                  return_url=return_url)


def mocked_response_create(*args, **kwargs):
    """Mock MaksuPalvelu responses based on provider url"""
    class MockResponse:
        def __init__(self, data, status_code=200):
            self.json_data = data
            self.status_code = status_code

        def json(self):
            return self.json_data

        def raise_for_status(self):
            if self.status_code != 200:
                raise RequestException("Mock request error with status_code {}.".format(self.status_code))
            pass

    if args[0].startswith(FAKE_TURKU_PAYMENT_API_URL):
        return MockResponse(data={}, status_code=500)
    else:
        return MockResponse(data={
            "orderNumber": 0,
            "token": "",
            "url": PAYMENT_URL
        })


@pytest.mark.skipif(not PAYMENTS_ENABLED, reason="Payments not enabled")
def test_initiate_payment_success(provider_base_config, order_with_products):
    """Test the request creator constructs the payload base and returns a url"""
    rf = RequestFactory()
    request = rf.post(RESERVATION_LIST_URL)

    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    with mock.patch('payments.providers.turku_payment_provider.requests.post', side_effect=mocked_response_create):
        url = payment_provider.initiate_payment(order_with_products)
        assert url == PAYMENT_URL


@pytest.mark.skipif(not PAYMENTS_ENABLED, reason="Payments not enabled")
def test_initiate_payment_error_unavailable(provider_base_config, order_with_products):
    """Test the request creator raises service unavailable if request doesn't go through"""
    rf = RequestFactory()
    request = rf.post(RESERVATION_LIST_URL)

    provider_base_config['RESPA_PAYMENTS_TURKU_API_URL'] = FAKE_TURKU_PAYMENT_API_URL
    unavailable_payment_provider = create_turku_payment_provider(provider_base_config,
                                                           request, UI_RETURN_URL)

    with mock.patch('payments.providers.turku_payment_provider.requests.post', side_effect=mocked_response_create):
        with pytest.raises(ServiceUnavailableError):
            unavailable_payment_provider.initiate_payment(order_with_products)


@pytest.mark.parametrize('order_preferred_language, expected_locale', (
    ('sv', 'sv_SE'),
    ('en', 'en_US'),
    ('fi', 'fi_FI'),
    ('unknown', 'fi_FI'),
))
def test_get_order_locale(payment_provider, order_with_products, two_hour_reservation,
                            order_preferred_language, expected_locale):
    """Test correct order locale is returned"""
    Reservation.objects.filter(id=two_hour_reservation.id).update(preferred_language=order_preferred_language)
    two_hour_reservation.refresh_from_db()
    locale = payment_provider.get_order_locale(order_with_products)
    assert locale == expected_locale


def test_create_auth_header(payment_provider, order_with_products):
    """Test correct auth header is returned"""
    timestamp = 'test-timestamp'
    payload = {'test': '123'}
    auth_header = payment_provider.create_auth_header(timestamp, payload)
    print(f'authheader: {auth_header}')
    assert auth_header == '2222c74fc705a4bc3fa2f10e391c29fa5503dbe052ddc4ceb6ff2fa4ba4b103e'


def test_handle_initiate_payment_success(payment_provider):
    """Test the response handler recognizes success and returns a url"""
    r = json.loads("""{
        "orderNumber": 0,
        "token": "",
        "url": "https://payment-url.com"
    }""")
    return_value = payment_provider.handle_initiate_payment(r)
    assert return_value == "https://payment-url.com"


def test_handle_initiate_payment_error_validation(payment_provider):
    """Test the response handler raises PayloadValidationError as expected"""
    r = json.loads("""{
        "errors": [{"message": "some error"}]
    }""")
    with pytest.raises(PayloadValidationError):
        payment_provider.handle_initiate_payment(r)


def test_handle_initiate_payment_error_unknown_code(payment_provider):
    """Test the response handler raises UnknownReturnCodeError as expected"""
    r = json.loads("""{
        "unknown_field": 1
    }""")
    with pytest.raises(UnknownReturnCodeError):
        payment_provider.handle_initiate_payment(r)


def test_payload_add_customer_success(payment_provider, order_with_products):
    """Test the customer data from order is added correctly into payload"""
    payload = {"orderDetails": {}}
    payment_provider.payload_add_customer(payload, order_with_products)

    assert 'contact' in payload['orderDetails']
    contact = payload['orderDetails'].get('contact')
    assert contact.get('telephone') == '555555555'
    assert contact.get('mobile') == '555555555'
    assert contact.get('email') == 'test@example.com'
    assert contact.get('firstName') == 'Seppo'
    assert contact.get('lastName') == 'Testi'

    assert 'address' in payload['orderDetails']['contact']
    address = payload['orderDetails']['contact'].get('address')
    assert address.get('street') == 'Test street 1'
    assert address.get('postalCode') == '12345'
    assert address.get('postalOffice') == 'Testcity'
    assert address.get('country') == 'FI'


def test_payload_add_products_success(payment_provider, order_with_products):
    """Test the products are added correctly into payload"""
    payload = { "orderDetails": {} }
    payment_provider.payload_add_products(payload, order_with_products)

    assert 'products' in payload['orderDetails']
    products = payload['orderDetails'].get('products')
    assert len(products) == 2

    for product in products:
        assert 'title' in product
        assert 'code' in product
        assert 'sapCode' in product
        assert 'amount' in product
        assert 'price' in product
        assert 'vat' in product
        assert 'discount' in product
        assert 'type' in product


def test_handle_success_request_order_not_found(provider_base_config, order_with_products):
    """Test request helper returns a failure url when order can't be found"""
    params = {
        'ORDER_NUMBER': '123fgh',
        'TIMESTAMP': '1496999439',
        'PAID': 'abcdefg321',
        'METHOD': '1',
        'RETURN_AUTHCODE': 'F684932DFA6BD2A53D518127893873F1',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    rf = RequestFactory()
    request = rf.get('/payments/success/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)

    returned = payment_provider.handle_success_request()
    assert isinstance(returned, HttpResponse)
    assert 'payment_status=failure' in returned.url


def test_handle_success_request_success(provider_base_config, order_with_products):
    """Test request helper changes the order status to confirmed

    Also check it returns a success url with order number"""
    params = {
        'ORDER_NUMBER': 'abc123',
        'TIMESTAMP': '1496999439',
        'PAID': 'abcdefg321',
        'METHOD': '1',
        'RETURN_AUTHCODE': '28BD6B51ACC929F38D50BD73D33D80E0',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    rf = RequestFactory()
    request = rf.get('/payments/success/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    returned = payment_provider.handle_success_request()
    order_after = Order.objects.get(order_number=params.get('ORDER_NUMBER'))
    assert order_after.state == Order.CONFIRMED
    assert isinstance(returned, HttpResponse)
    assert 'payment_status=success' in returned.url
    assert 'reservation_id={}'.format(order_after.reservation.id) in returned.url


def test_handle_failure_request_order_not_found(provider_base_config, order_with_products):
    """Test request helper returns a failure url when order can't be found"""
    params = {
        'ORDER_NUMBER': '123fgh',
        'TIMESTAMP': '1496999439',
        'RETURN_AUTHCODE': '48A9424A2C64BCF53ADE15B7584D73CF',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    rf = RequestFactory()
    request = rf.get('/payments/failure/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)

    returned = payment_provider.handle_failure_request()
    assert isinstance(returned, HttpResponse)
    assert 'payment_status=failure' in returned.url


def test_handle_failure_request_payment_failed(provider_base_config, order_with_products):
    """Test request helper changes the order status to rejected and returns a failure url"""
    params = {
        'ORDER_NUMBER': 'abc123',
        'TIMESTAMP': '1496999439',
        'RETURN_AUTHCODE': '0224A8AEA1A9B3C5488AED69F66AE3A5',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    rf = RequestFactory()
    request = rf.get('/payments/failure/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    returned = payment_provider.handle_failure_request()
    order_after = Order.objects.get(order_number=params.get('ORDER_NUMBER'))
    assert order_after.state == Order.REJECTED
    assert isinstance(returned, HttpResponse)
    assert 'payment_status=failure' in returned.url


def test_handle_notify_request_order_not_found(provider_base_config, order_with_products):
    """Test request notify helper returns http 200 when order can't be found"""
    params = {
        'ORDER_NUMBER': '123fgh',
        'TIMESTAMP': '1496999439',
        'RETURN_AUTHCODE': '48A9424A2C64BCF53ADE15B7584D73CF',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    rf = RequestFactory()
    request = rf.get('/payments/notify/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    returned = payment_provider.handle_notify_request()
    assert isinstance(returned, HttpResponse)
    assert returned.status_code == 200


@pytest.mark.parametrize('order_state, expected_order_state', (
    (Order.WAITING, Order.CONFIRMED),
    (Order.CONFIRMED, Order.CONFIRMED),
    (Order.EXPIRED, Order.EXPIRED),
    (Order.REJECTED, Order.REJECTED),
))
def test_handle_notify_request_success(provider_base_config, order_with_products, order_state, expected_order_state):
    """Test request notify helper returns http 200 and order status is correct when successful"""
    params = {
        'ORDER_NUMBER': 'abc123',
        'TIMESTAMP': '1496999439',
        'PAID': 'abcdefg321',
        'METHOD': '1',
        'RETURN_AUTHCODE': '28BD6B51ACC929F38D50BD73D33D80E0',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    order_with_products.set_state(order_state)

    rf = RequestFactory()
    request = rf.get('/payments/notify/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    returned = payment_provider.handle_notify_request()
    order_after = Order.objects.get(order_number=params.get('ORDER_NUMBER'))
    assert order_after.state == expected_order_state
    assert isinstance(returned, HttpResponse)
    assert returned.status_code == 200


@pytest.mark.parametrize('order_state, expected_order_state', (
    (Order.WAITING, Order.REJECTED),
    (Order.REJECTED, Order.REJECTED),
    (Order.EXPIRED, Order.EXPIRED),
    (Order.CONFIRMED, Order.CONFIRMED),
))
def test_handle_notify_request_payment_failed(provider_base_config, order_with_products, order_state,
                                              expected_order_state):
    """Test request notify helper returns http 200 and order status is correct when payment fails"""
    params = {
        'ORDER_NUMBER': 'abc123',
        'TIMESTAMP': '1496999439',
        'RETURN_AUTHCODE': '0224A8AEA1A9B3C5488AED69F66AE3A5',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    order_with_products.set_state(order_state)

    rf = RequestFactory()
    request = rf.get('/payments/notify/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    returned = payment_provider.handle_notify_request()
    order_after = Order.objects.get(order_number=params.get('ORDER_NUMBER'))
    assert order_after.state == expected_order_state
    assert isinstance(returned, HttpResponse)
    assert returned.status_code == 200


def test_check_new_payment_authcode_success(payment_provider):
    """Test the helper is able to extract necessary values from a request and compare authcodes"""
    params = {
        'ORDER_NUMBER': 'abc123',
        'TIMESTAMP': '1496999439',
        'PAID': 'abcdefg321',
        'METHOD': '1',
        'RETURN_AUTHCODE': '28BD6B51ACC929F38D50BD73D33D80E0'
    }
    rf = RequestFactory()
    request = rf.get('/payments/success/', params)
    assert payment_provider.check_new_payment_authcode(request)


def test_check_new_payment_authcode_invalid(payment_provider):
    """Test the helper fails when params do not match the auth code"""
    auth_code = payment_provider.calculate_auth_code('123fgh|1496999439|abcdefg321|1')
    params = {
        'ORDER_NUMBER': 'abc123',
        'TIMESTAMP': '1496999439',
        'PAID': 'abcdefg321',
        'METHOD': '1',
        'RETURN_AUTHCODE': auth_code
    }

    rf = RequestFactory()
    request = rf.get('/payments/success/', params)
    assert not payment_provider.check_new_payment_authcode(request)


def test_calculate_auth_code_success(payment_provider):
    """Test the auth code calculation returns a correct string"""
    data = 'some-data'
    data_with_key = data + "|" + payment_provider.config.get(RESPA_PAYMENTS_TURKU_API_KEY)
    calculated_code = payment_provider.calculate_auth_code(data)
    assert calculated_code == md5(data_with_key.encode('utf-8')).hexdigest().upper()
