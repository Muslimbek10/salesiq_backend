"""
Forecasting Model
=================
Stores results from each run of the AI forecasting engine.

Design decisions:
  - One record per forecast run — multiple runs for the same target are all
    kept, creating a history that shows how forecasts improved over time.
  - target_type + target_id is a "soft polymorphic FK" — no enforced DB
    constraint because the target can be a Product, Category, Branch, or
    the whole business ("overall" with target_id=None). Enforcing separate
    FKs would require nullable columns for every possible target.
  - forecast_data stores the full month-by-month breakdown as JSONB. This
    avoids a separate ForecastDataPoint table and is ideal for chart rendering.
  - accuracy_label is a computed property — a human-readable quality rating
    derived from RMSE that the frontend can display without business logic.
  - CheckConstraints prevent invalid period and model values at the DB level.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------

class ForecastQuerySet(models.QuerySet):

    def for_target(self, target_type, target_id=None):
        """Filter by target type and optional target id."""
        qs = self.filter(forecast_target_type=target_type)
        if target_id is not None:
            qs = qs.filter(target_id=target_id)
        return qs

    def overall(self):
        return self.filter(forecast_target_type=Forecast.TargetType.OVERALL)

    def for_product(self, product_id):
        return self.filter(
            forecast_target_type=Forecast.TargetType.PRODUCT,
            target_id=product_id,
        )

    def for_category(self, category_id):
        return self.filter(
            forecast_target_type=Forecast.TargetType.CATEGORY,
            target_id=category_id,
        )

    def for_branch(self, branch_id):
        return self.filter(
            forecast_target_type=Forecast.TargetType.BRANCH,
            target_id=branch_id,
        )

    def by_model(self, model_name):
        return self.filter(model_name=model_name)

    def latest_per_target(self):
        """
        Return only the most recent forecast for each unique
        (target_type, target_id, model_name) combination.
        Useful for the forecast history summary view.
        """
        from django.db.models import OuterRef, Subquery
        latest = (
            Forecast.objects
            .filter(
                forecast_target_type=OuterRef("forecast_target_type"),
                target_id=OuterRef("target_id"),
                model_name=OuterRef("model_name"),
            )
            .order_by("-created_at")
            .values("id")[:1]
        )
        return self.filter(id__in=Subquery(latest))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Forecast(models.Model):
    """
    Stored result from one forecasting engine run.

    Target identification:
        forecast_target_type = "product"   → target_id = Product.id
        forecast_target_type = "category"  → target_id = Category.id
        forecast_target_type = "branch"    → target_id = Branch.id
        forecast_target_type = "overall"   → target_id = None

    forecast_data JSON schema:
        [
          {"period": "2025-01", "actual": 45000.00, "predicted": null},
          {"period": "2025-02", "actual": 47000.00, "predicted": null},
          ...
          {"period": "2026-01", "actual": null, "predicted": 54200.00},
          {"period": "2026-02", "actual": null, "predicted": 56100.00},
        ]
    """

    class TargetType(models.TextChoices):
        PRODUCT  = "product",  "Product"
        CATEGORY = "category", "Category"
        BRANCH   = "branch",   "Branch"
        OVERALL  = "overall",  "Overall Business"

    class ModelName(models.TextChoices):
        MOVING_AVERAGE    = "moving_average",    "Moving Average"
        LINEAR_REGRESSION = "linear_regression", "Linear Regression"
        RANDOM_FOREST     = "random_forest",     "Random Forest"
        ARIMA             = "arima",             "ARIMA"

    class PeriodMonths(models.IntegerChoices):
        ONE    = 1,  "1 Month"
        THREE  = 3,  "3 Months"
        SIX    = 6,  "6 Months"
        TWELVE = 12, "12 Months"

    # ------------------------------------------------------------------
    # Target identification
    # ------------------------------------------------------------------
    forecast_target_type = models.CharField(
        max_length=20,
        choices=TargetType.choices,
        db_index=True,
        help_text="The type of entity being forecast.",
    )
    target_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="PK of the target entity. Null for 'overall' forecasts.",
    )

    # ------------------------------------------------------------------
    # Forecast parameters
    # ------------------------------------------------------------------
    forecast_period_months = models.IntegerField(
        choices=PeriodMonths.choices,
        help_text="Number of months ahead to forecast: 1, 3, or 6.",
    )
    model_name = models.CharField(
        max_length=30,
        choices=ModelName.choices,
        help_text="The statistical or ML model used to generate this forecast.",
    )

    # ------------------------------------------------------------------
    # Aggregate predictions (totals over the full forecast period)
    # ------------------------------------------------------------------
    predicted_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total predicted units over the forecast period.",
    )
    predicted_revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total predicted revenue over the forecast period.",
    )

    # ------------------------------------------------------------------
    # Model accuracy metrics
    # ------------------------------------------------------------------
    mae = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Mean Absolute Error — average magnitude of prediction errors.",
    )
    rmse = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Root Mean Squared Error — penalises large errors more than MAE.",
    )
    mape = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Mean Absolute Percentage Error — average % deviation from actuals.",
    )

    # ------------------------------------------------------------------
    # Human-readable output
    # ------------------------------------------------------------------
    commentary = models.TextField(
        blank=True,
        default="",
        help_text="Auto-generated plain-language interpretation of the forecast.",
    )

    # ------------------------------------------------------------------
    # Full monthly breakdown (stored as JSON for chart rendering)
    # ------------------------------------------------------------------
    forecast_data = models.JSONField(
        default=list,
        help_text=(
            "Array of {period, actual, predicted} dicts covering "
            "both historical and forecast months."
        ),
    )

    # ------------------------------------------------------------------
    # Timestamp
    # ------------------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = ForecastQuerySet.as_manager()

    class Meta:
        db_table         = "forecasts"
        verbose_name     = "Forecast"
        verbose_name_plural = "Forecasts"
        ordering         = ["-created_at"]
        indexes = [
            models.Index(
                fields=["forecast_target_type", "target_id", "created_at"],
                name="idx_forecast_target_created",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(forecast_period_months__in=[1, 3, 6, 12]),
                name="chk_forecast_period_valid",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(mae__isnull=True) | models.Q(mae__gte=0)
                ),
                name="chk_forecast_mae_non_negative",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(rmse__isnull=True) | models.Q(rmse__gte=0)
                ),
                name="chk_forecast_rmse_non_negative",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(mape__isnull=True) | models.Q(mape__gte=0)
                ),
                name="chk_forecast_mape_non_negative",
            ),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def clean(self):
        super().clean()

        # overall forecasts must not have a target_id
        if self.forecast_target_type == self.TargetType.OVERALL and self.target_id is not None:
            raise ValidationError({
                "target_id": "Overall forecasts must not reference a specific entity (target_id must be null)."
            })

        # non-overall forecasts must have a target_id
        if self.forecast_target_type != self.TargetType.OVERALL and self.target_id is None:
            raise ValidationError({
                "target_id": f"A target_id is required for forecasts of type '{self.forecast_target_type}'."
            })

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------
    def __str__(self):
        target = f"#{self.target_id}" if self.target_id else "all"
        return (
            f"[{self.get_model_name_display()}] "
            f"{self.get_forecast_target_type_display()} {target} "
            f"→ {self.forecast_period_months}mo forecast"
        )

    def __repr__(self):
        return (
            f"<Forecast id={self.pk} type={self.forecast_target_type!r} "
            f"target_id={self.target_id} model={self.model_name!r}>"
        )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def accuracy_label(self):
        """
        Human-readable accuracy rating.
        Prefers MAPE (percentage-based, scale-independent) when available;
        falls back to RMSE (absolute, same currency unit as revenue).

        MAPE thresholds (industry standard):
          < 10% → Excellent  |  < 20% → Good  |  < 50% → Moderate  |  ≥ 50% → Low

        RMSE thresholds (relative to typical monthly revenue):
          < 500  → Excellent  |  < 2000 → Good  |  < 5000 → Moderate  |  ≥ 5000 → Low
        """
        if self.mape is not None:
            mape = float(self.mape)
            if mape < 10:
                return "Excellent"
            if mape < 20:
                return "Good"
            if mape < 50:
                return "Moderate"
            return "Low"
        if self.rmse is not None:
            rmse = float(self.rmse)
            if rmse < 500:
                return "Excellent"
            if rmse < 2000:
                return "Good"
            if rmse < 5000:
                return "Moderate"
            return "Low"
        return "Unknown"

    @property
    def has_data(self):
        """True when forecast_data contains at least one entry."""
        return bool(self.forecast_data)

    @property
    def historical_points(self):
        """Subset of forecast_data where actual is not null."""
        return [p for p in self.forecast_data if p.get("actual") is not None]

    @property
    def predicted_points(self):
        """Subset of forecast_data where predicted is not null."""
        return [p for p in self.forecast_data if p.get("predicted") is not None]
