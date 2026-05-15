from django.contrib import admin

from .models import Recommendation


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = (
        "priority_level", "recommendation_type", "related_entity_type",
        "related_entity_name", "is_active", "generated_at",
    )
    list_filter  = ("priority_level", "recommendation_type", "is_active", "related_entity_type")
    search_fields = ("recommendation_text", "related_entity_name")
    ordering      = ("-generated_at",)
    readonly_fields = ("generated_at", "dismissed_at")
    actions = ["dismiss_selected", "reactivate_selected"]

    @admin.action(description="Dismiss selected recommendations")
    def dismiss_selected(self, request, queryset):
        for rec in queryset.filter(is_active=True):
            rec.dismiss()

    @admin.action(description="Re-activate selected recommendations")
    def reactivate_selected(self, request, queryset):
        for rec in queryset.filter(is_active=False):
            rec.reactivate()
