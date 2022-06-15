from decimal import Decimal
import json
from unittest import mock

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test.client import RequestFactory
from requests.exceptions import RequestException
from rest_framework.reverse import reverse
from payments.exceptions import PayloadValidationError, ServiceUnavailableError, UnknownReturnCodeError

from payments.models import Order, OrderLine
from payments.providers.turku_payment_provider_v3 import RequestTypes, TurkuPaymentProviderV3
from resources.models import Reservation


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
        'RESPA_PAYMENTS_TURKU_SAP_SALES_ORGANIZATION': '1234',
        'RESPA_PAYMENTS_TURKU_SAP_DISTRIBUTION_CHANNEL': '12',
        'RESPA_PAYMENTS_TURKU_SAP_SECTOR': '98'
    }


@pytest.fixture()
def payment_provider(provider_base_config):
    """When it doesn't matter if request is contained within provider the fixture can still be used"""
    return TurkuPaymentProviderV3(config=provider_base_config)


def create_turku_payment_provider(provider_base_config, request, return_url=None):
    """Helper for creating a new instance of provider with request and optional return_url contained within"""
    return TurkuPaymentProviderV3(config=provider_base_config,
                                  request=request,
                                  return_url=return_url)


def mocked_response_create(*args, **kwargs):
    """Mock Verkkomaksupalvelu responses based on provider url"""
    class MockResponse:
        def __init__(self, data, status_code=201):
            self.json_data = data
            self.status_code = status_code

        def json(self):
            return self.json_data

        def raise_for_status(self):
            if self.status_code != 201:
                raise RequestException(
                    "Mock request error with status_code {}.".format(self.status_code),
                    response=MockResponse(data={}, status_code=self.status_code))
            pass

    if args[0].startswith(FAKE_TURKU_PAYMENT_API_URL):
        return MockResponse(data={}, status_code=500)
    else:
        return MockResponse(data={
            "transactionId": 0,
            "terms": "abc",
            "href": PAYMENT_URL
        })


@pytest.mark.skipif(not PAYMENTS_ENABLED, reason="Payments not enabled")
def test_initiate_payment_success(provider_base_config, order_with_products):
    """Test the request creator constructs the payload base and returns a url"""
    rf = RequestFactory()
    request = rf.post(RESERVATION_LIST_URL)

    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    with mock.patch('payments.providers.turku_payment_provider_v3.requests.post', side_effect=mocked_response_create):
        href = payment_provider.initiate_payment(order_with_products)
        assert href == PAYMENT_URL


@pytest.mark.skipif(not PAYMENTS_ENABLED, reason="Payments not enabled")
def test_initiate_payment_success_free(provider_base_config, order_with_no_price_product_customer_group):
    """Test the request creator returns correct url when order is free"""
    rf = RequestFactory()
    request = rf.post(RESERVATION_LIST_URL)

    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    with mock.patch('payments.providers.turku_payment_provider_v3.requests.post', side_effect=mocked_response_create):
        href = payment_provider.initiate_payment(order_with_no_price_product_customer_group)
        reservation_id = order_with_no_price_product_customer_group.reservation.id
        expected_href = '/reservation-payment-return?payment_status=success&reservation_id={0}'.format(reservation_id)
        assert href == expected_href


@pytest.mark.skipif(not PAYMENTS_ENABLED, reason="Payments not enabled")
@mock.patch("payments.providers.turku_payment_provider_v3.TurkuPaymentProviderV3.handle_request_errors")
def test_initiate_payment_calls_handle_errors(handle_request_errors, provider_base_config, order_with_products):
    """Test the request creator calls handle_request_errors when an error occurs"""
    rf = RequestFactory()
    request = rf.post(RESERVATION_LIST_URL)

    provider_base_config['RESPA_PAYMENTS_TURKU_API_URL'] = FAKE_TURKU_PAYMENT_API_URL
    unavailable_payment_provider = create_turku_payment_provider(provider_base_config,
                                                           request, UI_RETURN_URL)

    with mock.patch('payments.providers.turku_payment_provider_v3.requests.post', side_effect=mocked_response_create):
        unavailable_payment_provider.initiate_payment(order_with_products)
        handle_request_errors.assert_called_once()


