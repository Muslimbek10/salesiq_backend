from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display  = (
        "alert_type", "priority_level", "related_entity_type",
        "related_entity_name", "is_active", "created_at",
    )
    list_filter   = ("alert_type", "priority_level", "is_active", "related_entity_type")
    search_fields = ("alert_message", "related_entity_name")
    ordering      = ("-created_at",)
    readonly_fields = ("created_at", "dismissed_at")
    actions = ["dismiss_selected", "reactivate_selected"]

    @admin.action(description="Dismiss selected alerts")
    def dismiss_selected(self, request, queryset):
        for alert in queryset.filter(is_active=True):
            alert.dismiss()

    @admin.action(description="Re-activate selected alerts")
    def reactivate_selected(self, request, queryset):
        for alert in queryset.filter(is_active=False):
            alert.reactivate()
