from django.contrib import admin

from .models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("category_name", "description", "created_at")
    search_fields = ("category_name",)
    ordering = ("category_name",)
