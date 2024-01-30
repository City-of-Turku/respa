from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, create_autospec, patch
from urllib.parse import urlencode
from django.core import mail
from django.utils import translation
from django.test import override_settings
import pytest
from guardian.shortcuts import assign_perm
from rest_framework.reverse import reverse

from notifications.tests.utils import check_received_mail_exists, get_expected_strings, get_body_with_all_template_vars, check_mail_was_not_sent
from notifications.models import NotificationTemplate, NotificationType
from resources.enums import UnitAuthorizationLevel
from resources.models import Reservation
from resources.models.reservation import ReservationMetadataField, ReservationMetadataSet
from resources.models.unit import UnitAuthorization
from resources.models.utils import generate_id, get_translated_fields
from resources.tests.conftest import resource_in_unit, user_api_client  # noqa
from resources.tests.test_reservation_api import day_and_period  # noqa

from ..factories import ProductFactory
from ..models import CustomerGroup, Order, OrderCustomerGroupData, OrderLine, Product, ProductCustomerGroup
from ..providers.base import PaymentProvider
from .test_order_api import ORDER_LINE_FIELDS, PRODUCT_FIELDS

LIST_URL = reverse('reservation-list')

ORDER_FIELDS = {'id', 'state', 'price', 'order_lines', 'is_requested_order', 'payment_method'}


@pytest.fixture(autouse=True)
def reservation_requested_notification():
    NotificationTemplate.objects.filter(type=NotificationType.RESERVATION_REQUESTED).delete()
    with translation.override('fi'):
        return NotificationTemplate.objects.create(
            type=NotificationType.RESERVATION_REQUESTED,
            is_default_template=True,
            short_message='Reservation requested short message.',
            subject='Reservation requested subject.',
            body='Reservation requested body. \n' + get_body_with_all_template_vars()
        )

@pytest.fixture(autouse=True)
def reservation_modified_notification():
    NotificationTemplate.objects.filter(type=NotificationType.RESERVATION_MODIFIED).delete()
    with translation.override('fi'):
        return NotificationTemplate.objects.create(
            type=NotificationType.RESERVATION_MODIFIED,
            is_default_template=True,
            short_message='Reservation modified short message.',
            subject='Reservation modified subject.',
            body='Reservation modified body. \n' + get_body_with_all_template_vars()
        )

@pytest.fixture(autouse=True)
def reservation_confirmed_notification():
    NotificationTemplate.objects.filter(type=NotificationType.RESERVATION_CONFIRMED).delete()
    with translation.override('fi'):
        return NotificationTemplate.objects.create(
            type=NotificationType.RESERVATION_CONFIRMED,
            is_default_template=True,
            short_message='Reservation confirmed short message.',
            subject='Reservation confirmed subject.',
            body='Reservation confirmed body. \n' + get_body_with_all_template_vars()
        )


@pytest.fixture(autouse=True)
def reservation_waiting_for_payment_notification():
    NotificationTemplate.objects.filter(type=NotificationType.RESERVATION_WAITING_FOR_PAYMENT).delete()
    with translation.override('fi'):
        return NotificationTemplate.objects.create(
            type=NotificationType.RESERVATION_WAITING_FOR_PAYMENT,
            is_default_template=True,
            short_message='Reservation waiting for payment short message.',
            subject='Reservation waiting for payment subject.',
            body='Reservation waiting for payment body.',
        )


def get_detail_url(reservation):
    return reverse('reservation-detail', kwargs={'pk': reservation.pk})


def build_reservation_data(resource):
    return {
        'resource': resource.pk,
        'begin': '2115-04-04T11:00:00+02:00',
        'end': '2115-04-04T12:00:00+02:00'
    }


def build_order_data(product, quantity=None, product_2=None, quantity_2=None, customer_group=None):
    data = {
        "order_lines": [
            {
                "product": product.product_id,
            }
        ],
        "return_url": "https://varauspalvelu.com/payment_return_url/",
    }

    if quantity:
        data['order_lines'][0]['quantity'] = quantity

    if product_2:
        order_line_data = {'product': product_2.product_id}
        if quantity_2:
            order_line_data['quantity'] = quantity_2
        data['order_lines'].append(order_line_data)

    if customer_group:
        data['customer_group'] = customer_group

    return data


@pytest.fixture(autouse=True)
def auto_use_django_db(db):
    pass


@pytest.fixture
def product(resource_in_unit):
    return ProductFactory(resources=[resource_in_unit])


@pytest.fixture
def product_2(resource_in_unit):
    return ProductFactory(resources=[resource_in_unit])


@pytest.fixture(autouse=True)
def mock_provider():
    mocked_provider = create_autospec(PaymentProvider)
    mocked_provider.initiate_payment = MagicMock(return_value='https://mocked-payment-url.com')
    with patch('payments.api.reservation.get_payment_provider', return_value=mocked_provider):
        yield mocked_provider