@pytest.mark.skipif(not PAYMENTS_ENABLED, reason="Payments not enabled")
def test_initiate_payment_error_unavailable(provider_base_config, order_with_products):
    """Test the request creator raises service unavailable if request doesn't go through"""
    rf = RequestFactory()
    request = rf.post(RESERVATION_LIST_URL)

    provider_base_config['RESPA_PAYMENTS_TURKU_API_URL'] = FAKE_TURKU_PAYMENT_API_URL
    unavailable_payment_provider = create_turku_payment_provider(provider_base_config,
                                                           request, UI_RETURN_URL)

    with mock.patch('payments.providers.turku_payment_provider_v3.requests.post', side_effect=mocked_response_create):
        with pytest.raises(ServiceUnavailableError):
            unavailable_payment_provider.initiate_payment(order_with_products)


@pytest.mark.parametrize('order_preferred_language, expected_locale', (
    ('sv', 'SV'),
    ('en', 'EN'),
    ('fi', 'FI'),
    ('unknown', 'FI'),
))
def test_get_order_locale(payment_provider, order_with_products, two_hour_reservation,
                            order_preferred_language, expected_locale):
    """Test correct order locale is returned"""
    Reservation.objects.filter(id=two_hour_reservation.id).update(preferred_language=order_preferred_language)
    two_hour_reservation.refresh_from_db()
    locale = payment_provider.get_order_locale(order_with_products)
    assert locale == expected_locale


def test_create_auth_header(payment_provider):
    """Test correct auth header is returned"""
    timestamp = 'test-timestamp'
    payload = {'test': '123'}
    auth_header = payment_provider.create_auth_header(timestamp, payload)
    assert auth_header == '2222c74fc705a4bc3fa2f10e391c29fa5503dbe052ddc4ceb6ff2fa4ba4b103e'


@pytest.mark.parametrize('status_code, expected_error', (
    (400, PayloadValidationError),
    (500, ServiceUnavailableError),
    (432, ServiceUnavailableError),
))
def test_handle_request_errors(status_code, expected_error, payment_provider):
    """Test correct errors are raised"""
    mock_response = mock.Mock(json_data={
        'test': 'test response'
    })
    mock_response.json = lambda : mock_response.json_data
    mock_error_response = mock.Mock()
    mock_error_response.status_code = status_code

    with pytest.raises(expected_error):
        payment_provider.handle_request_errors(
            mock_response, RequestException('mock error', response=mock_error_response)
        )


def test_handle_initiate_payment_success(payment_provider):
    """Test the response handler recognizes success and returns a url"""
    r = json.loads("""{
        "transactionId": 0,
        "terms": "abc",
        "href": "https://payment-url.com"
    }""")
    return_value = payment_provider.handle_initiate_payment(r)
    assert return_value == "https://payment-url.com"


def test_handle_initiate_payment_error_unknown_code(payment_provider):
    """Test the response handler raises UnknownReturnCodeError as expected"""
    r = json.loads("""{
        "unknown_field": 1
    }""")
    with pytest.raises(UnknownReturnCodeError):
        payment_provider.handle_initiate_payment(r)


def test_payload_add_sap_organization_details(payment_provider, provider_base_config):
    """Test sap organization data is added correctly into payload"""
    payload = {}
    payment_provider.payload_add_sap_organization_details(payload)
    assert 'sapOrganizationDetails' in payload
    sapOrganizationDetails = payload['sapOrganizationDetails']
    assert (sapOrganizationDetails.get('sapSalesOrganization') ==
        provider_base_config['RESPA_PAYMENTS_TURKU_SAP_SALES_ORGANIZATION'])
    assert (sapOrganizationDetails.get('sapDistributionChannel') ==
        provider_base_config['RESPA_PAYMENTS_TURKU_SAP_DISTRIBUTION_CHANNEL'])
    assert (sapOrganizationDetails.get('sapSector') ==
        provider_base_config['RESPA_PAYMENTS_TURKU_SAP_SECTOR'])


