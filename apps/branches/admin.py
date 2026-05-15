from django.contrib import admin

from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("branch_name", "location", "manager_name", "created_at")
    search_fields = ("branch_name", "location", "manager_name")
    ordering = ("branch_name",)
