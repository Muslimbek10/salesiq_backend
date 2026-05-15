"""
Role-Based Permission Classes
Used by all ViewSets to enforce the Admin / Manager / Analyst hierarchy.

Role hierarchy (highest to lowest):
    admin    → full access to all resources and all actions
    manager  → CRUD on business data; no user management
    analyst  → read-only on most resources; full access to analytics/forecasting

Usage in ViewSets:
    from core.permissions import IsAdminOrManager

    class ProductViewSet(ModelViewSet):
        def get_permissions(self):
            if self.action in ['create', 'update', 'partial_update', 'destroy']:
                return [IsAdminOrManager()]
            return [IsAuthenticated()]
"""
from rest_framework.permissions import BasePermission, IsAuthenticated  # noqa: F401


class IsAdmin(BasePermission):
    """
    Grants access only to users with role='admin'.
    Used for destructive or user-management operations.
    """
    message = "This action requires administrator privileges."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
        )


class IsAdminOrManager(BasePermission):
    """
    Grants access to admin and manager roles.
    Used for create, update, and delete on all business data.
    """
    message = "This action requires manager or administrator privileges."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ("admin", "manager")
        )


class IsAnalyst(BasePermission):
    """
    Grants access to all authenticated users (admin, manager, analyst).
    Used as a semantic alias for IsAuthenticated — makes ViewSet intent explicit.
    """
    message = "Authentication required."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ("admin", "manager", "analyst")
        )