def test_payload_add_customer(payment_provider, order_with_products):
    """Test the customer data from order is added correctly into payload"""
    payload = {}
    payment_provider.payload_add_customer(payload, order_with_products)

    assert 'customer' in payload
    customer = payload['customer']
    assert customer.get('email') == 'test@example.com'
    assert customer.get('firstName') == 'Seppo'
    assert customer.get('lastName') == 'Testi'
    assert customer.get('phone') == '555555555'


def test_payload_add_invoice_address(payment_provider, order_with_products):
    """Test invoice address data from order is added correctly into payload"""
    payload = {}
    payment_provider.payload_add_invoice_address(payload, order_with_products)

    assert 'invoicingAddress' in payload
    invoicingAddress = payload['invoicingAddress']
    assert invoicingAddress.get('streetAddress') == 'Test street 1'
    assert invoicingAddress.get('postalCode') == '12345'
    assert invoicingAddress.get('city') == 'Testcity'
    assert invoicingAddress.get('country') == 'FI'


def test_payload_add_products(payment_provider, order_with_products):
    """Test products are added correctly into payload"""
    payload = {}
    payment_provider.payload_add_products(payload, order_with_products)

    assert 'items' in payload
    products = payload['items']
    assert len(products) == 2
    for product in products:
        assert 'unitPrice' in product
        assert 'units' in product
        assert 'vatPercentage' in product
        assert 'productCode' in product
        assert 'description' in product


@pytest.mark.parametrize('sap_function_area, sap_unit', (
    ('', ''),
    ('0000000000000001', ''),
    ('', '0000000001'),
    ('0000000000000001', '0000000001'),
))
def test_product_add_sap_data(sap_function_area, sap_unit, payment_provider, order_with_product_customer_group):
    """Test sap codes are added correctly to product payload"""
    payload = {}
    product = OrderLine.objects.get(order=order_with_product_customer_group).product

    if sap_function_area:
        product.sap_function_area = sap_function_area
    if sap_unit:
        product.sap_unit = sap_unit

    payment_provider.product_add_sap_data(payload, product, order_with_product_customer_group)
    assert 'sapProduct' in payload
    sap_data = payload['sapProduct']
    assert 'sapCode' in sap_data
    assert 'sapOfficeCode' in sap_data
    if sap_function_area:
        assert 'sapFunctionArea' in sap_data
    else:
        assert 'sapFunctionArea' not in sap_data

    if sap_unit:
        assert 'sapProfitCenter' in sap_data
    else:
        assert 'sapProfitCenter' not in sap_data