@pytest.mark.parametrize('has_order, expected_state', (
    (False, Reservation.CONFIRMED),
    (True, Reservation.WAITING_FOR_PAYMENT),
))
def test_reservation_creation_state(user_api_client, resource_in_unit, has_order, expected_state):
    reservation_data = build_reservation_data(resource_in_unit)
    if has_order:
        product = ProductFactory(type=Product.RENT, resources=[resource_in_unit])
        reservation_data['order'] = build_order_data(product)

    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 201
    new_reservation = Reservation.objects.last()
    assert new_reservation.state == expected_state


@pytest.mark.parametrize('endpoint', ('list', 'detail'))
@pytest.mark.parametrize('include', (None, '', 'foo', ['foo', 'bar'], 'order_detail', ['foo', 'order_detail']))
def test_reservation_orders_field(user_api_client, order_with_products, endpoint, include):
    url = LIST_URL if endpoint == 'list' else get_detail_url(order_with_products.reservation)
    if include is not None:
        if not isinstance(include, list):
            include = list(include)
        query_string = urlencode([('include', i) for i in include])
        url += '?' + query_string

    response = user_api_client.get(url)
    assert response.status_code == 200

    reservation_data = response.data['results'][0] if endpoint == 'list' else response.data

    order_data = reservation_data['order']
    if include is not None and 'order_detail' in include:
        # order should be nested data
        assert set(order_data.keys()) == ORDER_FIELDS | {'customer_group_name'}
        assert order_data['id'] == order_with_products.order_number
        for ol in order_data['order_lines']:
            assert set(ol.keys()) == ORDER_LINE_FIELDS
            assert set(ol['product']) == PRODUCT_FIELDS
    else:
        # order should be just ID
        assert order_data == order_with_products.order_number


@pytest.mark.parametrize('begin, end, customer_group_id, price_result', (
    (datetime(2022, 3, 1, 10, 0), datetime(2022, 3, 1, 12, 0), None, '20.00'),
    (datetime(2022, 3, 1, 10, 0), datetime(2022, 3, 1, 12, 0), 'cg-adults-1', '16.00'),
    (datetime(2022, 3, 1, 10, 0), datetime(2022, 3, 1, 12, 0), 'cg-children-1', '22.00'),
    (datetime(2022, 3, 1, 10, 0), datetime(2022, 3, 1, 12, 0), 'cg-elders-1', '12.00'),
    (datetime(2022, 3, 1, 10, 0), datetime(2022, 3, 1, 12, 0), 'cg-companies-1', '20.00'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 16, 0), None, '30.00'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 16, 0), 'cg-adults-1', '24.00'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 16, 0), 'cg-children-1', '22.00'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 16, 0), 'cg-elders-1', '30.00'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 16, 0), 'cg-companies-1', '30.00'),
    (datetime(2022, 3, 1, 11, 30), datetime(2022, 3, 1, 12, 30), None, '12.50'),
    (datetime(2022, 3, 1, 11, 30), datetime(2022, 3, 1, 12, 30), 'cg-adults-1', '10.00'),
    (datetime(2022, 3, 1, 11, 30), datetime(2022, 3, 1, 12, 30), 'cg-children-1', '11.00'),
    (datetime(2022, 3, 1, 11, 30), datetime(2022, 3, 1, 12, 30), 'cg-elders-1', '10.50'),
    (datetime(2022, 3, 1, 11, 30), datetime(2022, 3, 1, 12, 30), 'cg-companies-1', '12.50'),
))
def test_reservation_order_with_time_slot_product_has_correct_price(begin, end, customer_group_id,
    price_result, user_api_client, order_with_selected_cg_and_product_with_pcgs_and_time_slots,
    customer_group_companies):
    '''
    Test that price is calculated correctly for created orders containing a product with
    time slots and customer groups
    '''
    reservation = Reservation.objects.get(id=order_with_selected_cg_and_product_with_pcgs_and_time_slots.reservation.id)
    reservation.state = Reservation.WAITING_FOR_PAYMENT
    reservation.begin = begin.astimezone()
    reservation.end = end.astimezone()
    reservation.save()

    customer_group = None
    if customer_group_id:
        customer_group = CustomerGroup.objects.get(id=customer_group_id)
    order = Order.objects.get(id=order_with_selected_cg_and_product_with_pcgs_and_time_slots.id)
    order.reservation = reservation
    order.customer_group = customer_group
    order.save()

    order_line = OrderLine.objects.get(order=order)
    prod_cg = ProductCustomerGroup.objects.filter(customer_group=customer_group)
    ocgd = OrderCustomerGroupData.objects.get(order_line=order_line)
    ocgd.product_cg_price=prod_cg.get_price_for(order_line.product)
    if prod_cg:
        ocgd.copy_translated_fields(prod_cg.first().customer_group)
        ocgd.price_is_based_on_product_cg = True
    else:
        ocgd.price_is_based_on_product_cg = False
    ocgd.save()

    url = get_detail_url(order.reservation)
    url += '?include=order_detail'

    response = user_api_client.get(url)
    assert response.status_code == 200

    reservation_data = response.data
    order_data = reservation_data['order']
    assert order_data['price'] == price_result


