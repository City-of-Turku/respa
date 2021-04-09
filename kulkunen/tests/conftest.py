import pytest
from django.utils.module_loading import import_string
from pytz import UTC

from kulkunen import models as kulkunen_models
from kulkunen.models import AccessControlResource, AccessControlSystem, AccessControlGrant, AccessControlUser
from resources.models.reservation import Reservation
from resources.tests.conftest import *  # noqa


@pytest.fixture
def test_driver(monkeypatch):
    for drv in kulkunen_models.DRIVERS:
        if drv[0] == 'test':
            break
    else:
        drivers = kulkunen_models.DRIVERS + (('test', 'Test driver', 'kulkunen.tests.driver.TestDriver'),)
        monkeypatch.setattr(kulkunen_models, 'DRIVERS', drivers)
        drv = drivers[-1]

    return import_string(drv[2])


@pytest.fixture
def ac_system(test_driver):
    return AccessControlSystem.objects.create(
        name='test acs',
        driver='test',
    )


@pytest.fixture
def ac_resource(ac_system, resource_in_unit):
    return AccessControlResource.objects.create(
        system=ac_system, resource=resource_in_unit
    )


@pytest.mark.django_db
@pytest.fixture()
def reservation(resource_in_unit, user):
    """reservation fixture with access code set to None"""
    return Reservation.objects.create(
        resource=resource_in_unit,
        begin=datetime.datetime(2119, 5, 5, 10, 0, 0, tzinfo=UTC),
        end=datetime.datetime(2119, 5, 5, 12, 0, 0, tzinfo=UTC),
        user=user,
        reserver_name='Testi Testaaja',
        state=Reservation.CONFIRMED,
        access_code=None
    )

@pytest.mark.django_db
@pytest.fixture()
def ac_user(ac_system, user):
    return AccessControlUser.objects.create(
        system=ac_system,
        user=user,
    )

@pytest.mark.django_db
@pytest.fixture()
def ac_grant(ac_resource, ac_user, reservation):
    return AccessControlGrant.objects.create(
        state=AccessControlGrant.REQUESTED,
        user=ac_user,
        resource=ac_resource,
        reservation=reservation,
        starts_at=reservation.begin,
        ends_at=reservation.end,
    )
