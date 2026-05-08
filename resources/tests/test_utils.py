import datetime
from decimal import Decimal
from types import SimpleNamespace
import pytest
import pytz
from django.conf import settings
from django.test.utils import override_settings
from django.utils import translation
from resources.models.utils import (
    calculate_final_order_sums,
    calculate_final_product_sums,
    create_datetime_days_from_now,
    format_dt_range,
    format_dt_range_alt,
    generate_id,
    get_object_or_none,
    get_order_pretax_price,
    get_order_quantity,
    get_order_tax_price,
    get_payment_requested_waiting_time,
    get_translated,
    get_translated_name,
    has_reservation_data_changed,
    humanize_duration,
    is_reservation_metadata_or_times_different,
    is_valid_time_slot,
    product_has_given_tax_percentage,
    save_dt,
    time_to_dtz,
)
from resources.models import Reservation, Resource, Unit
from payments.models import Product, Order
from payments.factories import OrderFactory


@pytest.fixture
def unit_payment_time_defined():
    return Unit.objects.create(
        name="unit_payment",
        time_zone='Europe/Helsinki',
        payment_requested_waiting_time=98
    )

@pytest.fixture
def unit_payment_time_env():
    return Unit.objects.create(
        name="unit_payment",
        time_zone='Europe/Helsinki',
        payment_requested_waiting_time=0
    )

@pytest.fixture
def get_resource_data(space_resource_type):
    return {
        'type': space_resource_type,
        'authentication': 'weak',
        'need_manual_confirmation': True,
        'max_reservations_per_user': 1,
        'max_period': datetime.timedelta(hours=2),
        'reservable': True,
    }

@pytest.fixture
def resource_resource_waiting_time(unit_payment_time_defined, get_resource_data):
    return Resource.objects.create(
        name="resource with waiting_time value.",
        unit=unit_payment_time_defined,
        payment_requested_waiting_time=48,
        **get_resource_data
    )

@pytest.fixture
def resource_unit_waiting_time(unit_payment_time_defined, get_resource_data):
    return Resource.objects.create(
        name="resource with no waiting_time value.",
        unit=unit_payment_time_defined,
        payment_requested_waiting_time=0,
        **get_resource_data
    )
@pytest.fixture
def resource_env_waiting_time(unit_payment_time_env, get_resource_data):
    return Resource.objects.create(
        name="resource with no waiting_time value.",
        unit=unit_payment_time_env,
        payment_requested_waiting_time=0,
        **get_resource_data
    )


@pytest.fixture
def get_reservation_data(user):
    '''
    Dict containing reservation data for the other reservation fixtures.
    '''
    return {
        'begin': '2022-02-02T12:00:00+02:00',
        'end': '2022-02-02T14:00:00+02:00',
        'user': user,
        'state': Reservation.WAITING_FOR_PAYMENT
    }

@pytest.fixture
def get_reservation_extradata(get_reservation_data):
    data_with_extra = get_reservation_data
    data_with_extra.update({
        'reserver_name': 'Test Tester',
        'reserver_email_address': 'test.tester@service.com',
        'reserver_phone_number': '+358404040404',
    })
    return data_with_extra


@pytest.fixture
def reservation_resource_waiting_time(resource_resource_waiting_time, get_reservation_data):
    '''
    Reservation for test where the resource waiting_time is used.
    '''
    return Reservation.objects.create(
        resource=resource_resource_waiting_time,
        reserver_name='name_time_from_resource',
        **get_reservation_data
    )

@pytest.fixture
def reservation_unit_waiting_time(resource_unit_waiting_time, get_reservation_data):
    '''
    Reservation for test where the unit waiting_time is used.
    '''
    return Reservation.objects.create(
        resource=resource_unit_waiting_time,
        reserver_name='name_time_from_unit',
        **get_reservation_data
    )


@pytest.fixture
def reservation_env_waiting_time(resource_env_waiting_time, get_reservation_data):
    '''
    Reservation for test where the env waiting_time is used.
    '''
    return Reservation.objects.create(
        resource=resource_env_waiting_time,
        reserver_name='name_time_from_env',
        **get_reservation_data
    )


@pytest.fixture
def reservation_basic(resource_with_metadata, get_reservation_data):
    return Reservation.objects.create(
        resource=resource_with_metadata,
        reserver_name='basic reserver',
        **get_reservation_data
    )


@pytest.fixture
def get_order_data():
    '''
    Dict containing order data for other fixtures.
    '''
    return {'state': Order.WAITING, 'confirmed_by_staff_at':'2022-01-10T12:00:00+02:00'}