@pytest.mark.parametrize('endpoint', ('list', 'detail'))
@pytest.mark.parametrize('request_user, expected', (
    (None, False),
    ('owner', True),
    ('other', False),
    ('other_with_perm', True),
))
def test_reservation_order_field_visibility(api_client, order_with_products, user2, request_user, endpoint, expected):
    url = LIST_URL if endpoint == 'list' else get_detail_url(order_with_products.reservation)

    if request_user == 'owner':
        api_client.force_authenticate(user=order_with_products.reservation.user)
    elif request_user == 'other':
        api_client.force_authenticate(user=user2)
    elif request_user == 'other_with_perm':
        assign_perm('unit:can_view_reservation_product_orders', user2, order_with_products.reservation.resource.unit)
        api_client.force_authenticate(user=user2)

    response = api_client.get(url)
    assert response.status_code == 200

    reservation_data = response.data['results'][0] if endpoint == 'list' else response.data
    assert ('order' in reservation_data) is expected


def test_reservation_in_state_waiting_for_payment_cannot_be_modified_or_deleted(user_api_client, order_with_products):
    reservation = order_with_products.reservation
    response = user_api_client.put(get_detail_url(reservation), data=build_reservation_data(reservation.resource))
    assert response.status_code == 403

    response = user_api_client.delete(get_detail_url(reservation))
    assert response.status_code == 403


@pytest.mark.parametrize('has_perm', (False, True))
def test_reservation_that_has_order_cannot_be_modified_without_permission(user_api_client, order_with_products, user,
                                                                          has_perm):
    order_with_products.set_state(Order.CONFIRMED)
    if has_perm:
        assign_perm('unit:can_modify_paid_reservations', user, order_with_products.reservation.resource.unit)

    data = build_reservation_data(order_with_products.reservation.resource)
    response = user_api_client.put(get_detail_url(order_with_products.reservation), data=data)
    assert response.status_code == 200 if has_perm else 403

    response = user_api_client.delete(get_detail_url(order_with_products.reservation))
    assert response.status_code == 204 if has_perm else 403


def test_order_post(user_api_client, resource_in_unit, product, product_2, mock_provider):
    reservation_data = build_reservation_data(resource_in_unit)
    reservation_data['order'] = build_order_data(product=product, product_2=product_2, quantity_2=5)

    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 201, response.data
    mock_provider.initiate_payment.assert_called()

    # check response fields
    order_create_response_fields = ORDER_FIELDS.copy() | {'payment_url', 'customer_group_name'}
    order_data = response.data['order']
    assert set(order_data.keys()) == order_create_response_fields
    assert order_data['payment_url'].startswith('https://mocked-payment-url.com')

    # check created object
    new_order = Order.objects.last()
    assert new_order.reservation == Reservation.objects.last()

    # check order lines
    order_lines = new_order.order_lines.all()
    assert order_lines.count() == 2
    assert order_lines[0].product == product
    assert order_lines[0].quantity == 1
    assert order_lines[1].product == product_2
    assert order_lines[1].quantity == 5


@pytest.mark.parametrize('payment_method, expected_status', (
    (None, 201),
    (Order.CASH, 201),
    (Order.ONLINE, 201),
))
def test_order_payment_methods_for_resources_allowing_cash_post(payment_method, expected_status,
    user_api_client, resource_in_unit, product):
    '''
    Tests that adding different payment methods to order work correctly with
    a resource allowing cash payments
    '''
    resource_in_unit.need_manual_confirmation = True
    resource_in_unit.cash_payments_allowed = True
    resource_in_unit.save()

    reservation_data = build_reservation_data(resource_in_unit)
    order = build_order_data(product=product)
    if payment_method:
        order['payment_method'] = payment_method
    reservation_data['order'] = order

    response = user_api_client.post(LIST_URL, reservation_data)
    order_data = response.data['order']

    assert response.status_code == expected_status, response.data
    if payment_method:
        assert order_data['payment_method'] == payment_method
    else:
        assert order_data['payment_method'] == Order.ONLINE


@pytest.mark.parametrize('payment_method, expected_status', (
    (None, 201),
    (Order.CASH, 400),
    (Order.ONLINE, 201),
))
def test_order_payment_methods_for_resources_not_allowing_cash_post(payment_method, expected_status,
    user_api_client, resource_in_unit, product):
    '''
    Tests that adding different payment methods to order work correctly with
    a resource not allowing cash payments
    '''
    resource_in_unit.cash_payments_allowed = False
    resource_in_unit.save()

    reservation_data = build_reservation_data(resource_in_unit)
    order = build_order_data(product=product)
    if payment_method:
        order['payment_method'] = payment_method
    reservation_data['order'] = order

    response = user_api_client.post(LIST_URL, reservation_data)
    assert response.status_code == expected_status, response.data

