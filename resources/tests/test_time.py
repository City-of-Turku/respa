import datetime
from types import SimpleNamespace

import pytest
import pytz

from resources.models import Reservation, Resource
from resources.timetools import OpenHours, TimeWarp, calculate_availability, get_availability


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

    assert len(free_slots) == 3
    assert free_slots[0].begin.hour == 8 and free_slots[0].end.hour == 10
    assert free_slots[1].begin.hour == 11 and free_slots[1].end.hour == 13
    assert free_slots[2].begin.hour == 15 and free_slots[2].end.hour == 18

    filtered = calculate_availability(resource, opening_hours, duration=datetime.timedelta(hours=3))
    assert len(filtered[day]) == 1
    assert filtered[day][0].begin.hour == 15 and filtered[day][0].end.hour == 18


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


@pytest.mark.django_db
def test_get_availability_blocks_by_unit_reservations(resource_in_unit4_1, resource_in_unit4_2):
    begin = _utc_datetime(2115, 5, 1, 8)
    end = _utc_datetime(2115, 5, 1, 18)

    Reservation.objects.create(
        resource=resource_in_unit4_2,
        begin=_utc_datetime(2115, 5, 1, 10),
        end=_utc_datetime(2115, 5, 1, 12),
    )

    resources = Resource.objects.filter(pk=resource_in_unit4_1.pk)
    _, availability = get_availability(begin, end, resources=resources, duration=datetime.timedelta(hours=1))
    slots = availability[resource_in_unit4_1][begin.date()]

    assert len(slots) == 2
    assert slots[0].begin.hour == 8 and slots[0].end.hour == 10
    assert slots[1].begin.hour == 12 and slots[1].end.hour == 18
