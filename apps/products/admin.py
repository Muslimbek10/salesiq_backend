from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "product_name", "sku", "category", "cost_price", "selling_price",
        "stock_quantity", "minimum_stock_level", "is_active", "is_low_stock",
    )
    list_filter = ("category", "is_active")
    search_fields = ("product_name", "sku")
    ordering = ("product_name",)
    list_select_related = ("category",)

    @admin.display(boolean=True, description="Low Stock?")
    def is_low_stock(self, obj):
        return obj.is_low_stock
