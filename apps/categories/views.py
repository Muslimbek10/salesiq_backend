"""
Categories Views
================

CategoryViewSet
  Standard ModelViewSet providing list, create, retrieve, update, destroy.
  Permissions: read for all authenticated users, write for Admin/Manager only.

  Custom actions:
    dropdown (GET /api/categories/dropdown/) — unpaginated list of id + name pairs
    used by product forms and filter components in the frontend.
"""
import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdminOrManager

from .models import Category
from .serializers import CategoryDropdownSerializer, CategorySerializer

logger = logging.getLogger(__name__)


class CategoryViewSet(ModelViewSet):
    """
    list:    GET  /api/categories/          → paginated list (all authenticated users)
    create:  POST /api/categories/          → Admin / Manager only
    retrieve:GET  /api/categories/{id}/     → all authenticated users
    update:  PUT  /api/categories/{id}/     → Admin / Manager only
    destroy: DELETE /api/categories/{id}/   → Admin only

    Custom:
    dropdown:GET  /api/categories/dropdown/ → id + name list, no pagination
    """
    queryset         = Category.objects.all()
    serializer_class = CategorySerializer
    search_fields    = ["category_name", "description"]
    ordering_fields  = ["category_name", "created_at"]
    ordering         = ["category_name"]

    def get_permissions(self):
        """
        Read operations: any authenticated user.
        Create / update: Admin or Manager.
        Destroy: Admin only.
        """
        if self.action == "destroy":
            return [IsAdminOrManager()]     # Managers can delete categories (with PROTECT guard)
        if self.action in ("create", "update", "partial_update"):
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """
        Annotate with product counts to avoid N+1 on list endpoint.
        The CategorySerializer reads annotated values when available.
        """
        from django.db.models import Count, Q
        return Category.objects.annotate(
            annotated_product_count=Count("products"),
            annotated_active_product_count=Count(
                "products",
                filter=Q(products__is_active=True),
            ),
        ).order_by("category_name")

    def get_serializer_class(self):
        if self.action == "dropdown":
            return CategoryDropdownSerializer
        return CategorySerializer

    def destroy(self, request, *args, **kwargs):
        """
        Override destroy to provide a clear error message when the category
        has linked products (Django's PROTECT raises ProtectedError).
        """
        from django.db.models import ProtectedError
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    "error": True,
                    "message": (
                        "Cannot delete this category because it has products assigned to it. "
                        "Reassign or deactivate all products first."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

    @action(detail=False, methods=["get"], url_path="dropdown", pagination_class=None)
    def dropdown(self, request):
        """
        GET /api/categories/dropdown/
        Returns all categories as a flat id+name list — no pagination.
        Used by product create/edit forms and category filter dropdowns.
        """
        categories = Category.objects.all().order_by("category_name")
        serializer = CategoryDropdownSerializer(categories, many=True)
        return Response(serializer.data)
