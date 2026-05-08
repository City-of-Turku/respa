import datetime
from types import SimpleNamespace

import pytz

from resources.timetools import OpenHours, TimeWarp, calculate_availability


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
