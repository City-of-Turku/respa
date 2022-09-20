from datetime import datetime
from decimal import Decimal
import pytest
from guardian.shortcuts import assign_perm
from rest_framework.reverse import reverse

from ..factories import ProductCustomerGroupFactory, ProductFactory
from ..models import Order, ProductCustomerGroup

from resources.models.utils import generate_id

CHECK_PRICE_URL = reverse('order-check-price')


PRICE_ENDPOINT_ORDER_FIELDS = {
    'order_lines', 'price', 'begin', 'end'
}

ORDER_LINE_FIELDS = {
    'product', 'quantity', 'price', 'unit_price'
}

PRODUCT_FIELDS = {
    'id', 'type', 'name', 'description', 'price', 'max_quantity',
    'product_customer_groups', 'time_slot_prices', 'price_tax_free'
}

PRICE_FIELDS = {'type'}


def get_detail_url(order):
    return reverse('order-detail', kwargs={'order_number': order.order_number})


@pytest.fixture(autouse=True)
def auto_use_django_db(db):
    pass


@pytest.fixture
def product(resource_in_unit):
    return ProductFactory(resources=[resource_in_unit])


@pytest.fixture
def product_2(resource_in_unit):
    return ProductFactory(resources=[resource_in_unit])


def test_order_price_check_success(user_api_client, product, two_hour_reservation):
    """Test the endpoint returns price calculations for given product without persisting anything"""

    order_count_before = Order.objects.count()

    price_check_data = {
        "order_lines": [
            {
                "product": product.product_id,
            }
        ],
        "begin": str(two_hour_reservation.begin),
        "end": str(two_hour_reservation.end)
    }

    response = user_api_client.post(CHECK_PRICE_URL, price_check_data)
    assert response.status_code == 200
    assert len(response.data['order_lines']) == 1
    assert set(response.data.keys()) == PRICE_ENDPOINT_ORDER_FIELDS
    for ol in response.data['order_lines']:
        assert set(ol.keys()) == ORDER_LINE_FIELDS
        assert set(ol['product']) == PRODUCT_FIELDS
        assert all(f in ol['product']['price'] for f in PRICE_FIELDS)

    # Check order count didn't change
    assert order_count_before == Order.objects.count()


def test_order_price_check_begin_time_after_end_time(user_api_client, product, two_hour_reservation):
    """Test the endpoint returns 400 for bad time input"""

    order_count_before = Order.objects.count()

    price_check_data = {
        "order_lines": [
            {
                "product": product.product_id,
            }
        ],
        # Begin and end input swapped to cause ValidationError
        "begin": str(two_hour_reservation.end),
        "end": str(two_hour_reservation.begin),
    }

    response = user_api_client.post(CHECK_PRICE_URL, price_check_data)
    assert response.status_code == 400

@pytest.mark.parametrize('no_cost', (True, False))
@pytest.mark.django_db
def test_order_price_check_success_customer_group(user_api_client, product_with_product_cg, two_hour_reservation, no_cost):
    if no_cost:
        prod_cg = ProductCustomerGroupFactory.create(product=product_with_product_cg, price=Decimal('0.00'))
    else:
        prod_cg = ProductCustomerGroup.objects.get(product=product_with_product_cg)
    order_count_before = Order.objects.count()
    price_check_data = {
        "order_lines": [
            {
                "product": product_with_product_cg.product_id,
            }
        ],
        "begin": str(two_hour_reservation.begin),
        "end": str(two_hour_reservation.end),
        "customer_group": prod_cg.customer_group.id
    }
    response = user_api_client.post(CHECK_PRICE_URL, price_check_data)

    assert response.status_code == 200
    assert len(response.data['order_lines']) == 1

    order_line = dict((key, val) for key, val in enumerate(response.data['order_lines'])).get(0, None)

    assert order_line is not None
    if no_cost:
        assert order_line['price'] == Decimal('0.00')
    else:
        assert order_line['price'] == prod_cg.price * 2, price_check_data # Two hour price
    assert order_count_before == Order.objects.count()

