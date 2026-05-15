"""
Products Filters
================
django-filter FilterSet for the product list endpoint.

Supported query parameters:
  category      → ?category=3              (FK lookup)
  is_active     → ?is_active=true          (boolean)
  stock_status  → ?stock_status=low        (custom filter)
  search        → ?search=laptop           (name + SKU text search via DRF SearchFilter)
  ordering      → ?ordering=selling_price  (via DRF OrderingFilter)
"""
import django_filters

from .models import Product


class ProductFilter(django_filters.FilterSet):
    # Filter by category FK
    category = django_filters.NumberFilter(
        field_name="category__id",
        lookup_expr="exact",
        label="Category ID",
    )

    # Boolean filter for active/inactive toggle
    is_active = django_filters.BooleanFilter(label="Is Active")

    # Custom stock status filter mapping to the model's StockStatus enum
    stock_status = django_filters.CharFilter(
        method="filter_stock_status",
        label="Stock Status (ok | low | out)",
    )

    # Price range filters
    min_price = django_filters.NumberFilter(
        field_name="selling_price",
        lookup_expr="gte",
        label="Minimum Selling Price",
    )
    max_price = django_filters.NumberFilter(
        field_name="selling_price",
        lookup_expr="lte",
        label="Maximum Selling Price",
    )

    class Meta:
        model  = Product
        fields = ["category", "is_active", "stock_status", "min_price", "max_price"]

    def filter_stock_status(self, queryset, name, value):
        """
        Custom filter that translates stock_status string into a DB query.
          ok  → stock_quantity > minimum_stock_level
          low → 0 < stock_quantity <= minimum_stock_level
          out → stock_quantity == 0
        """
        import django.db.models as models_module
        status = value.lower().strip()

        if status == "out":
            return queryset.filter(stock_quantity=0)

        if status == "low":
            return queryset.filter(
                stock_quantity__gt=0,
                stock_quantity__lte=models_module.F("minimum_stock_level"),
            )

        if status == "ok":
            return queryset.filter(
                stock_quantity__gt=models_module.F("minimum_stock_level")
            )

        return queryset  # Unknown status — return unfiltered