@pytest.fixture
def order_resource_waiting_time(reservation_resource_waiting_time, get_order_data):
    '''
    Order for test where the resource waiting_time is used.
    '''
    return OrderFactory(
        reservation=reservation_resource_waiting_time,
        **get_order_data
    )

@pytest.fixture
def order_unit_waiting_time(reservation_unit_waiting_time, get_order_data):
    '''
    Order for test where the unit waiting_time is used.
    '''
    return OrderFactory(
        reservation=reservation_unit_waiting_time,
        **get_order_data
    )

@pytest.fixture
def order_env_waiting_time(reservation_env_waiting_time, get_order_data):
    '''
    Order for test where the env waiting_time is used.
    '''
    return OrderFactory(
        reservation=reservation_env_waiting_time,
        **get_order_data
    )


def calculate_times(reservation, waiting_time):
    '''
    Used to calculate the expected waiting_time.
    '''
    exact_value = reservation.order.confirmed_by_staff_at + datetime.timedelta(hours=waiting_time)
    rounded_value = exact_value.replace(microsecond=0, second=0, minute=0)
    return rounded_value.astimezone(reservation.resource.unit.get_tz()).strftime('%d.%m.%Y %H:%M')


@pytest.mark.django_db
def test_returns_waiting_time_from_resource(reservation_resource_waiting_time, order_resource_waiting_time):
    '''
    Resource's waiting_time is used if defined.
    '''
    reservation = Reservation.objects.get(reserver_name='name_time_from_resource')
    return_value = get_payment_requested_waiting_time(reservation)

    expected_value = calculate_times(reservation=reservation, waiting_time=reservation.resource.payment_requested_waiting_time)
    assert return_value == expected_value


@pytest.mark.django_db
def test_return_waiting_time_from_unit(reservation_unit_waiting_time, order_unit_waiting_time):
    '''
    Unit waiting_time is used when the resource does not have a waiting_time.
    '''
    reservation = Reservation.objects.get(reserver_name='name_time_from_unit')
    return_value = get_payment_requested_waiting_time(reservation)

    expected_value = calculate_times(reservation=reservation, waiting_time=reservation.resource.unit.payment_requested_waiting_time)
    assert return_value == expected_value


@pytest.mark.django_db
@override_settings(RESPA_PAYMENTS_PAYMENT_REQUESTED_WAITING_TIME=6)
def test_return_waiting_time_from_env(reservation_env_waiting_time, order_env_waiting_time):
    '''
    Environment variable is used when neither the resource or the unit have a waiting_time.
    '''
    reservation = Reservation.objects.get(reserver_name='name_time_from_env')
    return_value = get_payment_requested_waiting_time(reservation)

    expected_value = calculate_times(reservation=reservation, waiting_time=settings.RESPA_PAYMENTS_PAYMENT_REQUESTED_WAITING_TIME)
    assert return_value == expected_value


@pytest.mark.django_db
def test_is_reservation_metadata_or_times_different_when_meta_changes(resource_with_metadata, get_reservation_extradata):
    '''
    Tests that the function returns True when the metadata changes.
    '''
    reservation_a = Reservation.objects.create(resource=resource_with_metadata, **get_reservation_extradata)
    new_data = {'reserver_name': 'new name'}
    updated_extradata = {**get_reservation_extradata, **new_data}
    reservation_b = Reservation.objects.create(resource=resource_with_metadata, **updated_extradata)
    assert is_reservation_metadata_or_times_different(reservation_a, reservation_b) == True


@pytest.mark.django_db
def test_is_reservation_metadata_or_times_different_when_time_changes(resource_with_metadata, get_reservation_extradata):
    '''
    Tests that the function returns True when a time changes.
    '''
    reservation_a = Reservation.objects.create(resource=resource_with_metadata, **get_reservation_extradata)
    new_data = {'end': '2022-02-02T14:30:00+02:00'}
    updated_extradata = {**get_reservation_extradata, **new_data}
    reservation_b = Reservation.objects.create(resource=resource_with_metadata, **updated_extradata)
    assert is_reservation_metadata_or_times_different(reservation_a, reservation_b) == True


@pytest.mark.django_db
def test_is_reservation_metadata_or_times_different_when_no_changes(resource_with_metadata, get_reservation_extradata):
    '''
    Tests that the function returns False when there are no changes.
    '''
    reservation_a = Reservation.objects.create(resource=resource_with_metadata, **get_reservation_extradata)
    reservation_b = Reservation.objects.create(resource=resource_with_metadata, **get_reservation_extradata)
    assert is_reservation_metadata_or_times_different(reservation_a, reservation_b) == False


