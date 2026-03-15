# customers/permissions.py  (या common/permissions.py में रख सकते हैं)
from rest_framework import permissions

class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.is_superuser and
            request.user.is_active
        )