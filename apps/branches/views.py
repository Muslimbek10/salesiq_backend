"""
Branches Views
==============

BranchViewSet
  Standard ModelViewSet with revenue/profit annotation on every queryset.

Custom actions:
  toggle_active (POST /api/branches/{id}/toggle_active/)
    Activates or deactivates a branch without a full PUT body.

  dropdown (GET /api/branches/dropdown/)
    Unpaginated list for sale form and filter selects.
"""
import logging

from django.db.models import Count, ProtectedError, Sum
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdminOrManager

from .models import Branch
from .serializers import (
    BranchCreateUpdateSerializer,
    BranchDetailSerializer,
    BranchDropdownSerializer,
    BranchListSerializer,
)

logger = logging.getLogger(__name__)


class BranchViewSet(ModelViewSet):
    """
    list:     GET    /api/branches/
    create:   POST   /api/branches/
    retrieve: GET    /api/branches/{id}/
    update:   PUT    /api/branches/{id}/
    partial:  PATCH  /api/branches/{id}/
    destroy:  DELETE /api/branches/{id}/

    Custom:
    toggle_active: POST /api/branches/{id}/toggle_active/
    dropdown:      GET  /api/branches/dropdown/
    """
    search_fields   = ["branch_name", "location", "manager_name"]
    ordering_fields = ["branch_name", "location", "created_at"]
    ordering        = ["branch_name"]

    def get_queryset(self):
        """
        Annotate with lifetime revenue, profit, and transaction count
        to populate the branch list table without N+1 queries.
        """
        return (
            Branch.objects
            .annotate(
                ann_revenue=Sum("sales__total_amount"),
                ann_profit=Sum("sales__total_profit"),
                ann_transactions=Count("sales"),
            )
            .order_by("branch_name")
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return BranchCreateUpdateSerializer
        if self.action == "retrieve":
            return BranchDetailSerializer
        if self.action == "dropdown":
            return BranchDropdownSerializer
        return BranchListSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "toggle_active"):
            return [IsAdminOrManager()]
        if self.action == "destroy":
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        """Block deletion of branches that have sales records (PROTECT FK)."""
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    "error": True,
                    "message": (
                        "Cannot delete this branch because it has sales records. "
                        "Deactivate it instead to hide it from new sales."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

    # ------------------------------------------------------------------
    # Custom actions
    # ------------------------------------------------------------------

    @action(
        detail=True, methods=["post"], url_path="toggle_active",
        permission_classes=[IsAdminOrManager],
    )
    def toggle_active(self, request, pk=None):
        """
        POST /api/branches/{id}/toggle_active/
        Flips is_active for the branch.
        """
        branch = self.get_object()
        branch.is_active = not branch.is_active
        branch.save(update_fields=["is_active", "updated_at"])

        action_taken = "activated" if branch.is_active else "deactivated"
        logger.info(
            "Branch '%s' (id=%s) %s by user '%s'.",
            branch.branch_name, branch.pk, action_taken, request.user.username,
        )

        return Response(
            {
                "message":   f"Branch '{branch.branch_name}' has been {action_taken}.",
                "is_active": branch.is_active,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False, methods=["get"], url_path="dropdown",
        pagination_class=None, permission_classes=[IsAuthenticated],
    )
    def dropdown(self, request):
        """
        GET /api/branches/dropdown/
        Returns all branches (active + inactive) for form selects.
        Active-first ordering so the most useful entries appear first.
        """
        queryset = Branch.objects.all().order_by("-is_active", "branch_name")
        serializer = BranchDropdownSerializer(queryset, many=True)
        return Response(serializer.data)