@pytest.mark.django_db
def test_format_dt_range_alt_same_day(reservation_basic):
    '''
    Tests that the function returns the expected time range when begin and end times are on the same day.
    '''
    reservation = Reservation.objects.get(id=reservation_basic.id)
    tz = reservation.resource.unit.get_tz()
    begin = reservation.begin.astimezone(tz)
    end = reservation.end.astimezone(tz)

    return_value = format_dt_range_alt('fi', begin, end)
    expected_value = '2.2.2022 klo 12.00–14.00'
    assert return_value == expected_value
    return_value = format_dt_range_alt('sv', begin, end)
    expected_value = '2.2.2022 kl 12.00–14.00'
    assert return_value == expected_value
    return_value = format_dt_range_alt('en', begin, end)
    expected_value = '2.2.2022 12:00–14:00'
    assert return_value == expected_value


@pytest.mark.django_db
def test_format_dt_range_alt_different_day(reservation_basic):
    '''
    Tests that the function returns the expected time range when begin and end times are on different day.
    '''
    reservation = Reservation.objects.get(id=reservation_basic.id)
    tz = reservation.resource.unit.get_tz()
    begin = reservation.begin.astimezone(tz)
    end = reservation.end.astimezone(tz) + datetime.timedelta(days=1)

    return_value = format_dt_range_alt('fi', begin, end)
    expected_value = '2.2.2022 klo 12.00 – 3.2.2022 klo 14.00'
    assert return_value == expected_value
    return_value = format_dt_range_alt('sv', begin, end)
    expected_value = '2.2.2022 kl 12.00 – 3.2.2022 kl 14.00'
    assert return_value == expected_value
    return_value = format_dt_range_alt('en', begin, end)
    expected_value = '2.2.2022 12:00 – 3.2.2022 14:00'
    assert return_value == expected_value


@pytest.mark.django_db
def test_has_reservation_data_changed_no_changes(reservation_basic):
    data = {'reserver_name': reservation_basic.reserver_name}
    result = has_reservation_data_changed(data, reservation_basic)
    assert result is False


@pytest.mark.django_db
def test_has_reservation_data_changed_changes(reservation_basic):
    data = {'reserver_name': 'changed name'}
    result = has_reservation_data_changed(data, reservation_basic)
    assert result is True


@pytest.mark.django_db
def test_has_reservation_data_changed_no_instance():
    data = {'reserver_name': 'changed name'}
    result = has_reservation_data_changed(data, None)
    assert result is False


@pytest.mark.django_db
def test_has_reservation_data_changed_empty_data(reservation_basic):
    data = {}
    result = has_reservation_data_changed(data, reservation_basic)
    assert result is False


def test_generate_id_returns_lowercase_string():
    generated = generate_id()
    assert isinstance(generated, str)
    assert generated
    assert generated == generated.lower()


def test_save_dt_and_get_translated_helpers():
    target = SimpleNamespace()
    naive_dt = datetime.datetime(2026, 5, 8, 12, 0)
    save_dt(target, "saved", naive_dt, orig_tz="Europe/Helsinki")
    assert getattr(target, "saved").tzinfo is not None
    assert getattr(target, "saved").utcoffset() == datetime.timedelta(0)

    default_lang = settings.LANGUAGES[0][0]
    translated = SimpleNamespace(**{f"name_{default_lang}": "localized", "name": "fallback"})
    assert get_translated(translated, "name") == "localized"
    assert get_translated_name(translated) == "localized"

    missing_translated = SimpleNamespace(**{f"name_{default_lang}": "", "name": "fallback"})
    assert get_translated(missing_translated, "name") == "fallback"


def test_time_to_dtz_and_time_slot_validation():
    day = datetime.date(2026, 5, 8)
    converted = time_to_dtz(datetime.time(9, 15), date=day)
    assert converted.hour == 9
    assert converted.minute == 15
    assert converted.tzinfo is not None

    arr = SimpleNamespace(year=2026, month=5, day=8)
    converted_with_arr = time_to_dtz(datetime.time(10, 30), arr=arr)
    assert converted_with_arr.hour == 10
    assert converted_with_arr.minute == 30

    assert time_to_dtz(None, date=day) is None

    opening = pytz.utc.localize(datetime.datetime(2026, 5, 8, 8, 0))
    valid = opening + datetime.timedelta(minutes=30)
    invalid = opening + datetime.timedelta(minutes=20)
    slot_size = datetime.timedelta(minutes=30)
    assert is_valid_time_slot(valid, slot_size, opening) is True
    assert is_valid_time_slot(invalid, slot_size, opening) is False


def test_humanize_duration_outputs_expected_strings():
    with translation.override("en"):
        assert humanize_duration(datetime.timedelta(hours=2, minutes=30)) == "2 hours 30 minutes"
        assert humanize_duration(datetime.timedelta(hours=1)) == "1 hour"
        assert humanize_duration(datetime.timedelta(minutes=45)) == "45 minutes"


