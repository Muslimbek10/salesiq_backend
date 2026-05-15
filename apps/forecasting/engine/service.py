"""
Forecasting Service
===================
Main orchestration layer.  Accepts user parameters, selects the right model,
runs the full pipeline, and persists the Forecast record.

Pipeline
--------
1. load_monthly_revenue()  — pull history from DB into a Pandas DataFrame
2. validate_series()        — ensure enough data to train
3. model.evaluate()         — hold-out accuracy metrics (MAE, RMSE)
4. model.fit(full_series)   — train on all available history
5. model.predict(periods)   — generate future forecasts
6. model.fitted_values()    — in-sample fit for chart overlay
7. _build_forecast_data()   — merge historical + future into JSON array
8. _generate_commentary()   — plain-language summary for the UI
9. Forecast.save()          — persist everything to the database

Public API
----------
run_forecast(target_type, target_id, model_name, forecast_period_months, ...)
  → Forecast instance (saved to DB)
"""
import logging
from decimal import Decimal

from apps.forecasting.models import Forecast

from .arima import ARIMAForecaster
from .linear_regression import LinearRegressionForecaster
from .metrics import calculate_mae, calculate_mape, calculate_rmse
from .moving_average import MovingAverageForecaster
from .preprocessor import load_monthly_revenue, validate_series
from .random_forest import RandomForestForecaster

logger = logging.getLogger(__name__)

# Minimum months of history (including hold-out) required per model type
_MIN_HISTORY = {
    Forecast.ModelName.MOVING_AVERAGE:    6,   # 3 train + 3 hold-out
    Forecast.ModelName.LINEAR_REGRESSION: 9,   # 6 train + 3 hold-out
    Forecast.ModelName.RANDOM_FOREST:     9,   # needs ≥3 lag features + hold-out
    Forecast.ModelName.ARIMA:             9,   # ARIMA(p,d,q) needs ~6 obs minimum
}

_HOLDOUT_PERIODS = 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_model(model_name, **kwargs):
    """Instantiate the correct forecaster class."""
    if model_name == Forecast.ModelName.MOVING_AVERAGE:
        return MovingAverageForecaster(window=kwargs.get("window", 3))
    if model_name == Forecast.ModelName.LINEAR_REGRESSION:
        return LinearRegressionForecaster(
            with_seasonality=kwargs.get("with_seasonality", True)
        )
    if model_name == Forecast.ModelName.RANDOM_FOREST:
        return RandomForestForecaster(
            n_estimators=kwargs.get("n_estimators", 200),
            min_samples_leaf=kwargs.get("min_samples_leaf", 2),
        )
    if model_name == Forecast.ModelName.ARIMA:
        return ARIMAForecaster(
            auto_select=kwargs.get("auto_select", True),
        )
    raise ValueError(
        f"Unsupported model_name '{model_name}'. "
        f"Valid options: {[c[0] for c in Forecast.ModelName.choices]}"
    )


def _build_forecast_data(df, future, fitted):
    """
    Merge historical actuals, in-sample fitted values, and future predictions
    into the flat JSON array stored in Forecast.forecast_data.

    Schema per entry:
      {period, actual, fitted, predicted}
      — historical months: actual=float, fitted=float, predicted=null
      — future months:     actual=null,  fitted=null,  predicted=float
    """
    fitted_by_period = {f["period"]: f["fitted"] for f in fitted}

    historical = [
        {
            "period":    idx.strftime("%Y-%m"),
            "actual":    round(float(val), 2),
            "fitted":    fitted_by_period.get(idx.strftime("%Y-%m")),
            "predicted": None,
        }
        for idx, val in df["revenue"].items()
    ]

    future_points = [
        {
            "period":    p["period"],
            "actual":    None,
            "fitted":    None,
            "predicted": p["predicted"],
        }
        for p in future
    ]

    return historical + future_points