@override_settings(RESPA_MAILS_ENABLED=True)
def test_cash_paid_reservation_process_flow_works_correctly(
    user_api_client, resource_in_unit, product, api_client, unit_manager_user):
    '''
    Tests that cash paid reservation process flow gets correct state changes,
    allows intended operations and sends the correct email notifications when the state changes.
    '''
    field_billing_email = ReservationMetadataField.objects.create(field_name='billing_email_address')
    metadata_set = ReservationMetadataSet.objects.create(name='test_set',)
    metadata_set.supported_fields.set([field_billing_email])
    metadata_set.required_fields.set([field_billing_email])
    resource_in_unit.reservation_metadata_set = metadata_set
    resource_in_unit.need_manual_confirmation = True
    resource_in_unit.cash_payments_allowed = True
    resource_in_unit.save()

    reservation_data = build_reservation_data(resource_in_unit)
    reservation_data.update({'billing_email_address': 'billing@something.here'})
    order = build_order_data(product=product)
    order['payment_method'] = Order.CASH
    reservation_data['order'] = order

    # user creates their reservation
    response = user_api_client.post(LIST_URL, reservation_data)
    assert response.status_code == 201, response.data
    new_order = Order.objects.last()
    new_reservation = Reservation.objects.last()
    assert new_order.reservation == new_reservation
    assert response.data['state'] == Reservation.REQUESTED
    assert response.data['order']['state'] == Order.WAITING

    # reservation requested email was sent to billing_email_address.
    check_received_mail_exists(
        'Reservation requested subject.',
        response.data['billing_email_address'],
        get_expected_strings(new_order),
    )

    # user updates their reservation
    reservation_data.update({'end': '2115-04-04T12:30:00+02:00'})
    response = user_api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 200
    assert response.data['state'] == Reservation.REQUESTED
    assert response.data['order']['state'] == Order.WAITING
    # reservation modified email was sent to billing_email_address.
    check_received_mail_exists(
        'Reservation modified subject.',
        response.data['billing_email_address'],
        get_expected_strings(new_order),
    )

    # staff confirms reservation to set its state to be waiting for cash payment
    api_client.force_authenticate(user=unit_manager_user)
    previous_reservation_state = response.data['state'] # reservation state as it was after the reservation was updated.
    reservation_data.update({'state': Reservation.CONFIRMED})
    response = api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 200
    assert previous_reservation_state == Reservation.REQUESTED
    assert response.data['state'] == Reservation.WAITING_FOR_CASH_PAYMENT # current reservation state.
    assert response.data['order']['state'] == Order.WAITING
    previous_reservation_state = response.data['state'] # update previous reservation state to current.
    # reservation confirmed email was sent to users billing_email_address.
    check_received_mail_exists(
        'Reservation confirmed subject.',
        response.data['billing_email_address'],
        get_expected_strings(new_order),
    )

    # user tries to update after confirmation
    reservation_data.update({'reserver_name': 'Test Tester 2'})
    response = user_api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 403

    # staff confirms reservation and its cash payment
    reservation_data.update({'state': Reservation.CONFIRMED})
    response = api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 200
    assert previous_reservation_state == Reservation.WAITING_FOR_CASH_PAYMENT # previous reservation state.
    assert response.data['state'] == Reservation.CONFIRMED # current reservation state.
    assert response.data['order']['state'] == Order.CONFIRMED
    # no mail was sent when reservation state changed from WAITING_FOR_CASH_PAYMENT to CONFIRMED.
    check_mail_was_not_sent()

    # user tries to update after confirmation
    reservation_data.update({'reserver_name': 'Test Tester 3'})
    response = user_api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 403


def test_existing_cash_paid_reservations_work_after_resource_disallows_cash(
    user_api_client, resource_in_unit, product, api_client, unit_manager_user):
    '''
    Tests that reservations already created with cash payment work after resource
    disallows cash payment option
    '''
    resource_in_unit.need_manual_confirmation = True
    resource_in_unit.cash_payments_allowed = True
    resource_in_unit.save()

    reservation_data = build_reservation_data(resource_in_unit)
    order = build_order_data(product=product)
    order['payment_method'] = Order.CASH
    reservation_data['order'] = order

    response = user_api_client.post(LIST_URL, reservation_data)
    assert response.status_code == 201, response.data
    new_order = Order.objects.last()
    new_reservation = Reservation.objects.last()
    assert new_order.reservation == new_reservation

    # resource disallows cash payments
    resource_in_unit.cash_payments_allowed = False
    resource_in_unit.save()

    # user updates their reservation
    reservation_data.update({'reserver_name': 'Test Tester'})
    response = user_api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 200

    # staff confirms reservation to set its state to be waiting for cash payment
    api_client.force_authenticate(user=unit_manager_user)
    reservation_data.update({'state': Reservation.CONFIRMED})
    response = api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 200
    assert response.data['state'] == Reservation.WAITING_FOR_CASH_PAYMENT
    assert response.data['order']['state'] == Order.WAITING

    # user tries to update after confirmation
    reservation_data.update({'reserver_name': 'Test Tester 2'})
    response = user_api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 403

    # staff confirms reservation and its cash payment
    reservation_data.update({'state': Reservation.CONFIRMED})
    response = api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 200
    assert response.data['state'] == Reservation.CONFIRMED
    assert response.data['order']['state'] == Order.CONFIRMED

    # user tries to update after confirmation
    reservation_data.update({'reserver_name': 'Test Tester 3'})
    response = user_api_client.put(get_detail_url(new_reservation), reservation_data)
    assert response.status_code == 403


