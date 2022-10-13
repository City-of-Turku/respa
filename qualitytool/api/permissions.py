from rest_framework import permissions
from resources.auth import is_any_admin


class QualitytoolPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return super().has_permission(request, view) and is_any_admin(user)