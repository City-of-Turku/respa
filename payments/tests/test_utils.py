from datetime import datetime, time
from decimal import Decimal

import pytest

from payments.utils import is_datetime_between_times, is_datetime_range_between_times, price_as_sub_units, round_price


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
