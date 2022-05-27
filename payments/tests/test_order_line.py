from datetime import timedelta
from decimal import Decimal

import pytest

from payments.factories import OrderLineFactory
from payments.models import Product


@pytest.fixture(autouse=True)
def auto_use_django_db(db):
    pass


@pytest.fixture
def order_line_price(two_hour_reservation, resource_in_unit):
    return OrderLineFactory(
        quantity=1,
        product__price=Decimal('12.40'),
        product__tax_percentage=Decimal('24.00'),
        product__price_type=Product.PRICE_PER_PERIOD,
        product__price_period=timedelta(hours=1),
        product__resources=[resource_in_unit],
        order__reservation=two_hour_reservation
    )

@pytest.fixture
def order_line_tax_price_period(three_hour_thirty_minute_reservation, resource_in_unit):
    return OrderLineFactory(
        quantity=1,
        product__price=Decimal('15.00'),
        product__tax_percentage=Decimal('24.00'),
        product__price_type=Product.PRICE_PER_PERIOD,
        product__price_period=timedelta(minutes=30),
        product__resources=[resource_in_unit],
        order__reservation=three_hour_thirty_minute_reservation
    )

@pytest.fixture
def order_line_tax_price_fixed(three_hour_thirty_minute_reservation, resource_in_unit):
    return OrderLineFactory(
        quantity=1,
        product__price=Decimal('60.00'),
        product__tax_percentage=Decimal('14.00'),
        product__price_type=Product.PRICE_FIXED,
        product__resources=[resource_in_unit],
        order__reservation=three_hour_thirty_minute_reservation
    )


def test_get_price_correct(order_line_price):
    """Test price calculation works correctly for prices with tax

    Two hour reservation of one product with a price of 12.40, plus
    individual product tax of 24% should equal 24.80"""
    price = order_line_price.get_price()
    assert price == Decimal('24.80')


def test_get_pretax_price_fixed_order(order_line_tax_price_fixed):
    """
    Test pre-tax price calculation works correctly for fixed prices with tax.

    Three hour and 30 minute reservation, price is 60 and tax percentage is 14%.

    pretax_price = 100 * 60 / (100 + 14) = ~52.63.
    """
    pretax_price = order_line_tax_price_fixed.get_pretax_price_for_reservation()
    assert pretax_price == Decimal('52.63')

def test_get_pretax_price_period_order(order_line_tax_price_period):
    """
    Test pre-tax price calculation works correctly for period prices with tax.

    Three hour and 30 minute reservation, price is 15 per 30 minutes period and tax percentage is 24%.
    Total price = 15 * 7 = 105.

    pretax_price = 100 * 105 / (100 + 24) = ~84.68.
    """
    pretax_price = order_line_tax_price_period.get_pretax_price_for_reservation()
    assert pretax_price == Decimal('84.68')

def test_get_tax_price_fixed_order(order_line_tax_price_fixed):
    """
    Test tax price calculation work correctly for fixed prices.
    Three hour and 30 minute reservation, price is 60 and tax percentage is 14%.

    tax_price = 14 * 60 / (100 + 14) = ~7.37.
    """
    tax_price = order_line_tax_price_fixed.get_tax_price_for_reservation()
    assert tax_price == Decimal('7.37')

def test_get_tax_price_period_order(order_line_tax_price_period):
    """
    Test tax price calculation work correctly for period prices.
    Three hour and 30 minute reservation, price is 15 per 30 minutes period and tax percentage is 24%.
    Total price = 15 * 7 = 105.

    tax_price = 24 * 105 / (100 + 24) = ~20.32.
    """
    tax_price = order_line_tax_price_period.get_tax_price_for_reservation()
    assert tax_price == Decimal('20.32')