def test_order_with_product_cg_post(user_api_client, resource_in_unit, product_with_product_cg, mock_provider):
    product_cg = ProductCustomerGroup.objects.get(product=product_with_product_cg)

    reservation_data = build_reservation_data(resource_in_unit)
    reservation_data['order'] = build_order_data(product=product_with_product_cg, quantity=2, customer_group=product_cg.customer_group.id)
    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 201, response.data
    mock_provider.initiate_payment.assert_called()

    order_create_response_fields = ORDER_FIELDS.copy() | {'payment_url', 'customer_group_name'}
    order_data = response.data['order']
    assert set(order_data.keys()) == order_create_response_fields
    assert order_data['payment_url'].startswith('https://mocked-payment-url.com')
    assert order_data['customer_group_name'] == get_translated_fields(product_cg.customer_group)
    new_order = Order.objects.last()
    assert new_order.reservation == Reservation.objects.last()

    order_lines = new_order.order_lines.all()
    assert order_lines.count() == 1
    assert order_lines[0].product == product_with_product_cg
    assert order_lines[0].quantity == 2

    ocgd = OrderCustomerGroupData.objects.filter(order_line__in=new_order.get_order_lines(), order_line__product=product_with_product_cg)
    assert ocgd.exists()


@pytest.mark.parametrize('with_customer_group_id', (True, False))
def test_order_with_invalid_product_cg_post(user_api_client, resource_in_unit, product_with_product_cg, with_customer_group_id):
    reservation_data = build_reservation_data(resource_in_unit)
    if with_customer_group_id:
        reservation_data['order'] = build_order_data(product=product_with_product_cg, quantity=2, customer_group=generate_id())
    else:
        reservation_data['order'] = build_order_data(product=product_with_product_cg, quantity=2)
    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 400, response.data


def test_order_product_must_match_resource(user_api_client, product, resource_in_unit, resource_in_unit2):
    product_with_another_resource = ProductFactory(resources=[resource_in_unit2])
    data = build_reservation_data(resource_in_unit)
    data['order'] = build_order_data(product=product, product_2=product_with_another_resource)

    response = user_api_client.post(LIST_URL, data)

    assert response.status_code == 400
    assert 'product' in response.data['order']['order_lines'][1]


def test_order_line_products_are_unique(user_api_client, resource_in_unit, product):
    """Test order validator enforces that order lines cannot contain duplicates of the same product"""
    reservation_data = build_reservation_data(resource_in_unit)
    reservation_data['order'] = build_order_data(product, quantity=2, product_2=product, quantity_2=2)
    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 400


@pytest.mark.parametrize('quantity, expected_status', (
    (1, 201),
    (2, 201),
    (3, 400),
))
def test_order_line_product_quantity_limitation(user_api_client, resource_in_unit, quantity, expected_status):
    """Test order validator order line quantity is within product max quantity limitation"""
    reservation_data = build_reservation_data(resource_in_unit)
    product_with_quantity = ProductFactory(resources=[resource_in_unit], max_quantity=2)
    order_data = build_order_data(product=product_with_quantity, quantity=quantity)
    reservation_data['order'] = order_data

    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == expected_status, response.data


@pytest.mark.parametrize('has_rent', (True, False))
def test_rent_product_makes_order_required_(user_api_client, resource_in_unit, has_rent):
    reservation_data = build_reservation_data(resource_in_unit)
    if has_rent:
        ProductFactory(type=Product.RENT, resources=[resource_in_unit])

    response = user_api_client.post(LIST_URL, reservation_data)

    if has_rent:
        assert response.status_code == 400
        assert 'order' in response.data
    else:
        assert response.status_code == 201


def test_order_cannot_be_modified(user_api_client, order_with_products, user):
    order_with_products.set_state(Order.CONFIRMED)
    assert order_with_products.reservation.state == Reservation.CONFIRMED
    new_product = ProductFactory(resources=[order_with_products.reservation.resource])
    reservation_data = build_reservation_data(order_with_products.reservation.resource)
    reservation_data['order'] = {
        'order_lines': [{
            'product': new_product.product_id,
            'quantity': 777
        }],
        'return_url': 'https://foo'
    }
    assign_perm('unit:can_modify_paid_reservations', user, order_with_products.reservation.resource.unit)

    response = user_api_client.put(get_detail_url(order_with_products.reservation), reservation_data)

    assert response.status_code == 400, response.data
    order_with_products.refresh_from_db()
    assert order_with_products.order_lines.first().product != new_product
    assert order_with_products.order_lines.first().quantity != 777
    assert order_with_products.order_lines.count() > 1


