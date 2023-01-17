from django.contrib.auth.models import AnonymousUser
from .enums import UnitGroupAuthorizationLevel, UnitAuthorizationLevel

def is_authenticated_user(user):
    return bool(user and user.is_authenticated)


def is_superuser(user):
    return is_authenticated_user(user) and user.is_superuser


def is_general_admin(user):
    return is_authenticated_user(user) and (
        user.is_superuser or getattr(user, 'is_general_admin', False))


def is_staff(user):
    return is_authenticated_user(user) and user.is_staff

def has_auth_level(user, level):
    if not is_authenticated_user(user):
        return False

    group_authorizations = user.unit_group_authorizations.all()
    authorizations = user.unit_authorizations.all()

    group_level = any(group_auth.level == level for group_auth in group_authorizations)
    unit_level = any(auth.level == level for auth in authorizations)

    return group_level or unit_level

def is_any_admin(user):
    if not is_authenticated_user(user):
        return False
    return is_general_admin(user) \
        or has_auth_level(user, UnitAuthorizationLevel.admin) \
        or has_auth_level(user, UnitGroupAuthorizationLevel.admin)

def is_any_manager(user):
    if not is_authenticated_user(user):
        return False
    return has_auth_level(user, UnitAuthorizationLevel.manager)

def is_underage(user, age):
    try:
        if isinstance(user, AnonymousUser):
            return False
        else:
            if is_staff(user):
                return False
            return user.get_user_age() < age
    except Exception as ex:
        return False


def is_overage(user, age):
    try:
        if isinstance(user, AnonymousUser):
            return False
        else:
            if is_staff(user):
                return False
            return user.get_user_age() > age
    except:
        return False

def is_unit_admin(unit_authorizations, unit_group_authorizations, unit):
    is_admin = False

    for group_auth in filter(lambda group_auth: group_auth.level == UnitGroupAuthorizationLevel.admin, unit_group_authorizations):
        if any(member_unit == unit for member_unit in group_auth.subject.members.all()):
            is_admin = True

    if any(auth.subject == unit and auth.level == UnitAuthorizationLevel.admin for auth in unit_authorizations):
        is_admin = True

    return is_admin


def is_unit_manager(unit_authorizations, unit):
    return any(auth.subject == unit and auth.level == UnitAuthorizationLevel.manager for auth in unit_authorizations)


def is_unit_viewer(unit_authorizations, unit):
    return any(auth.subject == unit and auth.level == UnitAuthorizationLevel.viewer for auth in unit_authorizations)


def has_permission(user, permission):
    return is_authenticated_user(user) and permission in user.get_all_permissions()

def has_api_permission(user, scope, permission, **kwargs):
    return is_authenticated_user(user) and \
        has_permission(user, '{app}.{scope}:api:{permission}' \
            .format(app=kwargs.get('app', 'resources'), scope=scope, permission=permission))
