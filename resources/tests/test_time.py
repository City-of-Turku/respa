import datetime
import operator
from types import SimpleNamespace

import pytz

from resources.timetools import OpenHours, TimeWarp, calculate_availability, periods_to_opening_hours


def _utc_datetime(year, month, day, hour, minute=0):
    return pytz.utc.localize(datetime.datetime(year, month, day, hour, minute))


def test_timewarp_serialization_and_floor_ceiling():
    helsinki = pytz.timezone("Europe/Helsinki")
    source_dt = datetime.datetime(2026, 1, 15, 10, 30)
    tw = TimeWarp(
        dt=source_dt,
        end_dt=source_dt + datetime.timedelta(hours=1),
        original_timezone="Europe/Helsinki",
    )

    serialized = tw.serialize(dt_format="{:%Y-%m-%d %H:%M}", zone="Europe/Helsinki")
    assert serialized == {"dt": "2026-01-15 10:30", "end_dt": "2026-01-15 11:30"}
    assert tw.as_date is True
    assert tw.astimezone("Europe/Helsinki").tzinfo.zone == helsinki.zone

    assert tw.ceiling().astimezone("Europe/Helsinki").hour == 0
    assert tw.floor().astimezone("Europe/Helsinki").hour == 0
    assert tw.floor().astimezone("Europe/Helsinki").date() == datetime.date(2026, 1, 16)


def test_timewarp_find_timezone_with_explicit_and_aware_dt():
    aware = pytz.timezone("Europe/Helsinki").localize(datetime.datetime(2026, 2, 1, 9, 0))
    tw = TimeWarp(dt=aware)

    explicit_tz = tw.find_timezone(aware, original_timezone="UTC")
    from_dt_tz = tw.find_timezone(aware)

    assert explicit_tz.zone == "UTC"
    assert from_dt_tz.zone == "Europe/Helsinki"


def test_calculate_availability_from_reservations():
    day = datetime.date(2026, 3, 10)
    opening_hours = {
        day: OpenHours(
            opens=_utc_datetime(2026, 3, 10, 8),
            closes=_utc_datetime(2026, 3, 10, 18),
        )
    }
    reservations = [
        SimpleNamespace(begin=_utc_datetime(2026, 3, 10, 10), end=_utc_datetime(2026, 3, 10, 11)),
        SimpleNamespace(begin=_utc_datetime(2026, 3, 10, 13), end=_utc_datetime(2026, 3, 10, 15)),
    ]
    resource = SimpleNamespace(overlapping_reservations=reservations)

    availability = calculate_availability(resource, opening_hours, duration=datetime.timedelta(hours=1))
    free_slots = availability[day]

    assert len(free_slots) == 1
    assert free_slots[0].begin.hour == 8 and free_slots[0].end.hour == 10

    filtered = calculate_availability(resource, opening_hours, duration=datetime.timedelta(hours=3))
    assert filtered[day] == []


def test_calculate_availability_whole_day_reserved():
    day = datetime.date(2026, 3, 11)
    opening_hours = {
        day: OpenHours(
            opens=_utc_datetime(2026, 3, 11, 8),
            closes=_utc_datetime(2026, 3, 11, 18),
        )
    }
    reservations = [SimpleNamespace(begin=_utc_datetime(2026, 3, 11, 7), end=_utc_datetime(2026, 3, 11, 19))]
    resource = SimpleNamespace(overlapping_reservations=reservations)

    availability = calculate_availability(resource, opening_hours)
    assert availability[day] == []


def test_calculate_availability_prefers_blocking_reservations():
    day = datetime.date(2026, 3, 12)
    opening_hours = {
        day: OpenHours(
            opens=_utc_datetime(2026, 3, 12, 8),
            closes=_utc_datetime(2026, 3, 12, 18),
        )
    }

    own_reservations = [SimpleNamespace(begin=_utc_datetime(2026, 3, 12, 8), end=_utc_datetime(2026, 3, 12, 9))]
    blocking_reservations = [SimpleNamespace(begin=_utc_datetime(2026, 3, 12, 10), end=_utc_datetime(2026, 3, 12, 12))]
    resource = SimpleNamespace(overlapping_reservations=own_reservations)

    availability = calculate_availability(resource, opening_hours, blocking_reservations=blocking_reservations)

    assert len(availability[day]) == 1
    assert availability[day][0].begin.hour == 8 and availability[day][0].end.hour == 10


def test_timewarp_raises_for_invalid_inputs():
    try:
        TimeWarp(dt=1)
    except ValueError:
        pass
    else:
        assert False, "Expected ValueError for dt without tzinfo attribute"

    start = datetime.datetime(2026, 4, 1, 12, 0)
    end = datetime.datetime(2026, 4, 1, 11, 0)
    try:
        TimeWarp(dt=start, end_dt=end, original_timezone="UTC")
    except ValueError:
        pass
    else:
        assert False, "Expected ValueError when end_dt is before dt"