def test_extra_product_doesnt_make_order_required(user_api_client, resource_in_unit):
    reservation_data = build_reservation_data(resource_in_unit)
    ProductFactory(type=Product.EXTRA, resources=[resource_in_unit])

    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 201


def test_order_must_include_rent_if_one_exists(user_api_client, resource_in_unit):
    reservation_data = build_reservation_data(resource_in_unit)
    ProductFactory(type=Product.RENT, resources=[resource_in_unit])
    extra = ProductFactory(type=Product.EXTRA, resources=[resource_in_unit])
    reservation_data['order'] = build_order_data(product=extra)

    response = user_api_client.post(LIST_URL, reservation_data)
    assert response.status_code == 400


def test_unit_admin_can_bypass_include_rent_requirement(user_api_client, resource_in_unit, user):
    reservation_data = build_reservation_data(resource_in_unit)
    ProductFactory(type=Product.RENT, resources=[resource_in_unit])
    extra = ProductFactory(type=Product.EXTRA, resources=[resource_in_unit])
    reservation_data['order'] = build_order_data(product=extra)
    UnitAuthorization.objects.create(subject=resource_in_unit.unit, level=UnitAuthorizationLevel.manager, authorized=user)

    response = user_api_client.post(LIST_URL, reservation_data)
    assert response.status_code == 201


def test_unit_admin_and_unit_manager_may_bypass_payment(user_api_client, resource_in_unit, user):
    reservation_data = build_reservation_data(resource_in_unit)
    ProductFactory(type=Product.RENT, resources=[resource_in_unit])

    # Order required for normal user
    response = user_api_client.post(LIST_URL, reservation_data)
    assert response.status_code == 400
    assert 'order' in response.data

    # Order not required for admin user
    UnitAuthorization.objects.create(subject=resource_in_unit.unit, level=UnitAuthorizationLevel.admin, authorized=user)
    response = user_api_client.post(LIST_URL, reservation_data)
    assert response.status_code == 201
    new_reservation = Reservation.objects.last()
    assert new_reservation.state == Reservation.CONFIRMED
    UnitAuthorization.objects.all().delete()
    Reservation.objects.all().delete()

    # Order not required for manager user
    UnitAuthorization.objects.create(subject=resource_in_unit.unit, level=UnitAuthorizationLevel.manager, authorized=user)
    response = user_api_client.post(LIST_URL, reservation_data)
    assert response.status_code == 201
    new_reservation = Reservation.objects.last()
    assert new_reservation.state == Reservation.CONFIRMED


@pytest.mark.django_db
def test_reservation_without_order_doesnt_require_billing_fields(user_api_client, resource_in_unit):
    '''
    Tests that a reservation without an order can be made without billing fields
    even if billing fields are set as required fields for the resource.
    '''
    field_1 = ReservationMetadataField.objects.get(field_name='reserver_name')
    field_2 = ReservationMetadataField.objects.get(field_name='reserver_phone_number')
    field_3 = ReservationMetadataField.objects.create(field_name='billing_first_name')
    metadata_set = ReservationMetadataSet.objects.create(name='test_set',)
    metadata_set.supported_fields.set([field_1, field_2, field_3])
    metadata_set.required_fields.set([field_1, field_3])
    resource_in_unit.reservation_metadata_set = metadata_set
    resource_in_unit.save()

    reservation_data = build_reservation_data(resource_in_unit)
    reservation_data.update({
        'reserver_name': 'Test Tester'
        })

    response = user_api_client.post(LIST_URL, data=reservation_data)
    assert response.status_code == 201


@pytest.mark.django_db
def test_reservation_with_order_requires_billing_fields_when_they_are_set_required(
    user_api_client, resource_in_unit, product):
    '''
    Tests that a reservation with an order and billing fields set as required for the resource
    cannot be made without the billing fields
    '''
    field_1 = ReservationMetadataField.objects.get(field_name='reserver_name')
    field_2 = ReservationMetadataField.objects.get(field_name='reserver_phone_number')
    field_3 = ReservationMetadataField.objects.create(field_name='billing_first_name')
    metadata_set = ReservationMetadataSet.objects.create(name='test_set',)
    metadata_set.supported_fields.set([field_1, field_2, field_3])
    metadata_set.required_fields.set([field_1, field_3])
    resource_in_unit.reservation_metadata_set = metadata_set
    resource_in_unit.save()

    reservation_data = build_reservation_data(resource_in_unit)
    order_data = build_order_data(product)
    reservation_data.update({
        'reserver_name': 'Test Tester',
        'order': order_data
    })

    response = user_api_client.post(LIST_URL, data=reservation_data)
    assert response.status_code == 400