def test_handle_success_request_order_not_found(provider_base_config, order_with_products):
    """Test request helper returns a failure url when order can't be found"""
    params = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': '1234567', # test incorrect val
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
        'X-TURKU-SP': 'respa-turku',
        'X-TURKU-TS': '2022-01-25T14:25:00Z',
        'Authorization': '3d94ba71e0f6e486f6efe0d7c1d4832e7d1d118df21ddc526f7cbe4e8982f36f',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    rf = RequestFactory()
    request = rf.get('/payments/success/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)

    returned = payment_provider.handle_success_request()
    assert isinstance(returned, HttpResponse)
    assert 'payment_status=failure' in returned.url


def test_handle_success_request_success(provider_base_config, order_with_products):
    """
    Test request helper changes the order status to confirmed
    and check it returns a success url with reservation id.
    """
    params = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': 'abc123',
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
        'X-TURKU-SP': 'respa-turku',
        'X-TURKU-TS': '2022-01-25T14:25:00Z',
        'Authorization': '8fddc5b7a4f5e610327150ab7fa3bd3d65ac4a024aec8e668d83c7c8d0550be9',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    rf = RequestFactory()
    request = rf.get('/payments/success/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    returned = payment_provider.handle_success_request()
    order_after = Order.objects.get(order_number=params.get('checkout-reference'))
    assert order_after.state == Order.CONFIRMED
    assert isinstance(returned, HttpResponse)
    assert 'payment_status=success' in returned.url
    assert 'reservation_id={}'.format(order_after.reservation.id) in returned.url


def test_handle_failure_request_order_not_found(provider_base_config, order_with_products):
    """Test request helper returns a failure url when order can't be found"""
    params = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': '1234567', # test incorrect val
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
        'X-TURKU-SP': 'respa-turku',
        'X-TURKU-TS': '2022-01-25T14:25:00Z',
        'Authorization': '3d94ba71e0f6e486f6efe0d7c1d4832e7d1d118df21ddc526f7cbe4e8982f36f',
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
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': 'abc123',
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
        'X-TURKU-SP': 'respa-turku',
        'X-TURKU-TS': '2022-01-25T14:25:00Z',
        'Authorization': '8fddc5b7a4f5e610327150ab7fa3bd3d65ac4a024aec8e668d83c7c8d0550be9',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    rf = RequestFactory()
    request = rf.get('/payments/failure/', params)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    returned = payment_provider.handle_failure_request()
    order_after = Order.objects.get(order_number=params.get('checkout-reference'))
    assert order_after.state == Order.REJECTED
    assert isinstance(returned, HttpResponse)
    assert 'payment_status=failure' in returned.url


def test_handle_notify_request_order_not_found(provider_base_config, order_with_products):
    """Test request notify helper returns http 200 when order can't be found"""
    headers = {
        'HTTP_X-TURKU-SP': 'respa-turku',
        'HTTP_X-TURKU-TS': '2022-01-25T14:25:00Z',
        'HTTP_Authorization': '1d718c97feca15fcfd0bc405013b58dac16d4e4b3e62d3c33c02472ae237e379',
    }
    json_data = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': '1234567', # test incorrect val
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
    }
    rf = RequestFactory()
    request = rf.post('/payments/notify/', data=json_data, content_type='application/json', **headers)
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
    headers = {
        'HTTP_X-TURKU-SP': 'respa-turku',
        'HTTP_X-TURKU-TS': '2022-01-25T14:25:00Z',
        'HTTP_Authorization': 'b29feb5113c18ef13d5edde8da0c1b6ee0f65f46fc85230c207521dfb8e0691f',
    }
    json_data = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': 'abc123',
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
    }
    order_with_products.set_state(order_state)

    rf = RequestFactory()
    request = rf.post('/payments/notify/', data=json_data, content_type='application/json', **headers)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    returned = payment_provider.handle_notify_request()
    order_after = Order.objects.get(order_number=json_data.get('checkout-reference'))
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
    headers = {
        'HTTP_X-TURKU-SP': 'respa-turku',
        'HTTP_X-TURKU-TS': '2022-01-25T14:25:00Z',
        'HTTP_AUTHORIZATION': '2461ae1df96eae975f62f906bf6d1144d5792f1b4dcb701921c6c1baf644ee49',
    }
    json_data = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': 'abc123',
        'checkout-status': 'fail',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
    }
    order_with_products.set_state(order_state)

    rf = RequestFactory()
    request = rf.post('/payments/notify/', data=json_data, content_type='application/json', **headers)
    payment_provider = create_turku_payment_provider(provider_base_config, request, UI_RETURN_URL)
    returned = payment_provider.handle_notify_request()
    order_after = Order.objects.get(order_number=json_data.get('checkout-reference'))
    assert order_after.state == expected_order_state
    assert isinstance(returned, HttpResponse)
    assert returned.status_code == 200