def test_timewarp_delta_comparisons_and_utc_conversion():
    tw = TimeWarp(dt=datetime.datetime(2026, 4, 2, 10, 0), original_timezone="Europe/Helsinki")
    plus_hour = tw.get_delta(datetime.timedelta(hours=1), operator.add)
    minus_hour = tw.get_delta(datetime.timedelta(hours=1), operator.sub)

    assert plus_hour > tw
    assert minus_hour < tw
    assert tw != plus_hour
    assert tw == TimeWarp(dt=datetime.datetime(2026, 4, 2, 10, 0), original_timezone="Europe/Helsinki")

    utc_from_naive = tw.dt_as_utc(datetime.datetime(2026, 4, 2, 8, 0))
    assert utc_from_naive.utcoffset() == datetime.timedelta(0)


def test_timewarp_day_range_and_default_serialize():
    tw = TimeWarp(day=datetime.date(2026, 7, 1), end_day=datetime.date(2026, 7, 2))
    assert tw.as_date is True
    assert tw.end_dt is not None
    serialized = tw.serialize()
    assert "dt" in serialized
    assert "end_dt" in serialized


def test_timewarp_get_delta_with_explicit_zone_and_astimezone_default():
    tw = TimeWarp(dt=datetime.datetime(2026, 8, 5, 12, 0), original_timezone="Europe/Helsinki")
    utc_delta = tw.get_delta(datetime.timedelta(hours=2), operator.add, zone=pytz.utc)

    # zone parameter path should produce a valid TimeWarp in UTC timeline
    assert utc_delta.dt.utcoffset() == datetime.timedelta(0)
    assert tw.astimezone().tzinfo.zone == "Europe/Helsinki"


def test_calculate_availability_without_reservations_returns_empty_mapping():
    day = datetime.date(2026, 9, 1)
    opening_hours = {
        day: OpenHours(opens=_utc_datetime(2026, 9, 1, 8), closes=_utc_datetime(2026, 9, 1, 18))
    }
    resource = SimpleNamespace(overlapping_reservations=[])
    assert calculate_availability(resource, opening_hours) == {}


def test_periods_to_opening_hours_unit_and_resource_overrides():
    begin_dt = datetime.datetime(2026, 6, 1, 0, 0)
    end_dt = datetime.datetime(2026, 6, 3, 0, 0)
    monday = datetime.date(2026, 6, 1)
    tuesday = datetime.date(2026, 6, 2)

    def day(weekday, opens=None, closes=None, closed=False):
        return SimpleNamespace(weekday=weekday, opens=opens, closes=closes, closed=closed)

    unit_period = SimpleNamespace(
        start=monday,
        end=tuesday,
        days=SimpleNamespace(all=lambda: [day(0, datetime.time(8, 0), datetime.time(16, 0))]),
    )
    # Resource-specific period overrides unit period for Monday
    resource_period = SimpleNamespace(
        start=monday,
        end=tuesday,
        days=SimpleNamespace(all=lambda: [day(0, datetime.time(10, 0), datetime.time(12, 0))]),
    )

    resource = SimpleNamespace(
        overlapping_unit=SimpleNamespace(periods=SimpleNamespace(all=lambda: [unit_period])),
        overlapping_periods=[resource_period],
    )

    hours = periods_to_opening_hours(resource, begin_dt, end_dt)
    assert hours[monday].opens.hour == 10
    assert hours[monday].closes.hour == 12
    assert hours[tuesday] is False


def test_periods_to_opening_hours_closed_and_overnight_day():
    begin_dt = datetime.datetime(2026, 6, 1, 0, 0)
    end_dt = datetime.datetime(2026, 6, 3, 0, 0)
    monday = datetime.date(2026, 6, 1)
    tuesday = datetime.date(2026, 6, 2)

    def day(weekday, opens=None, closes=None, closed=False):
        return SimpleNamespace(weekday=weekday, opens=opens, closes=closes, closed=closed)

    overnight_period = SimpleNamespace(
        start=monday,
        end=tuesday,
        days=SimpleNamespace(
            all=lambda: [
                day(0, datetime.time(22, 0), datetime.time(2, 0)),
                day(1, closed=True),
            ]
        ),
    )

    resource = SimpleNamespace(
        overlapping_unit=None,
        overlapping_periods=[overnight_period],
    )

    hours = periods_to_opening_hours(resource, begin_dt, end_dt)
    assert hours[monday].opens.hour == 22
    assert hours[monday].closes.date() == monday + datetime.timedelta(days=1)
    assert hours[tuesday] is False