def test_create_datetime_days_from_now_sets_midnight():
    assert create_datetime_days_from_now(None) is None

    dt = create_datetime_days_from_now(2)
    assert dt.hour == 0
    assert dt.minute == 0
    assert dt.second == 0
    assert dt.microsecond == 0


@pytest.mark.django_db
def test_get_object_or_none_returns_instance_or_none():
    unit = Unit.objects.create(name="unit for object lookup", time_zone="Europe/Helsinki")
    assert get_object_or_none(Unit, pk=unit.pk) == unit
    assert get_object_or_none(Unit, pk=-1) is None


@pytest.mark.django_db
def test_format_dt_range_fi_and_en(reservation_basic):
    reservation = Reservation.objects.get(id=reservation_basic.id)
    tz = reservation.resource.unit.get_tz()
    begin = reservation.begin.astimezone(tz)
    end = reservation.end.astimezone(tz)

    fi_same_day = format_dt_range("fi", begin, end)
    assert "klo" in fi_same_day
    assert "12.00" in fi_same_day
    assert "14.00" in fi_same_day
    assert "–" in fi_same_day

    en_same_day = format_dt_range("en", begin, end)
    assert "12:00" in en_same_day
    assert "14:00" in en_same_day
    assert "–" in en_same_day

    next_day = end + datetime.timedelta(days=1)
    fi_next_day = format_dt_range("fi", begin, next_day)
    assert "klo" in fi_next_day
    assert "12.00" in fi_next_day
    assert "14.00" in fi_next_day
    assert " – " in fi_next_day


def test_product_has_given_tax_percentage():
    product = {"tax_percentage": Decimal("24.00")}
    assert product_has_given_tax_percentage(product, Decimal("24.00")) is True
    assert product_has_given_tax_percentage(product, Decimal("10.00")) is False


def test_calculate_final_product_and_order_sums():
    product_sums = calculate_final_product_sums(
        {
            "a": {"tax_total": Decimal("1.11"), "taxfree_price_total": Decimal("10.00")},
            "b": {"tax_total": Decimal("0.89"), "taxfree_price_total": Decimal("5.00")},
        },
        quantity=2,
    )
    assert product_sums["product_tax_total"] == Decimal("4.00")
    assert product_sums["product_taxfree_total"] == Decimal("30.00")

    all_products = [
        {"tax_percentage": Decimal("24.00"), "product_taxfree_total": Decimal("20.00")},
        {"tax_percentage": Decimal("10.00"), "product_taxfree_total": Decimal("10.00")},
    ]
    totals = calculate_final_order_sums(all_products)["final_order_totals"]
    assert totals["order_taxfree_total"] == Decimal("30.00")
    assert totals["order_tax_total"][Decimal("24.00")] == Decimal("4.80")
    assert totals["order_tax_total"][Decimal("10.00")] == Decimal("1.00")
    assert totals["order_total"] == Decimal("35.80")


def test_order_line_price_helpers_for_price_type_paths():
    per_period_rent = {
        "quantity": "1",
        "unit_price": "40,00",
        "reservation_tax_price": "9,60",
        "reservation_pretax_price": "30,40",
        "product": {
            "price_type": "per_period",
            "type": "rent",
            "price": "10,00",
            "tax_price": "2,40",
            "pretax_price": "7,60",
        },
    }
    assert get_order_quantity(per_period_rent) == 4.0
    assert get_order_tax_price(per_period_rent) == 2.4
    assert get_order_pretax_price(per_period_rent) == 7.6

    non_rent = {
        "quantity": "3",
        "unit_price": "30,00",
        "reservation_tax_price": "7.20",
        "reservation_pretax_price": "22.80",
        "product": {
            "price_type": "per_period",
            "type": "service",
            "price": "10,00",
            "tax_price": "2,40",
            "pretax_price": "7,60",
        },
    }
    assert get_order_quantity(non_rent) == 3.0
    assert get_order_tax_price(non_rent) == 7.2
    assert get_order_pretax_price(non_rent) == 22.8

    zero_price = {
        "quantity": "2",
        "unit_price": "0,00",
        "reservation_tax_price": "0,00",
        "reservation_pretax_price": "0,00",
        "product": {
            "price_type": "fixed",
            "type": "rent",
            "price": "0,00",
            "tax_price": "0,00",
            "pretax_price": "0,00",
        },
    }
    assert get_order_quantity(zero_price) == 2.0
    assert get_order_tax_price(zero_price) == 0.0
    assert get_order_pretax_price(zero_price) == 0.0
