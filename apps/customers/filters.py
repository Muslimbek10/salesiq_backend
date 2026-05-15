"""
Customers Filters
=================
Supported query parameters:
  customer_type → ?customer_type=VIP
  region        → ?region=North       (case-insensitive)
  is_high_value → ?is_high_value=true (VIP + Corporate combined)
  is_dormant    → ?is_dormant=true    (no purchase in 60+ days)
  search        → ?search=john        (full_name + email + phone via SearchFilter)
"""
from datetime import timedelta

import django_filters
from django.utils import timezone

from .models import Customer


class CustomerFilter(django_filters.FilterSet):
    customer_type = django_filters.ChoiceFilter(
        choices=Customer.CustomerType.choices,
        label="Customer Type",
    )
    region = django_filters.CharFilter(
        field_name="region",
        lookup_expr="iexact",
        label="Region (case-insensitive exact match)",
    )
    is_high_value = django_filters.BooleanFilter(
        method="filter_high_value",
        label="VIP and Corporate customers only",
    )
    is_dormant = django_filters.BooleanFilter(
        method="filter_dormant",
        label="Customers with no purchase in 60+ days",
    )

    class Meta:
        model  = Customer
        fields = ["customer_type", "region", "is_high_value", "is_dormant"]

    def filter_high_value(self, queryset, name, value):
        if value:
            return queryset.filter(
                customer_type__in=[
                    Customer.CustomerType.VIP,
                    Customer.CustomerType.CORPORATE,
                ]
            )
        return queryset

    def filter_dormant(self, queryset, name, value):
        cutoff = timezone.now().date() - timedelta(days=60)
        if value:
            # Customers whose last purchase was before the cutoff, or who never purchased
            from django.db.models import Max, Q
            return queryset.annotate(
                last_sale=Max("sales__sale_date")
            ).filter(
                Q(last_sale__lt=cutoff) | Q(last_sale__isnull=True)
            )
        return queryset
