from django.contrib import admin

from .models import Forecast


@admin.register(Forecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display = (
        "forecast_target_type", "target_id", "model_name",
        "forecast_period_months", "predicted_revenue", "mae", "rmse", "created_at",
    )
    list_filter = ("forecast_target_type", "model_name", "forecast_period_months")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "forecast_data")
