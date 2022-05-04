import datetime
from decimal import Decimal

import factory.random
import pytest
import datetime
from pytz import UTC

from payments.factories import (
    CustomerGroupTimeSlotPriceFactory, OrderFactory, OrderLineFactory, CustomerGroupFactory,
    ProductFactory, ProductCustomerGroupFactory, OrderCustomerGroupDataFactory, TimeSlotPriceFactory
)
from payments.models import Order, Product, ProductCustomerGroup
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


@pytest.fixture
def order_with_selected_cg_and_product_with_pcgs_and_time_slots(two_hour_reservation,
    product_with_pcgs_and_time_slot_prices, customer_group_adults):
    Reservation.objects.filter(id=two_hour_reservation.id).update(
        state=Reservation.WAITING_FOR_PAYMENT,
        begin=datetime.datetime(2119, 5, 5, 10, 0, 0),
        end=datetime.datetime(2119, 5, 5, 12, 0, 0)
    )
    two_hour_reservation.refresh_from_db()

    order = OrderFactory.create(
        order_number='abc123',
        state=Order.WAITING,
        reservation=two_hour_reservation,
        customer_group=customer_group_adults
    )
    order_line = OrderLineFactory.create(
        quantity=1,
        product=product_with_pcgs_and_time_slot_prices,
        order=order
    )
    prod_cg = ProductCustomerGroup.objects.get(customer_group=customer_group_adults)
    ocgd = OrderCustomerGroupDataFactory.create(order_line=order_line,
        product_cg_price=ProductCustomerGroup.objects.get_price_for(order_line.product))
    ocgd.copy_translated_fields(prod_cg.customer_group)
    ocgd.save()

    return order


@pytest.fixture
def product_customer_group():
    return ProductCustomerGroupFactory.create()

@pytest.fixture
def product_customer_groups():
    return [ProductCustomerGroupFactory.create() for _ in range(0,5)]

@pytest.fixture
def customer_groups():
    return [CustomerGroupFactory.create() for _ in range(0,5)]

@pytest.fixture
def customer_group():
    return CustomerGroupFactory.create()

@pytest.fixture
def product_with_multiple_product_cg(product_customer_groups, resource_in_unit):
    product = ProductFactory.create(
            tax_percentage=Decimal('24.00'),
            price=Decimal('7.25'),
            price_type=Product.PRICE_PER_PERIOD,
            resources=[resource_in_unit],
            price_period=datetime.timedelta(hours=1)
        )
    for pcg in product_customer_groups:
        pcg.product = product
        pcg.save()
    return product


@pytest.fixture
def product_with_product_cg(product_customer_group, resource_in_unit):
    product = ProductFactory.create(
            tax_percentage=Decimal('24.00'),
            price=Decimal('50.25'),
            price_type=Product.PRICE_PER_PERIOD,
            resources=[resource_in_unit],
            price_period=datetime.timedelta(hours=1)
        )
    product_customer_group.product = product
    product_customer_group.save()
    return product

@pytest.fixture
def product_with_no_price_product_cg(product_customer_group, resource_in_unit):
    product = ProductFactory.create(
            tax_percentage=Decimal('24.00'),
            price=Decimal('50.25'),
            price_type=Product.PRICE_PER_PERIOD,
            resources=[resource_in_unit],
            price_period=datetime.timedelta(hours=1)
        )
    product_customer_group.price = Decimal('0.00')
    product_customer_group.product = product
    product_customer_group.save()
    return product

@pytest.fixture
def product_extra_manual_confirmation(resource_with_manual_confirmation, customer_group):
    product = ProductFactory.create(
        type=Product.EXTRA,
        resources=[resource_with_manual_confirmation]
    )
    ProductCustomerGroupFactory.create(product=product, customer_group=customer_group)
    return product


