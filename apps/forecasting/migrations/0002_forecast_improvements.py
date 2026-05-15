# Generated migration — forecasting engine improvements
#
# Changes:
#   1. Add mape (Mean Absolute Percentage Error) DecimalField
#   2. Add 12-month forecast period to PeriodMonths choices
#   3. Add ARIMA to ModelName choices
#   4. Replace chk_forecast_period_valid constraint (1/3/6 → 1/3/6/12)
#   5. Add chk_forecast_mape_non_negative constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("forecasting", "0001_initial"),
    ]

    operations = [
        # ── 1. Add mape field ──────────────────────────────────────────────
        migrations.AddField(
            model_name="forecast",
            name="mape",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Mean Absolute Percentage Error — average % deviation from actuals.",
                max_digits=10,
                null=True,
            ),
        ),

        # ── 2. Update model_name choices (adds ARIMA) ──────────────────────
        # CharField choices are Python-level only — no DB schema change needed.
        migrations.AlterField(
            model_name="forecast",
            name="model_name",
            field=models.CharField(
                choices=[
                    ("moving_average",    "Moving Average"),
                    ("linear_regression", "Linear Regression"),
                    ("random_forest",     "Random Forest"),
                    ("arima",             "ARIMA"),
                ],
                help_text="The statistical or ML model used to generate this forecast.",
                max_length=30,
            ),
        ),

        # ── 3. Update forecast_period_months choices (adds 12) ─────────────
        migrations.AlterField(
            model_name="forecast",
            name="forecast_period_months",
            field=models.IntegerField(
                choices=[(1, "1 Month"), (3, "3 Months"), (6, "6 Months"), (12, "12 Months")],
                help_text="Number of months ahead to forecast: 1, 3, 6, or 12.",
            ),
        ),

        # ── 4. Replace period CHECK constraint (drop old, add new) ─────────
        migrations.RemoveConstraint(
            model_name="forecast",
            name="chk_forecast_period_valid",
        ),
        migrations.AddConstraint(
            model_name="forecast",
            constraint=models.CheckConstraint(
                check=models.Q(forecast_period_months__in=[1, 3, 6, 12]),
                name="chk_forecast_period_valid",
            ),
        ),

        # ── 5. Add mape non-negative constraint ────────────────────────────
        migrations.AddConstraint(
            model_name="forecast",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(mape__isnull=True) | models.Q(mape__gte=0)
                ),
                name="chk_forecast_mape_non_negative",
            ),
        ),
    ]
