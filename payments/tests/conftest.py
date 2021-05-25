import datetime
from decimal import Decimal

import factory.random
import pytest
from pytz import UTC

from payments.factories import OrderFactory, OrderLineFactory
from payments.models import Order, Product
from resources.models import Reservation
from resources.tests.conftest import *  # noqa


@pytest.fixture(autouse=True)
def set_fixed_random_seed():
    factory.random.reseed_random(777)


@pytest.fixture()
def two_hour_reservation(resource_in_unit, user):
    """A two-hour reservation fixture with actual datetime objects"""
    return Reservation.objects.create(
        resource=resource_in_unit,
        begin=datetime.datetime(2119, 5, 5, 10, 0, 0, tzinfo=UTC),
        end=datetime.datetime(2119, 5, 5, 12, 0, 0, tzinfo=UTC),
        user=user,
        event_subject='some fancy event',
        host_name='esko',
        reserver_name='martta',
        state=Reservation.CONFIRMED,
        billing_first_name='Seppo',
        billing_last_name='Testi',
        billing_email_address='test@example.com',
        billing_phone_number='555555555',
        billing_address_street='Test street 1',
        billing_address_zip='12345',
        billing_address_city='Testcity',
    )

@pytest.fixture()
def three_hour_thirty_minute_reservation(resource_in_unit, user):
    """A three and a half hour reservation fixture with actual datetime objects"""
    return Reservation.objects.create(
        resource=resource_in_unit,
        begin=datetime.datetime(2048, 1, 20, 12, 0, 0, tzinfo=UTC),
        end=datetime.datetime(2048, 1, 20, 15, 30, 0, tzinfo=UTC),
        user=user,
        event_subject='a three and a half hour event',
        host_name='Esko Esimerkki',
        reserver_name='Martta Meikäläinen',
        state=Reservation.CONFIRMED,
        billing_first_name='Mikko',
        billing_last_name='Maksaja',
        billing_email_address='mikko@maksaja.com',
        billing_phone_number='555555555',
        billing_address_street='Maksupolku 1',
        billing_address_zip='12345',
        billing_address_city='Kaupunkikylä',
    )

@pytest.fixture()
def order_with_product(three_hour_thirty_minute_reservation):
    Reservation.objects.filter(id=three_hour_thirty_minute_reservation.id).update(state=Reservation.WAITING_FOR_PAYMENT)
    three_hour_thirty_minute_reservation.refresh_from_db()

    order = OrderFactory.create(
        order_number='123orderABC',
        state=Order.WAITING,
        reservation=three_hour_thirty_minute_reservation
    )
    OrderLineFactory.create(
        quantity=1,
        product__name="Test product",
        product__price=Decimal('18.00'),
        product__tax_percentage=Decimal('24.00'),
        product__price_type=Product.PRICE_PER_PERIOD,
        product__price_period=datetime.timedelta(hours=0.5),
        order=order
    )

    return order

@pytest.fixture()
def order_with_products(two_hour_reservation):
    Reservation.objects.filter(id=two_hour_reservation.id).update(state=Reservation.WAITING_FOR_PAYMENT)
    two_hour_reservation.refresh_from_db()

    order = OrderFactory.create(
        order_number='abc123',
        state=Order.WAITING,
        reservation=two_hour_reservation
    )
    OrderLineFactory.create(
        quantity=1,
        product__name="Test product",
        product__price=Decimal('12.40'),
        product__tax_percentage=Decimal('24.00'),
        product__price_type=Product.PRICE_PER_PERIOD,
        product__price_period=datetime.timedelta(hours=1),
        order=order
    )
    OrderLineFactory.create(
        quantity=1,
        product__name="Test product 2",
        product__price=Decimal('12.40'),
        product__tax_percentage=Decimal('24.00'),
        product__price_type=Product.PRICE_FIXED,
        order=order
    )
    return order