def test_order_price_check_invalid_customer_group(user_api_client, product, two_hour_reservation):
    """Test the endpoint returns 400 for non-existant customer_group"""

    order_count_before = Order.objects.count()

    price_check_data = {
        "order_lines": [
            {
                "product": product.product_id,
            }
        ],
        "begin": str(two_hour_reservation.begin),
        "end": str(two_hour_reservation.end),
        "customer_group": generate_id()
    }

    response = user_api_client.post(CHECK_PRICE_URL, price_check_data)
    assert response.status_code == 400
    assert order_count_before == 0


@pytest.mark.parametrize('begin, end, customer_group, price_result', (
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
def test_order_price_check_returns_correct_price(begin, end, customer_group, price_result,
    product_with_pcgs_and_time_slot_prices, user_api_client, product_with_all_named_customer_groups):
    '''
    Test the check price endpoint returns correct price for a product containing
    a time slot and product customer groups.
    '''
    price_check_data = {
        "order_lines": [
            {
                "product": product_with_pcgs_and_time_slot_prices.product_id,
            },
            {
                "product": product_with_all_named_customer_groups.product_id,
                "quantity": 0
            },
        ],
        "begin": str(begin),
        "end": str(end),
    }

    if customer_group:
        price_check_data['customer_group'] = customer_group
    response = user_api_client.post(CHECK_PRICE_URL, price_check_data)
    assert response.status_code == 200
    assert len(response.data['order_lines']) == 2
    assert response.data['price'] == price_result


@pytest.mark.parametrize('begin, end, customer_group, price_result', (
    (datetime(2022, 3, 1, 7, 0), datetime(2022, 3, 1, 8, 0), None, '50.25'),
    (datetime(2022, 3, 1, 7, 0), datetime(2022, 3, 1, 11, 0), None, '50.25'),
    (datetime(2022, 3, 1, 10, 0), datetime(2022, 3, 1, 11, 0), None, '10.00'),
    (datetime(2022, 3, 1, 10, 0), datetime(2022, 3, 1, 12, 0), None, '10.00'),
    (datetime(2022, 3, 1, 12, 0), datetime(2022, 3, 1, 13, 0), None, '12.00'),
    (datetime(2022, 3, 1, 12, 0), datetime(2022, 3, 1, 15, 30), None, '11.50'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 16, 0), None, '14.00'),
    (datetime(2022, 3, 1, 10, 0), datetime(2022, 3, 1, 16, 0), 'cg-adults-1', '50.25'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 15, 0), 'cg-adults-1', '8.00'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 16, 0), 'cg-adults-1', '8.00'),
    (datetime(2022, 3, 1, 15, 0), datetime(2022, 3, 1, 16, 0), 'cg-adults-1', '7.00'),
    (datetime(2022, 3, 1, 7, 0), datetime(2022, 3, 1, 8, 0), 'cg-children-1', '6.50'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 16, 0), 'cg-children-1', '6.50'),
    (datetime(2022, 3, 1, 7, 0), datetime(2022, 3, 1, 8, 0), 'cg-elders-1', '50.25'),
    (datetime(2022, 3, 1, 10, 0), datetime(2022, 3, 1, 11, 0), 'cg-elders-1', '10.00'),
    (datetime(2022, 3, 1, 14, 0), datetime(2022, 3, 1, 16, 0), 'cg-elders-1', '14.00'),
))
def test_order_price_check_with_fixed_price_product_returns_correct_price(begin, end, customer_group, price_result,
    product_with_fixed_price_type_and_time_slots, user_api_client, product_with_all_named_customer_groups):
    '''
    Test the check price endpoint returns correct price for a product containing
    time slots, product customer groups and fixed pricing.
    '''
    price_check_data = {
        "order_lines": [
            {
                "product": product_with_fixed_price_type_and_time_slots.product_id,
            },
            {
                "product": product_with_all_named_customer_groups.product_id,
                "quantity": 0
            },
        ],
        "begin": str(begin),
        "end": str(end),
    }

    if customer_group:
        price_check_data['customer_group'] = customer_group
    response = user_api_client.post(CHECK_PRICE_URL, price_check_data)
    assert response.status_code == 200
    assert len(response.data['order_lines']) == 2
    assert response.data['price'] == price_result
