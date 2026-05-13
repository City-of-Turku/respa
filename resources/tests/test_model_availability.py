import datetime

import pytest
import pytz
from freezegun import freeze_time
from django.core.exceptions import ValidationError

from resources.models import Day, Period
from resources.models.availability import combine_datetime, datetime_to_date, get_opening_hours


@pytest.mark.django_db
def test_get_opening_hours_normalizes_datetime_range(test_unit):
    period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2026, 1, 1),
        end=datetime.date(2026, 1, 3),
        name="normalized range",
    )
    Day.objects.create(period=period, weekday=3, opens=datetime.time(8, 0), closes=datetime.time(16, 0))

    tz = test_unit.get_tz()
    begin_dt = tz.localize(datetime.datetime(2026, 1, 1, 12, 0))
    end_dt = tz.localize(datetime.datetime(2026, 1, 1, 18, 0))
    hours = get_opening_hours(test_unit.time_zone, [period], begin_dt, end_dt)

    day_data = hours[datetime.date(2026, 1, 1)][0]
    assert day_data["opens"].hour == 8
    assert day_data["closes"].hour == 16


@pytest.mark.django_db
def test_get_opening_hours_prefers_shorter_period_when_priority_equal(test_unit):
    long_period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2026, 2, 1),
        end=datetime.date(2026, 2, 28),
        name="long",
    )
    short_period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2026, 2, 3),
        end=datetime.date(2026, 2, 3),
        name="short",
    )
    Day.objects.create(period=long_period, weekday=1, opens=datetime.time(9, 0), closes=datetime.time(17, 0))
    Day.objects.create(period=short_period, weekday=1, opens=datetime.time(11, 0), closes=datetime.time(12, 0))

    # `priority` isn't a model field but function supports dynamic attribute.
    long_period.priority = 1
    short_period.priority = 1

    hours = get_opening_hours(
        test_unit.time_zone,
        [long_period, short_period],
        datetime.date(2026, 2, 3),
        datetime.date(2026, 2, 3),
    )
    day_data = hours[datetime.date(2026, 2, 3)][0]
    assert day_data["opens"].hour == 11
    assert day_data["closes"].hour == 12


@pytest.mark.django_db
def test_get_opening_hours_closed_day_and_zero_length_interval(test_unit):
    closed_period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2026, 3, 2),
        end=datetime.date(2026, 3, 2),
        name="closed day",
    )
    Day.objects.create(period=closed_period, weekday=0, closed=True)

    zero_period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2026, 3, 3),
        end=datetime.date(2026, 3, 3),
        name="zero interval",
    )
    Day.objects.create(period=zero_period, weekday=1, opens=datetime.time(10, 0), closes=datetime.time(10, 0))

    hours = get_opening_hours(
        test_unit.time_zone,
        [closed_period, zero_period],
        datetime.date(2026, 3, 2),
        datetime.date(2026, 3, 3),
    )

    monday_data = hours[datetime.date(2026, 3, 2)][0]
    tuesday_data = hours[datetime.date(2026, 3, 3)][0]
    assert monday_data["opens"] is None and monday_data["closes"] is None
    assert tuesday_data["opens"] is None and tuesday_data["closes"] is None


@freeze_time("2026-04-10")
@pytest.mark.django_db
def test_get_opening_hours_defaults_begin_and_end_to_today(test_unit):
    period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2026, 4, 10),
        end=datetime.date(2026, 4, 10),
        name="today period",
    )
    Day.objects.create(period=period, weekday=4, opens=datetime.time(8, 30), closes=datetime.time(9, 30))

    hours = get_opening_hours(test_unit.time_zone, [period], begin=None, end=None)
    assert list(hours.keys()) == [datetime.date(2026, 4, 10)]
    day_data = hours[datetime.date(2026, 4, 10)][0]
    assert day_data["opens"].hour == 8
    assert day_data["closes"].hour == 9


@pytest.mark.django_db
def test_datetime_to_date_handles_naive_and_aware(test_unit):
    tz = test_unit.get_tz()
    naive = datetime.datetime(2026, 5, 1, 12, 0)
    aware = tz.localize(datetime.datetime(2026, 5, 1, 13, 0))

    assert datetime_to_date(naive, tz) == datetime.date(2026, 5, 1)
    assert datetime_to_date(aware, tz) == datetime.date(2026, 5, 1)


# ---------------------------------------------------------------------------
# combine_datetime
# ---------------------------------------------------------------------------

