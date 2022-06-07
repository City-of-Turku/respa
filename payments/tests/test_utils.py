from datetime import datetime, time
from decimal import Decimal

import pytest
from payments.factories import TimeSlotPriceFactory
from payments.models import CustomerGroup, TimeSlotPrice

from payments.utils import (find_time_slot_with_smallest_duration, get_fixed_time_slot_price,
    is_datetime_between_times, is_datetime_range_between_times, price_as_sub_units, round_price)


@pytest.fixture
def price_even():
    return Decimal('10.00')


@pytest.fixture
def price_round_up():
    return Decimal('9.995')


@pytest.fixture
def price_round_down():
    return Decimal('9.994')


def test_price_as_sub_units(price_even):
    """Test the price is converted to sub units"""
    even = price_as_sub_units(price_even)
    assert even == 1000


def test_round_price(price_even, price_round_up, price_round_down):
    """Test the price is round correctly"""
    even = round_price(price_even)
    up = round_price(price_round_up)
    down = round_price(price_round_down)
    assert even == Decimal('10.00')
    assert up == Decimal('10.00')
    assert down == Decimal('9.99')


@pytest.mark.parametrize('time, begin, end, result', (
    (datetime(2022, 4, 25, 9, 0, 0), time(8, 0), time(10, 0), True),
    (datetime(2022, 4, 25, 9, 0, 0), time(9, 0), time(10, 0), True),
    (datetime(2022, 4, 25, 9, 0, 0), time(9, 30), time(10, 0), False),
    (datetime(2022, 4, 25, 9, 0, 0), time(8, 0), time(9, 0), True),
    (datetime(2022, 4, 25, 9, 0, 0), time(8, 0), time(8, 30), False),
))
def test_is_datetime_between_times(time, begin, end, result):
    """Test returns correctly when time is between begin and end"""
    assert is_datetime_between_times(time, begin, end) == result


@pytest.mark.parametrize('date_begin, date_end, time_begin, time_end, result', (
    (datetime(2022, 4, 25, 9), datetime(2022, 4, 25, 10), time(8, 0), time(10, 0), True),
    (datetime(2022, 4, 25, 9), datetime(2022, 4, 25, 10), time(9, 0), time(10, 0), True),
    (datetime(2022, 4, 25, 9), datetime(2022, 4, 25, 10), time(9, 30), time(10, 0), False),
    (datetime(2022, 4, 25, 9), datetime(2022, 4, 25, 10), time(8, 0), time(9, 0), False),
))
def test_is_datetime_range_between_times(date_begin, date_end, time_begin, time_end, result):
    """Test returns correctly when datetimes are between times"""
    assert is_datetime_range_between_times(date_begin, date_end, time_begin, time_end) == result


@pytest.mark.parametrize('slot_times', (
    ([[time(8, 0), time(10, 0), False], [time(9, 0), time(10, 0), True], [time(7, 0), time(11, 0), False]]),
    ([[time(8, 30), time(16, 0), False], [time(12, 0), time(15, 0), False], [time(11, 0), time(13, 30), True]]),
    ([[time(10, 0), time(14, 30), True], [time(9, 0), time(17, 0), False]]),
    ([[time(8, 0), time(16, 0), False], [time(8, 30), time(10, 30), True], [time(7, 0), time(13, 0), False],
    [time(7, 0), time(18, 0), False]]),
))
@pytest.mark.django_db
def test_find_time_slot_with_smallest_duration(slot_times):
    """Test returns correctly the time slot with smallest duration"""
    time_slot_prices = []
    expected_result = None
    for slot_time in slot_times:
        time_slot_price = TimeSlotPriceFactory.create(
            begin = slot_time[0],
            end = slot_time[1]
        )
        time_slot_prices.append(time_slot_price)
        if slot_time[2]:
            expected_result = time_slot_price
    time_slot_qs = TimeSlotPrice.objects.all()
    assert find_time_slot_with_smallest_duration(time_slot_qs) == expected_result


@pytest.mark.parametrize('begin, end, customer_group, default_price, result', (
    (time(7, 0), time(8, 0), None, 50.25, 50.25), # default price
    (time(7, 0), time(11, 0), None, 50.25, 50.25), # default price
    (time(10, 0), time(11, 0), None, 50.25, 10.00), # slot price
    (time(10, 0), time(12, 0), None, 50.25, 10.00), # slot price
    (time(12, 0), time(13, 0), None, 50.25, 12.00), # slot price
    (time(12, 0), time(15, 30), None, 50.25, 11.50), # slot price
    (time(14, 0), time(16, 0), None, 50.25, 14.00), # slot price
    (time(10, 0), time(16, 0), 'cg-adults-1', 50.25, 50.25), # default price
    (time(14, 0), time(15, 0), 'cg-adults-1', 50.25, 8.00), # slot cg price
    (time(14, 0), time(16, 0), 'cg-adults-1', 50.25, 8.00), # slot cg price
    (time(15, 0), time(16, 0), 'cg-adults-1', 50.25, 7.00), # slot cg price
    (time(7, 0), time(8, 0), 'cg-children-1', 6.50, 6.50), # default (pcg) price
    (time(14, 0), time(16, 0), 'cg-children-1', 6.50, 6.50), # default (pcg) price
    (time(7, 0), time(8, 0), 'cg-elders-1', 50.25, 50.25), # default price
    (time(10, 0), time(11, 0), 'cg-elders-1', 50.25, 10.00), # slot price
    (time(14, 0), time(16, 0), 'cg-elders-1', 50.25, 14.00), # slot price
))
@pytest.mark.django_db
def test_get_fixed_time_slot_price(begin, end, customer_group, default_price,
    result, product_with_fixed_price_type_and_time_slots, customer_group_elders):
    """Tests that correct time slot price or default price is returned for given situation"""
    prod = product_with_fixed_price_type_and_time_slots
    if customer_group:
        prod._in_memory_cg = CustomerGroup.objects.get(id=customer_group)
    else:
        prod._in_memory_cg = None
    time_slot_qs = TimeSlotPrice.objects.filter(product=prod)
    assert get_fixed_time_slot_price(time_slot_qs, begin, end, prod, default_price) == Decimal(result)
