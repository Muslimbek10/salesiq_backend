"""
ARIMA Forecaster
================
Auto-Regressive Integrated Moving Average model via statsmodels SARIMAX.

Model selection
---------------
A lightweight AIC-based grid search is run over a small set of ARIMA(p,d,q)
orders.  The model with the lowest AIC is selected automatically.

Search space:
  p ∈ {0, 1, 2}   — autoregressive lags
  d ∈ {0, 1}      — differencing order (1 = remove linear trend)
  q ∈ {0, 1, 2}   — moving-average lags

Maximum 18 candidate models → fast even inside Docker.

Seasonal extension (SARIMA)
---------------------------
Monthly data with 12+ months naturally contains seasonal patterns.
When the training series has >= 24 months, a (1,1,1,12) seasonal order
is added on top of the best ARIMA(p,d,q).  With fewer months the seasonal
component is skipped because seasonal differencing would eat too many
observations.

Why ARIMA here?
- Statistically rigorous — explicitly handles autocorrelation structure
- First-differences (d=1) make most revenue series stationary
- Outperforms both SMA and Linear Regression on data with momentum effects
- Confidence intervals available natively (stored in forecast_data)

Minimum history: 9 months (6 train + 3 hold-out).
"""
import logging
import warnings

import numpy as np
import pandas as pd

try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    _STATSMODELS_AVAILABLE = True
except ImportError:
    _STATSMODELS_AVAILABLE = False

from .metrics import calculate_mae, calculate_rmse

logger = logging.getLogger(__name__)

# ARIMA grid search space
_P_RANGE = [0, 1, 2]
_D_RANGE = [0, 1]
_Q_RANGE = [0, 1, 2]