@pytest.mark.parametrize('is_staff', (True, False))
def test_manual_confirmation_reservation_with_zero_price(
    resource_with_manual_confirmation, api_client,
    unit_manager_user, user, product_extra_manual_confirmation, is_staff,
    product_customer_group
):
    reservation_data = build_reservation_data(resource_with_manual_confirmation)
    reservation_data['reserver_name'] = 'Nordea Demo'

    product_customer_group.price = Decimal('0.00')
    product_customer_group.product = product_extra_manual_confirmation
    product_customer_group.save()

    reservation_data['order'] = build_order_data(product_extra_manual_confirmation, customer_group=product_customer_group.customer_group.id)

    if is_staff:
        api_client.force_authenticate(user=unit_manager_user)
    else:
        api_client.force_authenticate(user=user)

    response = api_client.post(LIST_URL, data=reservation_data)

    assert response.status_code == 201, response.data
    state = response.data['state']

    if is_staff:
        assert state == Reservation.CONFIRMED, state
    else:
        assert state == Reservation.REQUESTED, state



@pytest.mark.parametrize('with_product', (True, False))
@pytest.mark.parametrize('customer_group_selected', (True, False))
def test_staff_manual_confirmation_reservation_with_product(
    resource_with_manual_confirmation, unit_manager_api_client,
    customer_group, customer_group_selected, with_product, product_extra_manual_confirmation):

    reservation_data = build_reservation_data(resource_with_manual_confirmation)
    reservation_data['reserver_name'] = 'Nordea Demo'

    if with_product:
        order_data = build_order_data(product_extra_manual_confirmation, customer_group=customer_group.id)
        if not customer_group_selected:
            del order_data['customer_group']
        reservation_data['order'] = order_data

    response = unit_manager_api_client.post(LIST_URL, data=reservation_data)

    if with_product and not customer_group_selected:
        assert response.status_code == 400, response.data # POST shouldn't go through if data has no customer_group
        return

    assert response.status_code == 201, response.data
    state = response.data['state']

    reservation = Reservation.objects.get(pk=response.data['id'])
    if reservation.has_order():
        order = reservation.get_order()
        assert order.state == Order.WAITING, order.state

    assert state == Reservation.CONFIRMED, state

@pytest.mark.parametrize('with_product', (True, False))
@pytest.mark.parametrize('customer_group_selected', (True, False))
def test_regular_user_manual_confirmation_reservation_with_product(
    resource_with_manual_confirmation, user_api_client,
    customer_group, customer_group_selected, with_product,
    product_extra_manual_confirmation):

    reservation_data = build_reservation_data(resource_with_manual_confirmation)
    reservation_data['reserver_name'] = 'Nordea Demo'
    reservation_data['reserver_email_address'] = 'jey@example.com'
    reservation_data['reserver_phone_number'] = '0401234567'

    if with_product:
        order_data = build_order_data(product_extra_manual_confirmation, customer_group=customer_group.id)
        if not customer_group_selected:
            del order_data['customer_group']
        reservation_data['order'] = order_data

    response = user_api_client.post(LIST_URL, data=reservation_data)

    if with_product and not customer_group_selected:
        assert response.status_code == 400, response.data # POST shouldn't go through if data has no customer_group
        return

    assert response.status_code == 201, response.data
    reservation = Reservation.objects.get(pk=response.data['id'])
    state = response.data['state']

    if reservation.has_order():
        order = reservation.get_order()
        assert order.state == Order.WAITING, order.state
    assert state == Reservation.REQUESTED, state

    response = user_api_client.put(get_detail_url(reservation), data=reservation_data)
    # PUT / PATCH should be OK for regular user before reservation state is confirmed.
    assert response.status_code == 200, response.data

    for state in (
        Reservation.WAITING_FOR_PAYMENT,
        Reservation.CONFIRMED): # Modifying reservation after confirmation should not be allowed as user.
        reservation.set_state(state, None)
        response = user_api_client.put(get_detail_url(reservation), data=reservation_data)
        assert response.status_code == 403, state


def test_reservation_raises_validation_error_when_order_cg_is_not_allowed_for_a_product(
    api_client, user, resource_in_unit, product, product_with_cg_login_restrictions,
    customer_group_login_method_internals, customer_group_with_login_method_restrictions):
    """
    Tests that a validation error is raised when reservation order product has customer group
    with login method restriction not allowing reserversion user login method and chosen order cg
    is restricted
    """
    reservation_data = build_reservation_data(resource_in_unit)

    order_data = build_order_data(
        product, quantity=1, product_2=product_with_cg_login_restrictions, quantity_2=1,
        customer_group=customer_group_with_login_method_restrictions.id
    )
    reservation_data.update({
        'reserver_name': 'Test Tester',
        'order': order_data
    })
    user.amr = 'test-wont-work'
    user.save()
    api_client.force_authenticate(user=user)
    response = api_client.post(LIST_URL, data=reservation_data)
    assert response.status_code == 400
    assert response.data['order']['non_field_errors'][0].code == 'unallowed-login-method'


