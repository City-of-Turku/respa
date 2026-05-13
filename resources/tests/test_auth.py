import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser

from resources.auth import (
    has_any_auth_equal_or_higher,
    has_any_auth_higher,
    has_api_permission,
    has_auth_level,
    has_permission,
    is_any_admin,
    is_any_manager,
    is_general_admin,
    is_overage,
    is_staff,
    is_superuser,
    is_underage,
    is_unit_admin,
    is_unit_manager,
    is_unit_viewer,
)
from resources.enums import UnitAuthorizationLevel, UnitGroupAuthorizationLevel
from resources.models import UnitGroup


@pytest.mark.django_db
def test_basic_user_role_helpers(user, staff_user, general_admin):
    assert is_superuser(user) is False
    assert is_superuser(SimpleNamespace(is_authenticated=True, is_superuser=True)) is True

    assert is_staff(user) is False
    assert is_staff(staff_user) is True

    assert is_general_admin(user) is False
    assert is_general_admin(general_admin) is True
    assert is_general_admin(SimpleNamespace(is_authenticated=True, is_superuser=True, is_general_admin=False)) is True


@pytest.mark.django_db
def test_auth_level_helpers_for_unit_authorizations(user, test_unit):
    assert has_any_auth_equal_or_higher(user, UnitAuthorizationLevel.viewer) is False
    assert has_any_auth_higher(user, UnitAuthorizationLevel.viewer) is False

    user.unit_authorizations.create(subject=test_unit, level=UnitAuthorizationLevel.manager)
    assert has_any_auth_equal_or_higher(user, UnitAuthorizationLevel.viewer) is True
    assert has_any_auth_equal_or_higher(user, UnitAuthorizationLevel.manager) is True
    assert has_any_auth_higher(user, UnitAuthorizationLevel.viewer) is True
    assert has_any_auth_higher(user, UnitAuthorizationLevel.manager) is False


@pytest.mark.django_db
def test_has_auth_level_matches_group_or_unit(user, test_unit):
    group = UnitGroup.objects.create(name="test group")
    group.members.add(test_unit)

    assert has_auth_level(user, UnitAuthorizationLevel.admin) is False
    assert has_auth_level(user, UnitGroupAuthorizationLevel.admin) is False

    user.unit_group_authorizations.create(subject=group, level=UnitGroupAuthorizationLevel.admin)
    assert has_auth_level(user, UnitGroupAuthorizationLevel.admin) is True

    user.unit_authorizations.create(subject=test_unit, level=UnitAuthorizationLevel.admin)
    assert has_auth_level(user, UnitAuthorizationLevel.admin) is True


@pytest.mark.django_db
def test_any_admin_and_manager_helpers(user, test_unit):
    assert is_any_admin(user) is False
    assert is_any_manager(user) is False

    user.unit_authorizations.create(subject=test_unit, level=UnitAuthorizationLevel.manager)
    assert is_any_manager(user) is True
    assert is_any_admin(user) is False

    user.unit_authorizations.create(subject=test_unit, level=UnitAuthorizationLevel.admin)
    assert is_any_admin(user) is True


@pytest.mark.django_db
def test_underage_and_overage_helpers(user, staff_user):
    today = datetime.date.today()
    user.birthdate = today - datetime.timedelta(days=int(15 * 365.25))
    user.save(update_fields=["birthdate"])
    assert is_underage(user, 18) is True
    assert is_overage(user, 18) is False

    user.birthdate = today - datetime.timedelta(days=int(30 * 365.25))
    user.save(update_fields=["birthdate"])
    assert is_underage(user, 18) is False
    assert is_overage(user, 18) is True

    # staff users are excluded from age checks
    assert is_underage(staff_user, 18) is False
    assert is_overage(staff_user, 18) is False
    assert is_underage(AnonymousUser(), 18) is False
    assert is_overage(AnonymousUser(), 18) is False


@pytest.mark.django_db
def test_underage_overage_handles_age_errors(user):
    user.birthdate = None
    assert is_underage(user, 18) is False
    assert is_overage(user, 18) is False


def test_permission_helpers():
    user = SimpleNamespace(
        is_authenticated=True,
        get_all_permissions=lambda: {"resources:api:read", "resources.unit:api:list"},
    )
    assert has_permission(user, "resources:api:read") is True
    assert has_permission(user, "resources:api:write") is False
    assert has_api_permission(user, "unit", "list") is True
    assert has_api_permission(user, "unit", "create") is False
    assert has_api_permission(user, "unit", "list", app="resources") is True
    assert has_api_permission(SimpleNamespace(is_authenticated=False, get_all_permissions=lambda: set()), "unit", "list") is False


def test_unit_authorization_helpers_for_unit_and_group():
    unit = SimpleNamespace(id="u1")
    other_unit = SimpleNamespace(id="u2")
    group_admin_auth = SimpleNamespace(
        level=UnitGroupAuthorizationLevel.admin,
        subject=SimpleNamespace(members=SimpleNamespace(all=lambda: [unit])),
    )
    group_non_match_auth = SimpleNamespace(
        level=UnitGroupAuthorizationLevel.admin,
        subject=SimpleNamespace(members=SimpleNamespace(all=lambda: [other_unit])),
    )
    unit_admin_auth = SimpleNamespace(subject=unit, level=UnitAuthorizationLevel.admin)
    unit_manager_auth = SimpleNamespace(subject=unit, level=UnitAuthorizationLevel.manager)
    unit_viewer_auth = SimpleNamespace(subject=unit, level=UnitAuthorizationLevel.viewer)

    assert is_unit_admin([], [group_non_match_auth], unit) is False
    assert is_unit_admin([], [group_admin_auth], unit) is True
    assert is_unit_admin([unit_admin_auth], [], unit) is True

    assert is_unit_manager([unit_manager_auth], unit) is True
    assert is_unit_manager([unit_viewer_auth], unit) is False
    assert is_unit_viewer([unit_viewer_auth], unit) is True
    assert is_unit_viewer([unit_manager_auth], unit) is False
