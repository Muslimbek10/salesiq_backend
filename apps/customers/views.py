"""
Customers Views
===============

CustomerViewSet
  Standard ModelViewSet with role-based permissions and queryset annotation.
  The queryset is annotated with purchase stats so list serializer fields
  resolve without extra per-row queries.

Custom actions:
  dropdown (GET /api/customers/dropdown/)
    Unpaginated id + name list for the sale form customer select.

  purchase_history (GET /api/customers/{id}/purchase_history/)
    Returns the customer's last N sales with product and branch details.
    Used by the customer detail drawer on the Customers page.
"""
import logging

from django.db.models import Count, Max, Sum
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdminOrManager

from .filters import CustomerFilter
from .models import Customer
from .serializers import (
    CustomerCreateUpdateSerializer,
    CustomerDetailSerializer,
    CustomerDropdownSerializer,
    CustomerListSerializer,
)

logger = logging.getLogger(__name__)


class CustomerViewSet(ModelViewSet):
    """
    list:     GET    /api/customers/
    create:   POST   /api/customers/
    retrieve: GET    /api/customers/{id}/
    update:   PUT    /api/customers/{id}/
    partial:  PATCH  /api/customers/{id}/
    destroy:  DELETE /api/customers/{id}/

    Custom:
    dropdown:         GET  /api/customers/dropdown/
    purchase_history: GET  /api/customers/{id}/purchase_history/
    """
    filterset_class = CustomerFilter
    search_fields   = ["full_name", "email", "phone", "region"]
    ordering_fields = ["full_name", "customer_type", "region", "created_at"]
    ordering        = ["full_name"]

    def get_queryset(self):
        """
        Annotate with purchase stats to avoid N+1 on the list endpoint.
        The CustomerListSerializer reads annotated values via SerializerMethodField.
        """
        return (
            Customer.objects
            .annotate(
                total_purchases_ann=Count("sales"),
                total_spent_ann=Sum("sales__total_amount"),
                last_purchase_ann=Max("sales__sale_date"),
            )
            .order_by("full_name")
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CustomerCreateUpdateSerializer
        if self.action == "retrieve":
            return CustomerDetailSerializer
        if self.action == "dropdown":
            return CustomerDropdownSerializer
        return CustomerListSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [IsAdminOrManager()]
        if self.action == "destroy":
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        """
        Customers are SET_NULL on sales — deletion is allowed.
        We still log it for auditability.
        """
        customer = self.get_object()
        name = customer.full_name
        customer.delete()
        logger.info(
            "Customer '%s' (id=%s) deleted by user '%s'.",
            name, customer.pk, request.user.username,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # Custom actions
    # ------------------------------------------------------------------

    @action(
        detail=False, methods=["get"], url_path="dropdown",
        pagination_class=None, permission_classes=[IsAuthenticated],
    )
    def dropdown(self, request):
        """
        GET /api/customers/dropdown/
        Returns all customers as id + full_name + customer_type.
        No pagination. Used to populate the sale form customer select.
        """
        queryset = Customer.objects.all().order_by("full_name")
        serializer = CustomerDropdownSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="purchase_history")
    def purchase_history(self, request, pk=None):
        """
        GET /api/customers/{id}/purchase_history/
        Returns the most recent 50 sales for this customer,
        with product name and branch name included.
        Used in the customer detail drawer on the Customers page.
        """
        from apps.sales.models import Sale
        from apps.sales.serializers import SaleListSerializer

        customer = self.get_object()

        sales = (
            Sale.objects
            .filter(customer=customer)
            .select_related("product", "product__category", "branch")
            .order_by("-sale_date")[:50]
        )

        serializer = SaleListSerializer(
            sales, many=True, context=self.get_serializer_context()
        )
        return Response({
            "customer_id":   customer.pk,
            "customer_name": customer.full_name,
            "total_records": customer.sales.count(),
            "results":       serializer.data,
        })