def test_combine_datetime_produces_aware_datetime():
    tz = pytz.timezone("Europe/Helsinki")
    dt = combine_datetime(datetime.date(2026, 7, 1), datetime.time(9, 30), tz)
    assert dt.date() == datetime.date(2026, 7, 1)
    assert dt.time() == datetime.time(9, 30)
    assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# Period.__str__, _validate_belonging, clean, _check_closed, save_closedness
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_period_str(test_unit):
    period = Period(
        unit=test_unit,
        start=datetime.date(2026, 1, 1),
        end=datetime.date(2026, 12, 31),
        name="Test period",
        closed=False,
    )
    text = str(period)
    assert "Test period" in text
    assert "2026" in text


@pytest.mark.django_db
def test_period_validate_belonging_no_unit_or_resource():
    period = Period(start=datetime.date(2026, 1, 1), end=datetime.date(2026, 1, 31))
    with pytest.raises(ValidationError):
        period._validate_belonging()


@pytest.mark.django_db
def test_period_validate_belonging_both_set(test_unit, resource_in_unit):
    period = Period(
        unit=test_unit,
        resource=resource_in_unit,
        start=datetime.date(2026, 1, 1),
        end=datetime.date(2026, 1, 31),
    )
    with pytest.raises(ValidationError):
        period._validate_belonging()


@pytest.mark.django_db
def test_period_clean_missing_dates(test_unit):
    period = Period(unit=test_unit, start=None, end=None)
    with pytest.raises(ValidationError):
        period.clean()


@pytest.mark.django_db
def test_period_clean_start_after_end(test_unit):
    period = Period(
        unit=test_unit,
        start=datetime.date(2026, 6, 30),
        end=datetime.date(2026, 6, 1),
    )
    with pytest.raises(ValidationError):
        period.clean()


@pytest.mark.django_db
def test_period_check_closed_unsaved(test_unit):
    period = Period(
        unit=test_unit,
        start=datetime.date(2026, 1, 1),
        end=datetime.date(2026, 1, 31),
    )
    period._check_closed()
    # Unsaved → no days → closed
    assert period.closed is True


@pytest.mark.django_db
def test_period_check_closed_saved_with_open_day(test_unit):
    period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2116, 1, 1),
        end=datetime.date(2116, 12, 31),
        name="open period",
    )
    Day.objects.create(period=period, weekday=0, opens=datetime.time(8, 0), closes=datetime.time(16, 0))
    period._check_closed()
    assert period.closed is False


@pytest.mark.django_db
def test_period_save_closedness(test_unit):
    period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2116, 1, 1),
        end=datetime.date(2116, 12, 31),
        name="save closedness test",
    )
    Day.objects.create(period=period, weekday=1, opens=datetime.time(9, 0), closes=datetime.time(17, 0))
    period.save_closedness()
    period.refresh_from_db()
    assert period.closed is False


# ---------------------------------------------------------------------------
# Day.__str__, Day.save (length calculation)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_day_str_with_hours(test_unit):
    period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2116, 3, 1),
        end=datetime.date(2116, 3, 31),
        name="day str test",
    )
    day = Day.objects.create(
        period=period,
        weekday=0,
        opens=datetime.time(8, 0),
        closes=datetime.time(16, 0),
    )
    text = str(day)
    assert "8:00" in text
    assert "16:00" in text


@pytest.mark.django_db
def test_day_str_without_hours(test_unit):
    period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2116, 4, 1),
        end=datetime.date(2116, 4, 30),
        name="closed day",
    )
    day = Day.objects.create(period=period, weekday=0, closed=True)
    text = str(day)
    # Weekday display depends on active language — just confirm the string is not empty
    assert len(text) > 0


@pytest.mark.django_db
def test_day_save_sets_length_range(test_unit):
    period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2116, 5, 1),
        end=datetime.date(2116, 5, 31),
        name="day length test",
    )
    day = Day.objects.create(
        period=period,
        weekday=2,
        opens=datetime.time(9, 0),
        closes=datetime.time(17, 30),
    )
    day.refresh_from_db()
    assert day.length is not None
    assert day.length.lower == 90000   # "09:00:00" → "090000" → 90000
    assert day.length.upper == 173000  # "17:30:00" → "173000" → 173000


@pytest.mark.django_db
def test_day_save_no_length_when_no_hours(test_unit):
    period = Period.objects.create(
        unit=test_unit,
        start=datetime.date(2116, 6, 1),
        end=datetime.date(2116, 6, 30),
        name="no hours day",
    )
    day = Day.objects.create(period=period, weekday=3, closed=True)
    day.refresh_from_db()
    assert day.length is None