def test_reservation_does_not_raise_validation_error_when_order_products_do_not_contain_login_method_restrictions(
    api_client, user, resource_in_unit, product, product_with_cg_login_restrictions,
    customer_group_login_method_internals, customer_group_with_login_method_restrictions):
    """
    Tests that validation errors are not raised when reservation order does not contain products with
    login method restrictions
    """
    reservation_data = build_reservation_data(resource_in_unit)
    # resource has restricted product but it is not included in the order
    order_data = build_order_data(
        product, quantity=1,
        customer_group=customer_group_with_login_method_restrictions.id
    )
    reservation_data.update({
        'reserver_name': 'Test Tester',
        'order': order_data
    })
    user.amr = 'test-some-other-amr'
    user.save()
    api_client.force_authenticate(user=user)
    response = api_client.post(LIST_URL, data=reservation_data)
    assert response.status_code == 201


def test_reservation_does_not_raise_validation_error_when_order_has_restricted_cgs_but_chosen_cg_is_allowed(
    api_client, user, resource_in_unit, product, product_with_cg_login_restrictions,
    customer_group_login_method_internals, customer_group_with_login_method_restrictions):
    """
    Tests that validation errors are not raised when reservation order contains products with
    login method restrictions but reservation order cg is one of the allowed cgs
    """
    # add restricted prod to resource, but choose allowed cg
    reservation_data = build_reservation_data(resource_in_unit)
    order_data = build_order_data(
        product, quantity=1, product_2=product_with_cg_login_restrictions, quantity_2=1,
        customer_group=customer_group_with_login_method_restrictions.id
    )
    reservation_data.update({
        'reserver_name': 'Test Tester',
        'order': order_data
    })
    user.amr = customer_group_login_method_internals.login_method_id
    user.save()
    api_client.force_authenticate(user=user)
    response = api_client.post(LIST_URL, data=reservation_data)
    assert response.status_code == 201


def test_reservation_does_not_raise_validation_error_when_prods_have_only_restricted_cgs(
    api_client, user, resource_in_unit, product_with_cg_login_restrictions):
    """
    Tests that validation errors are not raised when reserved resource has only
    restricted products for the user
    """
    # add only restricted prods to resource and don't choose any cg
    reservation_data = build_reservation_data(resource_in_unit)
    order_data = build_order_data(
        product_with_cg_login_restrictions, quantity=1,
        customer_group=''
    )
    reservation_data.update({
        'reserver_name': 'Test Tester',
        'order': order_data
    })
    user.amr = 'test-amr-123'
    user.save()
    api_client.force_authenticate(user=user)
    response = api_client.post(LIST_URL, data=reservation_data)
    assert response.status_code == 201


@override_settings(RESPA_MAILS_ENABLED=True)
@pytest.mark.django_db
def test_reservation_waiting_for_payment_sent_only_once(resource_with_manual_confirmation, api_client, user, unit_manager_api_client,
                                                        product_extra_manual_confirmation, reservation_waiting_for_payment_notification,
                                                        reservation_requested_notification, reservation_confirmed_notification,
                                                        customer_group):
    """Tests that reserver receives waiting for payment notification only once even if staff modifies the reservation"""
    # client user makes a reservation with order which also requires manual confirmation
    reservation_data = build_reservation_data(resource_with_manual_confirmation)
    reservation_data['reserver_name'] = 'Nordea Demo'
    reservation_data['reserver_email_address'] = 'test@tester.com'
    reservation_data['billing_email_address'] = 'test@tester.com'
    reservation_data['preferred_language'] = 'fi'
    order_data = build_order_data(product_extra_manual_confirmation, customer_group=customer_group.id)
    reservation_data['order'] = order_data

    api_client.force_authenticate(user=user)
    response = api_client.post(LIST_URL, data=reservation_data)

    assert response.status_code == 201
    assert response.data['state'] == Reservation.REQUESTED
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == 'Reservation requested subject.'

    # staff approves reservation
    reservation_data['state'] = Reservation.CONFIRMED
    mail.outbox = []
    new_reservation = Reservation.objects.last()
    response = unit_manager_api_client.put(get_detail_url(new_reservation), data=reservation_data, format='json')
    assert response.status_code == 200
    assert response.data['state'] == Reservation.READY_FOR_PAYMENT
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == 'Reservation waiting for payment subject.'

    # staff writes comments
    reservation_data['comments'] = 'test comment'
    reservation_data['state'] = Reservation.READY_FOR_PAYMENT
    mail.outbox = []
    response = unit_manager_api_client.put(get_detail_url(new_reservation), data=reservation_data, format='json')
    assert response.status_code == 200
    assert response.data['state'] == Reservation.READY_FOR_PAYMENT
    assert len(mail.outbox) == 0

    reservation_data['comments'] = 'other test comment'
    response = unit_manager_api_client.put(get_detail_url(new_reservation), data=reservation_data, format='json')
    assert response.status_code == 200
    assert response.data['state'] == Reservation.READY_FOR_PAYMENT
    assert len(mail.outbox) == 0
