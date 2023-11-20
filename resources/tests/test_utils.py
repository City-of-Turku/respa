import datetime
import pytest
from django.conf import settings
from django.test.utils import override_settings
from resources.models.utils import (
    get_payment_requested_waiting_time, is_reservation_metadata_or_times_different, format_dt_range_alt
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
