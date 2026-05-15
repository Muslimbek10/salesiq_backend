from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "customer_type", "region", "phone", "email", "created_at")
    list_filter = ("customer_type", "region")
    search_fields = ("full_name", "email", "phone")
    ordering = ("full_name",)
