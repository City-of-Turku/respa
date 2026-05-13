from django.contrib.auth.models import AnonymousUser

import pytest

from resources.enums import UnitGroupAuthorizationLevel
from resources.models import UnitGroup, UnitGroupAuthorization


@pytest.mark.django_db
def test_unit_group_str_and_is_admin_for_superuser(test_unit):
    group = UnitGroup.objects.create(name="Test group")
    group.members.add(test_unit)
    superuser = type("User", (), {"is_superuser": True, "is_authenticated": True, "is_general_admin": False})()
    assert str(group) == "Test group"
    assert group.is_admin(superuser) is True


@pytest.mark.django_db
def test_unit_group_is_admin_for_general_admin_and_authorized_user(general_admin, user, test_unit):
    group = UnitGroup.objects.create(name="Test group")
    group.members.add(test_unit)
    assert group.is_admin(general_admin) is True
    assert group.is_admin(user) is False

    UnitGroupAuthorization.objects.create(
        subject=group,
        authorized=user,
        level=UnitGroupAuthorizationLevel.admin,
    )
    assert group.is_admin(user) is True
    assert group.is_admin(AnonymousUser()) is False


@pytest.mark.django_db
def test_unit_group_authorization_queryset_helpers(user, user2, test_unit, test_unit2):
    group1 = UnitGroup.objects.create(name="Group 1")
    group2 = UnitGroup.objects.create(name="Group 2")
    group1.members.add(test_unit)
    group2.members.add(test_unit2)

    auth1 = UnitGroupAuthorization.objects.create(
        subject=group1,
        authorized=user,
        level=UnitGroupAuthorizationLevel.admin,
    )
    UnitGroupAuthorization.objects.create(
        subject=group2,
        authorized=user2,
        level=UnitGroupAuthorizationLevel.admin,
    )

    qs = UnitGroupAuthorization.objects.all()
    assert list(qs.for_user(user)) == [auth1]
    assert list(qs.to_unit_group(group1)) == [auth1]
    assert list(qs.to_unit(test_unit)) == [auth1]
    assert list(qs.admin_level()) != []


@pytest.mark.django_db
def test_unit_group_authorization_str(user, test_unit):
    group = UnitGroup.objects.create(name="Group for str")
    group.members.add(test_unit)
    auth = UnitGroupAuthorization.objects.create(
        subject=group,
        authorized=user,
        level=UnitGroupAuthorizationLevel.admin,
    )
    text = str(auth)
    assert "Group for str" in text
    assert str(auth.level) in text
    assert user.email in text
