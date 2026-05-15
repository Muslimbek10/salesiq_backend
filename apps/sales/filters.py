"""
Sales Filters
=============

SaleFilter
  Supports filtering by product, branch, customer, category, date range,
  and financial thresholds for the sales table and analytics queries.
"""
import django_filters

from .models import Sale


class SaleFilter(django_filters.FilterSet):
    # FK lookups
    product_id  = django_filters.NumberFilter(field_name="product_id")
    branch_id   = django_filters.NumberFilter(field_name="branch_id")
    customer_id = django_filters.NumberFilter(field_name="customer_id")

    # Traverse FK to filter by category
    category_id = django_filters.NumberFilter(field_name="product__category_id")

    # Date range
    date_from = django_filters.DateFilter(field_name="sale_date", lookup_expr="gte")
    date_to   = django_filters.DateFilter(field_name="sale_date", lookup_expr="lte")

    # Financial thresholds
    min_total  = django_filters.NumberFilter(field_name="total_amount", lookup_expr="gte")
    max_total  = django_filters.NumberFilter(field_name="total_amount", lookup_expr="lte")
    min_profit = django_filters.NumberFilter(field_name="total_profit", lookup_expr="gte")

    # Anonymous / identified customer filter
    is_walk_in = django_filters.BooleanFilter(method="filter_walk_in")

    class Meta:
        model  = Sale
        fields = [
            "product_id",
            "branch_id",
            "customer_id",
            "category_id",
            "date_from",
            "date_to",
            "min_total",
            "max_total",
            "min_profit",
            "is_walk_in",
        ]

    def filter_walk_in(self, queryset, name, value):
        """
        ?is_walk_in=true  → sales with no linked customer
        ?is_walk_in=false → sales with a linked customer
        """
        if value:
            return queryset.filter(customer_id__isnull=True)
        return queryset.filter(customer_id__isnull=False)
