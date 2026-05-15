"""
Forecasting Serializers
=======================

ForecastRequestSerializer
  Validates POST /api/forecast/run/ request body.
  Enforces target_id rules (required for product/category/branch, null for overall).

ForecastResponseSerializer
  Full response including forecast_data (month-by-month breakdown for chart).
  Returned after a successful run.

ForecastListSerializer
  Lightweight list view — omits forecast_data to keep paginated responses small.
  Used by GET /api/forecast/history/.
"""
from rest_framework import serializers

from .models import Forecast


# ---------------------------------------------------------------------------
# Request (write)
# ---------------------------------------------------------------------------

class ForecastRequestSerializer(serializers.Serializer):
    """Validates the POST /api/forecast/run/ request body."""

    target_type = serializers.ChoiceField(
        choices=Forecast.TargetType.choices,
        help_text=(
            "Type of entity to forecast: "
            "'overall' (whole business), 'product', 'category', 'branch'."
        ),
    )
    target_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        help_text="PK of the target entity. Required for product/category/branch; null for overall.",
    )
    model_name = serializers.ChoiceField(
        choices=[
            (Forecast.ModelName.MOVING_AVERAGE,    "Moving Average"),
            (Forecast.ModelName.LINEAR_REGRESSION, "Linear Regression"),
            (Forecast.ModelName.RANDOM_FOREST,     "Random Forest"),
            (Forecast.ModelName.ARIMA,             "ARIMA"),
        ],
        help_text="Forecasting algorithm to use.",
    )
    forecast_period_months = serializers.ChoiceField(
        choices=[(1, "1 Month"), (3, "3 Months"), (6, "6 Months"), (12, "12 Months")],
        help_text="Number of months ahead to forecast.",
    )
    months_back = serializers.IntegerField(
        min_value=6,
        max_value=60,
        default=24,
        required=False,
        help_text="Months of historical data to use for training (default 24, max 60).",
    )
    # Moving Average only
    window = serializers.IntegerField(
        min_value=2,
        max_value=12,
        default=3,
        required=False,
        help_text="Averaging window for Moving Average (ignored for Linear Regression).",
    )

    def validate(self, data):
        target_type = data["target_type"]
        target_id   = data.get("target_id")

        if target_type == Forecast.TargetType.OVERALL and target_id is not None:
            raise serializers.ValidationError({
                "target_id": "Set target_id to null for 'overall' forecasts."
            })
        if target_type != Forecast.TargetType.OVERALL and not target_id:
            raise serializers.ValidationError({
                "target_id": f"target_id is required for '{target_type}' forecasts."
            })
        return data


# ---------------------------------------------------------------------------
# Response (read)
# ---------------------------------------------------------------------------

class ForecastResponseSerializer(serializers.ModelSerializer):
    """
    Full forecast response — includes forecast_data for chart rendering.
    Returned by POST /api/forecast/run/ and GET /api/forecast/history/{id}/.
    """
    accuracy_label    = serializers.CharField(read_only=True)
    historical_points = serializers.ListField(read_only=True)
    predicted_points  = serializers.ListField(read_only=True)

    class Meta:
        model  = Forecast
        fields = [
            "id",
            "forecast_target_type",
            "target_id",
            "model_name",
            "forecast_period_months",
            "predicted_revenue",
            "mae",
            "rmse",
            "mape",
            "accuracy_label",
            "commentary",
            "forecast_data",
            "historical_points",
            "predicted_points",
            "created_at",
        ]
        read_only_fields = fields


class ForecastListSerializer(serializers.ModelSerializer):
    """
    Lightweight list view — omits forecast_data.
    Used by GET /api/forecast/history/.
    """
    accuracy_label = serializers.CharField(read_only=True)

    class Meta:
        model  = Forecast
        fields = [
            "id",
            "forecast_target_type",
            "target_id",
            "model_name",
            "forecast_period_months",
            "predicted_revenue",
            "mae",
            "rmse",
            "mape",
            "accuracy_label",
            "commentary",
            "created_at",
        ]
        read_only_fields = fields
