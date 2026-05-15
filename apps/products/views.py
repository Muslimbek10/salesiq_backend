"""
Products Views
==============

ProductViewSet
  Full CRUD plus two custom actions:

  low_stock  (GET /api/products/low_stock/)
    Returns products where stock_quantity <= minimum_stock_level.
    Used by the dashboard low-stock widget and the alert engine.

  toggle_active (POST /api/products/{id}/toggle_active/)
    Flips is_active without requiring a full PUT body.
    Managers and Admins can activate or deactivate a product.

  dropdown (GET /api/products/dropdown/)
    Unpaginated list of active products for the sale form select.
"""
import logging

from django.db import models as django_models
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdminOrManager

from .filters import ProductFilter
from .models import Product
from .serializers import (
    ProductCreateUpdateSerializer,
    ProductDetailSerializer,
    ProductDropdownSerializer,
    ProductListSerializer,
)

logger = logging.getLogger(__name__)


class ProductViewSet(ModelViewSet):
    """
    list:    GET    /api/products/
    create:  POST   /api/products/
    retrieve:GET    /api/products/{id}/
    update:  PUT    /api/products/{id}/
    partial: PATCH  /api/products/{id}/
    destroy: DELETE /api/products/{id}/

    Custom:
    low_stock:     GET  /api/products/low_stock/
    toggle_active: POST /api/products/{id}/toggle_active/
    dropdown:      GET  /api/products/dropdown/
    """
    filterset_class = ProductFilter
    search_fields   = ["product_name", "sku"]
    ordering_fields = ["product_name", "selling_price", "stock_quantity", "created_at"]
    ordering        = ["product_name"]

    def get_queryset(self):
        """
        Always eager-load category to prevent N+1 on list views.
        Annotate with sales totals when the detail view requests them.
        """
        return (
            Product.objects
            .select_related("category")
            .order_by("product_name")
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProductCreateUpdateSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        if self.action == "dropdown":
            return ProductDropdownSerializer
        return ProductListSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "toggle_active"):
            return [IsAdminOrManager()]
        if self.action == "destroy":
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        """
        Block deletion of products that have sales records (PROTECT FK).
        Provide a clear business message instead of a raw 500.
        """
        from django.db.models import ProtectedError
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    "error": True,
                    "message": (
                        "Cannot delete this product because it has sales records. "
                        "Deactivate it instead to hide it from new sales."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

    # ------------------------------------------------------------------
    # Custom actions
    # ------------------------------------------------------------------

    @action(detail=False, methods=["get"], url_path="low_stock")
    def low_stock(self, request):
        """
        GET /api/products/low_stock/
        Returns all products where stock_quantity <= minimum_stock_level,
        ordered by urgency (out-of-stock first, then lowest remaining stock).
        """
        queryset = (
            self.get_queryset()
            .filter(
                stock_quantity__lte=django_models.F("minimum_stock_level")
            )
            .annotate(
                shortage=django_models.F("minimum_stock_level") - django_models.F("stock_quantity")
            )
            .order_by("stock_quantity", "-shortage")
        )

        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductListSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(queryset, many=True, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="toggle_active", permission_classes=[IsAdminOrManager])
    def toggle_active(self, request, pk=None):
        """
        POST /api/products/{id}/toggle_active/
        Flips is_active for the product.
        Returns the updated product record.
        """
        product = self.get_object()
        product.is_active = not product.is_active
        product.save(update_fields=["is_active", "updated_at"])

        action_taken = "activated" if product.is_active else "deactivated"
        logger.info(
            "Product '%s' (id=%s) %s by user '%s'.",
            product.product_name, product.pk, action_taken, request.user.username,
        )

        return Response(
            {
                "message": f"Product '{product.product_name}' has been {action_taken}.",
                "is_active": product.is_active,
                "product": ProductListSerializer(product, context=self.get_serializer_context()).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False, methods=["get"], url_path="dropdown",
        pagination_class=None, permission_classes=[IsAuthenticated],
    )
    def dropdown(self, request):
        """
        GET /api/products/dropdown/
        Returns all active products with id, name, sku, selling_price, stock_quantity.
        No pagination. Used to populate the sale create/edit form product select.
        """
        queryset = (
            Product.objects
            .filter(is_active=True)
            .order_by("product_name")
        )
        serializer = ProductDropdownSerializer(queryset, many=True)
        return Response(serializer.data)