@pytest.fixture
def order_with_product_customer_group(product_with_product_cg, two_hour_reservation):
    prod_cg = ProductCustomerGroup.objects.get(product=product_with_product_cg)
    order = OrderFactory.create(
        order_number='abc123',
        state=Order.WAITING,
        reservation=two_hour_reservation
    )
    order_line = OrderLineFactory.create(
        quantity=1,
        product=product_with_product_cg,
        order=order
    )
    ocgd = OrderCustomerGroupDataFactory.create(order_line=order_line,
        product_cg_price=ProductCustomerGroup.objects.get_price_for(order_line.product))
    ocgd.copy_translated_fields(prod_cg.customer_group)
    ocgd.save()
    return order

@pytest.fixture
def order_with_no_price_product_customer_group(product_with_no_price_product_cg, two_hour_reservation):
    prod_cg = ProductCustomerGroup.objects.get(product=product_with_no_price_product_cg)
    order = OrderFactory.create(
        order_number='abc123',
        state=Order.WAITING,
        reservation=two_hour_reservation
    )
    order_line = OrderLineFactory.create(
        quantity=1,
        product=product_with_no_price_product_cg,
        order=order
    )
    ocgd = OrderCustomerGroupDataFactory.create(order_line=order_line,
        product_cg_price=ProductCustomerGroup.objects.get_price_for(order_line.product))
    ocgd.copy_translated_fields(prod_cg.customer_group)
    ocgd.save()
    return order


@pytest.fixture
def customer_group_adults():
    return CustomerGroupFactory(name='Adults', id='cg-adults-1')


@pytest.fixture
def customer_group_children():
    return CustomerGroupFactory(name='Children', id='cg-children-1')


@pytest.fixture
def customer_group_elders():
    return CustomerGroupFactory(name='Elders', id='cg-elders-1')


@pytest.fixture
def customer_group_companies():
    return CustomerGroupFactory(name='Companies', id='cg-companies-1')


@pytest.fixture
def product_with_pcgs_and_time_slot_prices(customer_group_adults,
    customer_group_children, customer_group_elders, resource_in_unit):
    product = ProductFactory.create(
            tax_percentage=Decimal('24.00'),
            price=Decimal('15.00'),
            price_type=Product.PRICE_PER_PERIOD,
            resources=[resource_in_unit],
            price_period=datetime.timedelta(hours=1)
        )
    ProductCustomerGroupFactory.create(
        customer_group=customer_group_adults,
        product=product, price=Decimal('12.00')
    )
    ProductCustomerGroupFactory.create(
        customer_group=customer_group_children,
        product=product, price=Decimal('11.00')
    )
    time_slot_10_to_12 = TimeSlotPriceFactory.create(
        begin=datetime.time(10, 0), end=datetime.time(12, 0),
        price=Decimal('10.00'), product=product
    )
    CustomerGroupTimeSlotPriceFactory.create(
        customer_group=customer_group_adults, price=Decimal('8.00'),
        time_slot_price=time_slot_10_to_12
    )
    CustomerGroupTimeSlotPriceFactory.create(
        customer_group=customer_group_elders, price=Decimal('6.00'),
        time_slot_price=time_slot_10_to_12
    )
    return product


@pytest.fixture
def product_with_all_named_customer_groups(customer_group_adults,
    customer_group_children, customer_group_elders, customer_group_companies,
    resource_in_unit):
    product = ProductFactory.create(resources=[resource_in_unit])
    ProductCustomerGroupFactory.create(
        customer_group=customer_group_adults,
        product=product, price=Decimal('150.00')
    )
    ProductCustomerGroupFactory.create(
        customer_group=customer_group_children,
        product=product, price=Decimal('125.00')
    )
    ProductCustomerGroupFactory.create(
        customer_group=customer_group_elders,
        product=product, price=Decimal('130.00')
    )
    ProductCustomerGroupFactory.create(
        customer_group=customer_group_companies,
        product=product, price=Decimal('175.00')
    )
    return product
