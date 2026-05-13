from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

import pytest

from resources.enums import UnitAuthorizationLevel
from resources.models import Unit, UnitAuthorization, UnitIdentifier


def test_unit_import_flags_and_editable_status():
    unit = Unit(name="Unit", time_zone="Europe/Helsinki")
    assert unit.has_imported_data() is False
    assert unit.has_imported_hours() is False
    assert unit.is_editable() is True

    unit.data_source = "external-system"
    assert unit.has_imported_data() is True
    assert unit.is_editable() is False

    unit.data_source = ""
    unit.data_source_hours = "external-hours"
    assert unit.has_imported_hours() is True
    assert unit.is_editable() is False


def test_unit_get_tz_returns_timezone_object():
    unit = Unit(name="Unit", time_zone="Europe/Helsinki")
    tz = unit.get_tz()
    assert getattr(tz, "zone", None) == "Europe/Helsinki"


def test_unit_get_reservable_before_after_calls_helper(monkeypatch):
    calls = []

    def fake_create_datetime_days_from_now(value):
        calls.append(value)
        return f"value-{value}"

    monkeypatch.setattr("resources.models.unit.create_datetime_days_from_now", fake_create_datetime_days_from_now)
    unit = Unit(name="Unit", time_zone="Europe/Helsinki")
    unit.reservable_max_days_in_advance = 5
    unit.reservable_min_days_in_advance = 2

    assert unit.get_reservable_before() == "value-5"
    assert unit.get_reservable_after() == "value-2"
    assert calls == [5, 2]


@pytest.mark.django_db
def test_unit_queryset_managed_by_and_by_roles(user, general_admin):
    unit1 = Unit.objects.create(name="Unit 1", time_zone="Europe/Helsinki")
    unit2 = Unit.objects.create(name="Unit 2", time_zone="Europe/Helsinki")

    assert Unit.objects.managed_by(AnonymousUser()).count() == 0
    assert Unit.objects.by_roles(AnonymousUser(), [UnitAuthorizationLevel.admin]).count() == 0
    assert Unit.objects.by_roles(user, []).count() == 0

    managed = Unit.objects.managed_by(general_admin)
    assert unit1 in managed and unit2 in managed


@pytest.mark.django_db
def test_unit_queryset_by_roles_superuser_gets_all():
    Unit.objects.create(name="Unit 1", time_zone="Europe/Helsinki")
    Unit.objects.create(name="Unit 2", time_zone="Europe/Helsinki")
    superuser = get_user_model().objects.create(
        username="super_u",
        email="super@example.com",
        is_superuser=True,
        is_staff=True,
    )
    result = Unit.objects.by_roles(superuser, [UnitAuthorizationLevel.admin])
    assert result.count() >= 2


@pytest.mark.django_db
def test_unit_get_highest_authorization_level_for_user(user):
    unit = Unit.objects.create(name="Unit", time_zone="Europe/Helsinki")
    assert unit.get_highest_authorization_level_for_user(None) is None
    assert unit.get_highest_authorization_level_for_user(AnonymousUser()) is None

    superuser = get_user_model().objects.create(
        username="super_u_2",
        email="super2@example.com",
        is_superuser=True,
        is_staff=True,
    )
    assert unit.get_highest_authorization_level_for_user(superuser) == UnitAuthorizationLevel.admin

    unit.authorizations.create(authorized=user, level=UnitAuthorizationLevel.viewer)
    unit.authorizations.create(authorized=user, level=UnitAuthorizationLevel.manager)
    assert unit.get_highest_authorization_level_for_user(user) == UnitAuthorizationLevel.manager


@pytest.mark.django_db
def test_unit_authorization_queryset_helpers_and_comparisons(user, user2):
    unit1 = Unit.objects.create(name="Unit 1", time_zone="Europe/Helsinki")
    unit2 = Unit.objects.create(name="Unit 2", time_zone="Europe/Helsinki")
    viewer_auth = UnitAuthorization.objects.create(
        subject=unit1, authorized=user, level=UnitAuthorizationLevel.viewer
    )
    manager_auth = UnitAuthorization.objects.create(
        subject=unit1, authorized=user, level=UnitAuthorizationLevel.manager
    )
    UnitAuthorization.objects.create(
        subject=unit2, authorized=user2, level=UnitAuthorizationLevel.admin
    )

    qs = UnitAuthorization.objects.all()
    assert list(qs.for_user(user)) == [viewer_auth, manager_auth]
    assert list(qs.to_unit(unit1)) == [viewer_auth, manager_auth]
    assert list(qs.manager_level()) == [manager_auth]
    assert list(qs.at_least_manager_level()) != []
    assert manager_auth > viewer_auth
    assert viewer_auth < manager_auth
    assert manager_auth >= viewer_auth
    assert viewer_auth <= manager_auth


@pytest.mark.django_db
def test_unit_authorization_highest_per_user_and_ensure_lower_auth(user, user2):
    unit = Unit.objects.create(name="Unit", time_zone="Europe/Helsinki")
    auth_admin = UnitAuthorization.objects.create(
        subject=unit, authorized=user, level=UnitAuthorizationLevel.admin
    )
    auth_manager_user2 = UnitAuthorization.objects.create(
        subject=unit, authorized=user2, level=UnitAuthorizationLevel.manager
    )
    highest = UnitAuthorization.objects.highest_per_user()
    assert auth_admin in highest
    assert auth_manager_user2 in highest

    # Admin should ensure lower auth levels exist.
    auth_admin._ensure_lower_auth()
    levels = set(
        UnitAuthorization.objects.filter(subject=unit, authorized=user).values_list("level", flat=True)
    )
    assert UnitAuthorizationLevel.admin in levels
    assert UnitAuthorizationLevel.manager in levels
    assert UnitAuthorizationLevel.viewer in levels


@pytest.mark.django_db
def test_unit_authorization_str_and_unit_identifier_str(user):
    unit = Unit.objects.create(name="Unit for str", time_zone="Europe/Helsinki")
    auth = UnitAuthorization.objects.create(
        subject=unit, authorized=user, level=UnitAuthorizationLevel.admin
    )
    auth_text = str(auth)
    assert "Unit for str" in auth_text
    assert str(auth.level) in auth_text
    assert user.email in auth_text

    identifier = UnitIdentifier.objects.create(unit=unit, namespace="tprek", value="123")
    assert str(identifier) == "tprek: 123"