def _generate_commentary(future, metrics, model_name):
    """
    Generate a plain-language interpretation of the forecast results.
    Written in a style suitable for an analytics dashboard card.
    """
    if not future:
        return "Unable to generate a forecast — insufficient data."

    values        = [p["predicted"] for p in future]
    avg_predicted = sum(values) / len(values)
    first, last   = values[0], values[-1]

    if last > first * 1.05:
        trend = "upward"
    elif last < first * 0.95:
        trend = "downward"
    else:
        trend = "stable"

    model_label = {
        Forecast.ModelName.MOVING_AVERAGE:    "Moving Average",
        Forecast.ModelName.LINEAR_REGRESSION: "Linear Regression",
        Forecast.ModelName.RANDOM_FOREST:     "Random Forest",
        Forecast.ModelName.ARIMA:             "ARIMA",
    }.get(model_name, model_name)

    mape = metrics.get("mape")
    rmse = metrics.get("rmse")

    if mape is not None:
        if mape < 10:
            accuracy_label = f"excellent accuracy (MAPE: {mape:.1f}%)"
        elif mape < 20:
            accuracy_label = f"good accuracy (MAPE: {mape:.1f}%)"
        elif mape < 50:
            accuracy_label = f"moderate accuracy (MAPE: {mape:.1f}%)"
        else:
            accuracy_label = f"low accuracy — treat with caution (MAPE: {mape:.1f}%)"
    elif rmse is not None:
        if rmse < 500:
            accuracy_label = f"excellent accuracy (RMSE: {rmse:,.2f})"
        elif rmse < 2000:
            accuracy_label = f"good accuracy (RMSE: {rmse:,.2f})"
        elif rmse < 5000:
            accuracy_label = f"moderate accuracy (RMSE: {rmse:,.2f})"
        else:
            accuracy_label = f"low accuracy — treat with caution (RMSE: {rmse:,.2f})"
    else:
        accuracy_label = "accuracy could not be measured"

    return (
        f"The {model_label} model projects a {trend} revenue trend "
        f"averaging {avg_predicted:,.2f} per month over the forecast window. "
        f"Hold-out evaluation indicates {accuracy_label}."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_forecast(
    target_type,
    target_id,
    model_name,
    forecast_period_months,
    months_back=24,
    **model_kwargs,
):
    """
    Execute the full forecasting pipeline and persist the result.

    Parameters
    ----------
    target_type             : str  — Forecast.TargetType value
    target_id               : int | None
    model_name              : str  — Forecast.ModelName value
    forecast_period_months  : int  — 1 | 3 | 6
    months_back             : int  — months of history to load (default 24)
    **model_kwargs          : extra model params (e.g. window=5)

    Returns
    -------
    Forecast instance (saved to DB)

    Raises
    ------
    ValueError  — insufficient data or unsupported model
    """
    # 1. Load history
    df = load_monthly_revenue(target_type, target_id, months_back=months_back)

    # 2. Validate
    min_required = _MIN_HISTORY.get(model_name, 6)
    validate_series(df, min_periods=min_required)

    # 3. Build model and evaluate on hold-out
    model   = _build_model(model_name, **model_kwargs)
    metrics = model.evaluate(df, holdout_periods=_HOLDOUT_PERIODS)

    # Compute MAPE from hold-out results (requires actual values)
    holdout_actuals = [float(v) for v in df.iloc[-_HOLDOUT_PERIODS:]["revenue"]]
    holdout_future  = model.predict(_HOLDOUT_PERIODS) if metrics.get("mae") is not None else []
    holdout_preds   = [p["predicted"] for p in holdout_future]
    metrics["mape"] = calculate_mape(holdout_actuals, holdout_preds)

    # 4. Re-fit on the full series
    model.fit(df)

    # 5. Predict future periods
    future = model.predict(forecast_period_months)

    # 6. In-sample fitted values for chart overlay
    fitted = model.fitted_values()

    # 7. Build forecast_data JSON array
    forecast_data = _build_forecast_data(df, future, fitted)

    # 8. Aggregate totals
    predicted_revenue = sum(p["predicted"] for p in future)

    # 9. Commentary
    commentary = _generate_commentary(future, metrics, model_name)

    # 10. Persist
    forecast = Forecast(
        forecast_target_type   = target_type,
        target_id              = target_id,
        model_name             = model_name,
        forecast_period_months = forecast_period_months,
        predicted_revenue      = Decimal(str(round(predicted_revenue, 2))),
        mae                    = Decimal(str(metrics["mae"]))  if metrics.get("mae")  is not None else None,
        rmse                   = Decimal(str(metrics["rmse"])) if metrics.get("rmse") is not None else None,
        mape                   = Decimal(str(metrics["mape"])) if metrics.get("mape") is not None else None,
        commentary             = commentary,
        forecast_data          = forecast_data,
    )
    forecast.full_clean()
    forecast.save()

    logger.info(
        "Forecast saved: id=%s type=%s target_id=%s model=%s "
        "periods=%s mae=%s rmse=%s mape=%s predicted_revenue=%s",
        forecast.pk, target_type, target_id, model_name,
        forecast_period_months, metrics.get("mae"), metrics.get("rmse"),
        metrics.get("mape"), round(predicted_revenue, 2),
    )
    return forecast