# Use seasonal component when training series has at least this many months
_SEASONAL_MIN_PERIODS = 24


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fit_arima(series, order, seasonal_order=(0, 0, 0, 0)):
    """
    Fit a single SARIMAX model and return it, or None on convergence failure.
    Warnings from statsmodels are suppressed to keep logs clean.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            result = SARIMAX(
                series,
                order=order,
                seasonal_order=seasonal_order,
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False, maxiter=200)
            return result
        except Exception as exc:
            logger.debug("ARIMA%s failed: %s", order, exc)
            return None


def _select_best_order(series, use_seasonal):
    """
    Grid-search ARIMA orders by AIC. Return (best_order, best_seasonal_order).

    Parameters
    ----------
    series       : pd.Series — training revenue
    use_seasonal : bool      — whether to add seasonal (1,1,1,12)

    Returns
    -------
    (order, seasonal_order) — the winning combination
    """
    best_aic    = float("inf")
    best_order  = (1, 1, 1)          # sensible default if all fail
    best_s_order = (0, 0, 0, 0)

    seasonal_candidates = [(1, 1, 1, 12), (0, 0, 0, 0)] if use_seasonal else [(0, 0, 0, 0)]

    for p in _P_RANGE:
        for d in _D_RANGE:
            for q in _Q_RANGE:
                if p == 0 and q == 0:
                    continue    # white-noise model — not useful for forecasting
                order = (p, d, q)
                for s_order in seasonal_candidates:
                    result = _fit_arima(series, order, s_order)
                    if result is None:
                        continue
                    try:
                        aic = result.aic
                        if np.isfinite(aic) and aic < best_aic:
                            best_aic     = aic
                            best_order   = order
                            best_s_order = s_order
                    except Exception:
                        continue

    logger.info(
        "ARIMA model selected: order=%s seasonal=%s AIC=%.2f",
        best_order, best_s_order, best_aic,
    )
    return best_order, best_s_order


# ---------------------------------------------------------------------------
# Forecaster class
# ---------------------------------------------------------------------------

class ARIMAForecaster:
    """
    Auto-selected ARIMA / SARIMA forecaster.

    Parameters
    ----------
    auto_select : bool — run AIC grid search (True) or use order=(1,1,1) (False)
    """

    def __init__(self, auto_select=True):
        if not _STATSMODELS_AVAILABLE:
            raise ImportError(
                "statsmodels is required for the ARIMA model. "
                "Add statsmodels to requirements.txt and rebuild the Docker image."
            )
        self.auto_select     = auto_select
        self._result         = None    # fitted SARIMAX result object
        self._series         = None    # training revenue series
        self._order          = None
        self._seasonal_order = None

    # ------------------------------------------------------------------ #
    # Fit
    # ------------------------------------------------------------------ #

    def fit(self, df):
        """
        Fit the ARIMA model on the training DataFrame.

        Parameters
        ----------
        df : pd.DataFrame — 'revenue' column, DatetimeIndex (monthly freq)

        Returns self (for chaining)
        """
        self._series = df["revenue"].copy()

        use_seasonal = len(self._series) >= _SEASONAL_MIN_PERIODS

        if self.auto_select:
            self._order, self._seasonal_order = _select_best_order(
                self._series, use_seasonal
            )
        else:
            self._order          = (1, 1, 1)
            self._seasonal_order = (1, 1, 1, 12) if use_seasonal else (0, 0, 0, 0)

        self._result = _fit_arima(self._series, self._order, self._seasonal_order)

        # Ultimate fallback: plain ARIMA(1,1,1) with no seasonal term
        if self._result is None:
            logger.warning("Best ARIMA order failed to converge; falling back to ARIMA(1,1,1)")
            self._order          = (1, 1, 1)
            self._seasonal_order = (0, 0, 0, 0)
            self._result         = _fit_arima(self._series, (1, 1, 1), (0, 0, 0, 0))

        if self._result is None:
            raise RuntimeError(
                "ARIMA model could not be fitted on the provided data. "
                "Try using Linear Regression or Moving Average instead."
            )

        return self

    # ------------------------------------------------------------------ #
    # Predict
    # ------------------------------------------------------------------ #

    def predict(self, periods):
        """
        Forecast `periods` months beyond the training data.

        Parameters
        ----------
        periods : int — number of future months to forecast

        Returns
        -------
        list[dict] — [{period: "YYYY-MM", predicted: float}, ...]
        """
        if self._result is None:
            raise RuntimeError("Call fit() before predict().")

        last_period  = self._series.index[-1]
        future_index = pd.date_range(
            start=last_period + pd.DateOffset(months=1),
            periods=periods,
            freq="MS",
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            forecast = self._result.get_forecast(steps=periods)
            mean_vals = forecast.predicted_mean.values

        return [
            {
                "period":    p.strftime("%Y-%m"),
                "predicted": round(max(float(v), 0.0), 2),
            }
            for p, v in zip(future_index, mean_vals)
        ]

    # ------------------------------------------------------------------ #
    # Evaluate (hold-out)
    # ------------------------------------------------------------------ #

    def evaluate(self, df, holdout_periods=3):
        """
        Hold-out evaluation: train on df[:-holdout_periods], predict forward,
        compare against df[-holdout_periods:].

        Returns
        -------
        dict — {mae: float|None, rmse: float|None}
        """
        if len(df) <= holdout_periods:
            return {"mae": None, "rmse": None}

        train = df.iloc[:-holdout_periods]
        test  = df.iloc[-holdout_periods:]

        try:
            self.fit(train)
            predictions = self.predict(holdout_periods)
        except Exception as exc:
            logger.warning("ARIMA evaluate failed: %s", exc)
            return {"mae": None, "rmse": None}

        actual    = [float(v) for v in test["revenue"]]
        predicted = [p["predicted"] for p in predictions]

        return {
            "mae":  calculate_mae(actual, predicted),
            "rmse": calculate_rmse(actual, predicted),
        }

    # ------------------------------------------------------------------ #
    # Fitted values (for chart overlay)
    # ------------------------------------------------------------------ #

    def fitted_values(self):
        """
        In-sample one-step-ahead predictions from the fitted ARIMA model.
        These show how well the model tracks historical data.

        Returns
        -------
        list[dict] — [{period: "YYYY-MM", fitted: float}, ...]
        """
        if self._result is None:
            return []

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            in_sample = self._result.fittedvalues

        return [
            {
                "period": idx.strftime("%Y-%m"),
                "fitted": round(max(float(v), 0.0), 2),
            }
            for idx, v in in_sample.items()
            if idx in self._series.index
        ]

    @property
    def selected_order(self):
        """Return the auto-selected ARIMA order for diagnostic display."""
        return {"order": self._order, "seasonal_order": self._seasonal_order}
