# vendors/permissions.py
from rest_framework import permissions


class IsSuperAdmin(permissions.BasePermission):
    """
    केवल Django superuser ही इन endpoints को access कर सकता है
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.is_superuser and
            request.user.is_active
        )


class IsVendor(permissions.BasePermission):
    """
    पहले से मौजूद permission (vendor के लिए)
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.is_vendor
            and hasattr(request.user, 'vendor_profile')
            and request.user.vendor_profile.is_approved
        )