"""
Sales Views
===========

SaleViewSet
  Full CRUD for sales records.

  list     — paginated, filterable, select_related for flat serializer
  create   — uses SaleCreateSerializer; signals decrement stock
  retrieve — uses SaleDetailSerializer (nested)
  update   — uses SaleUpdateSerializer; signals reconcile stock delta
  destroy  — signals restore stock via post_delete

Custom actions:
  export (GET /api/sales/export/)
    Returns a streaming CSV of the current filtered queryset.
    Applies the same SaleFilter as the list view.
    Skips pagination so all matching rows are included.

  summary (GET /api/sales/summary/)
    Returns aggregate totals for the current filtered queryset.
    Used by the dashboard KPI cards.
"""
import csv
import logging

from django.http import StreamingHttpResponse
from django.utils import timezone
from django.db.models import Count, Sum
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdminOrManager

from .filters import SaleFilter
from .models import Sale
from .serializers import (
    SaleCreateSerializer,
    SaleDetailSerializer,
    SaleListSerializer,
    SaleUpdateSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CSV streaming helper
# ---------------------------------------------------------------------------

class _EchoBuffer:
    """Minimal write buffer that returns the value written (for StreamingHttpResponse)."""
    def write(self, value):
        return value


def _stream_sales_csv(queryset):
    """
    Generator that yields CSV rows one at a time.
    select_related is already applied on the incoming queryset.
    """
    buffer = _EchoBuffer()
    writer = csv.writer(buffer)

    # Header
    yield writer.writerow([
        "ID", "Sale Date", "Product", "SKU", "Category",
        "Customer", "Branch",
        "Quantity", "Unit Price", "Total Amount", "Total Cost", "Total Profit",
    ])

    for sale in queryset.iterator(chunk_size=500):
        customer_name = (
            sale.customer.full_name if sale.customer_id and sale.customer else "Walk-in"
        )
        yield writer.writerow([
            sale.pk,
            sale.sale_date.isoformat(),
            sale.product.product_name,
            sale.product.sku,
            sale.product.category.category_name,
            customer_name,
            sale.branch.branch_name,
            sale.quantity,
            sale.unit_price,
            sale.total_amount,
            sale.total_cost,
            sale.total_profit,
        ])


# ---------------------------------------------------------------------------
# ViewSet
# ---------------------------------------------------------------------------

class SaleViewSet(ModelViewSet):
    """
    list:     GET    /api/sales/
    create:   POST   /api/sales/
    retrieve: GET    /api/sales/{id}/
    update:   PUT    /api/sales/{id}/
    partial:  PATCH  /api/sales/{id}/
    destroy:  DELETE /api/sales/{id}/

    Custom:
    export:   GET  /api/sales/export/
    summary:  GET  /api/sales/summary/
    """
    filterset_class = SaleFilter
    search_fields   = [
        "product__product_name",
        "product__sku",
        "customer__first_name",
        "customer__last_name",
        "branch__branch_name",
    ]
    ordering_fields = [
        "sale_date", "total_amount", "total_profit",
        "quantity", "created_at",
    ]
    ordering = ["-sale_date"]

    def get_queryset(self):
        return (
            Sale.objects
            .select_related("product", "product__category", "customer", "branch")
            .order_by("-sale_date", "-created_at")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return SaleCreateSerializer
        if self.action in ("update", "partial_update"):
            return SaleUpdateSerializer
        if self.action == "retrieve":
            return SaleDetailSerializer
        return SaleListSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        sale = serializer.save()
        logger.info(
            "Sale created: id=%s product='%s' qty=%s by user='%s'.",
            sale.pk, sale.product.product_name, sale.quantity,
            self.request.user.username,
        )

    def perform_update(self, serializer):
        sale = serializer.save()
        logger.info(
            "Sale updated: id=%s by user='%s'.",
            sale.pk, self.request.user.username,
        )

    def perform_destroy(self, instance):
        sale_id      = instance.pk
        product_name = instance.product.product_name
        instance.delete()
        logger.info(
            "Sale deleted: id=%s product='%s' by user='%s'.",
            sale_id, product_name, self.request.user.username,
        )

    # ------------------------------------------------------------------
    # Custom actions
    # ------------------------------------------------------------------

    @action(
        detail=False, methods=["get"], url_path="export",
        permission_classes=[IsAdminOrManager],
        pagination_class=None,
    )
    def export(self, request):
        """
        GET /api/sales/export/
        Streams the filtered sales queryset as a CSV file.
        Accepts the same query params as the list view (SaleFilter).
        """
        queryset = self.filter_queryset(self.get_queryset())

        filename  = f"sales_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response  = StreamingHttpResponse(
            streaming_content=_stream_sales_csv(queryset),
            content_type="text/csv",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        logger.info(
            "Sales CSV export initiated by user='%s' (%d rows).",
            request.user.username, queryset.count(),
        )
        return response

    @action(
        detail=False, methods=["get"], url_path="summary",
        permission_classes=[IsAuthenticated],
        pagination_class=None,
    )
    def summary(self, request):
        """
        GET /api/sales/summary/
        Returns aggregate KPI totals for the filtered queryset.
        Accepts the same query params as the list view (SaleFilter).

        Response:
          {
            "total_revenue":      float,
            "total_profit":       float,
            "total_cost":         float,
            "total_transactions": int,
            "total_units_sold":   int,
          }
        """
        queryset = self.filter_queryset(self.get_queryset())
        totals   = queryset.aggregate(
            total_revenue=Sum("total_amount"),
            total_profit=Sum("total_profit"),
            total_cost=Sum("total_cost"),
            total_transactions=Count("id"),
            total_units_sold=Sum("quantity"),
        )

        return Response({
            "total_revenue":      float(totals["total_revenue"]      or 0),
            "total_profit":       float(totals["total_profit"]       or 0),
            "total_cost":         float(totals["total_cost"]         or 0),
            "total_transactions": totals["total_transactions"]       or 0,
            "total_units_sold":   totals["total_units_sold"]         or 0,
        })