def test_check_new_payment_authcode_success_redirect(payment_provider):
    """
    Test the helper is able to extract necessary values from a request and compare authcodes
    with redirect calls
    """
    params = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': 'abc123',
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
        'X-TURKU-SP': 'respa-turku',
        'X-TURKU-TS': '2022-01-25T14:25:00Z',
        'Authorization': '8fddc5b7a4f5e610327150ab7fa3bd3d65ac4a024aec8e668d83c7c8d0550be9',
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }
    rf = RequestFactory()
    request = rf.get('/payments/success/', params)
    assert payment_provider.check_new_payment_authcode(request, RequestTypes.REDIRECT)


def test_check_new_payment_authcode_invalid_redirect(payment_provider):
    """Test the helper fails when params do not match the auth code with redirect calls"""
    auth_values = '2022-01-25T14:25:00Z'
    auth_values += 'checkout-amount:24.80\n'
    auth_values += 'checkout-provider:test-provider\n'
    auth_values += 'checkout-reference:abc123\n'
    auth_values += 'checkout-stamp:321\n' # test incorrect val
    auth_values += 'checkout-status:ok\n'
    auth_values += 'checkout-transaction-id:123-abc\n'
    auth_code = payment_provider.calculate_auth_code(auth_values)
    params = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': 'abc123',
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
        'X-TURKU-SP': 'respa-turku',
        'X-TURKU-TS': '2022-01-25T14:25:00Z',
        'Authorization': auth_code,
        'RESPA_UI_RETURN_URL': 'http%3A%2F%2F127.0.0.1%3A8000%2Fv1',
    }

    rf = RequestFactory()
    request = rf.get('/payments/success/', params)
    assert not payment_provider.check_new_payment_authcode(request, RequestTypes.REDIRECT)


def test_check_new_payment_authcode_success_callback(payment_provider):
    """
    Test the helper is able to extract necessary values from a request and compare authcodes
    with callback calls
    """
    headers = {
        'HTTP_X-TURKU-SP': 'respa-turku',
        'HTTP_X-TURKU-TS': '2022-01-25T14:25:00Z',
        'HTTP_Authorization': 'b29feb5113c18ef13d5edde8da0c1b6ee0f65f46fc85230c207521dfb8e0691f',
    }
    json_data = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': 'abc123',
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
    }
    rf = RequestFactory()
    request = rf.post('/payments/notify/', data=json_data, content_type='application/json', **headers)
    assert payment_provider.check_new_payment_authcode(request, RequestTypes.CALLBACK)


def test_check_new_payment_authcode_invalid_callback(payment_provider):
    """Test the helper fails when params do not match the auth code with callback calls"""
    headers = {
        'HTTP_X-TURKU-SP': 'respa-turku',
        'HTTP_X-TURKU-TS': '2022-01-25T14:25:00Z',
        'HTTP_Authorization': 'test-wrong-auth',
    }
    json_data = {
        'checkout-amount': '24.80',
        'checkout-stamp': '123123123123',
        'checkout-reference': 'abc123',
        'checkout-status': 'ok',
        'checkout-provider': 'test-provider',
        'checkout-transaction-id': '123-abc',
    }
    rf = RequestFactory()
    request = rf.post('/payments/notify/', data=json_data, content_type='application/json', **headers)
    assert not payment_provider.check_new_payment_authcode(request, RequestTypes.CALLBACK)


def test_calculate_auth_code_success(payment_provider):
    """Test the auth code calculation returns the correct string"""
    data = 'some-data'
    calculated_code = payment_provider.calculate_auth_code(data)
    assert calculated_code == '225e7b77a83054ccc1b9413ae986055b02fce613adcbc2e8aa9f05d2c8e1584b'


@pytest.mark.parametrize('price, expected_result', (
    ('10', 1000),
    ('1', 100),
    ('3.50', 350),
    ('120.59', 12059),
    ('3.33', 333)
))
def test_convert_price_to_cents(payment_provider, price, expected_result):
    """Test given euros are converted correctly to cents"""
    assert payment_provider.convert_price_to_cents(Decimal(price)) == expected_result
