from django.contrib import admin

from .models import Sale


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "id", "product", "customer", "branch", "quantity",
        "unit_price", "total_amount", "total_profit", "sale_date",
    )
    list_filter = ("branch", "sale_date", "product__category")
    search_fields = ("product__product_name", "customer__full_name")
    ordering = ("-sale_date",)
    date_hierarchy = "sale_date"
    list_select_related = ("product", "customer", "branch")
    readonly_fields = ("total_amount", "total_cost", "total_profit", "created_at", "updated_at")
