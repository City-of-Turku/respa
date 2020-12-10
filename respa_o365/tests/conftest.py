import pytest
import datetime
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient, APIRequestFactory

from resources.enums import UnitAuthorizationLevel
from resources.models import Resource, ResourceType, Unit, Purpose, Day, Period, Reservation
from resources.models import Equipment, EquipmentAlias, ResourceEquipment, EquipmentCategory, TermsOfUse, ResourceGroup
from resources.models import AccessibilityValue, AccessibilityViewpoint, ResourceAccessibility, UnitAccessibility
from munigeo.models import Municipality


@pytest.mark.django_db
@pytest.fixture
def space_resource_type():
    return ResourceType.objects.get_or_create(id="test_space", name="test_space", main_type="space")[0]


@pytest.mark.django_db
@pytest.fixture
def space_resource(space_resource_type):
    return Resource.objects.create(type=space_resource_type, authentication="none", name="resource")


@pytest.mark.django_db
@pytest.fixture
def test_unit():
    return Unit.objects.create(name="unit", time_zone='Europe/Helsinki')


@pytest.fixture
def generic_terms():
    return TermsOfUse.objects.create(
        name_fi='testikäyttöehdot',
        name_en='test terms of use',
        text_fi='kaikki on kielletty',
        text_en='everything is forbidden',
    )


@pytest.fixture
def payment_terms():
    return TermsOfUse.objects.create(
        name_fi='testimaksuehdot',
        name_en='test terms of payment',
        text_fi='kaikki on maksullista',
        text_en='everything is chargeable',
        terms_type=TermsOfUse.TERMS_TYPE_PAYMENT
    )


@pytest.mark.django_db
@pytest.fixture
def resource_in_unit(space_resource_type, test_unit, generic_terms, payment_terms):
    return Resource.objects.create(
        type=space_resource_type,
        authentication="none",
        name="resource in unit",
        unit=test_unit,
        max_reservations_per_user=1,
        max_period=datetime.timedelta(hours=2),
        reservable=True,
        generic_terms=generic_terms,
        payment_terms=payment_terms,
        specific_terms_fi='spesifiset käyttöehdot',
        specific_terms_en='specific terms of use',
        reservation_confirmed_notification_extra_en='this resource rocks'
    )


@pytest.mark.django_db
@pytest.fixture
def user():
    return get_user_model().objects.create(
        username='test_user',
        first_name='Cem',
        last_name='Kaner',
        email='cem@kaner.com',
        preferred_language='en'
    )


@pytest.mark.django_db
@pytest.fixture
def reservation(resource_in_unit, user):
    reservation = Reservation.objects.create(
        resource=resource_in_unit,
        begin='2015-04-04T09:00:00+02:00',
        end='2015-04-04T10:00:00+02:00',
        user=user,
        reserver_name='John Smith',
        state=Reservation.CONFIRMED
    )
    # Begin and end times remain as strings without refresh.
    # By refreshing will make item look like it comes from database (as it actually does).
    # Time comparisons in test do not work without this. In other fixtures this
    # extra step does not matter and it is skipped.
    reservation.refresh_from_db()

    return reservation
