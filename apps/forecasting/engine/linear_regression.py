"""
Linear Regression Forecaster
==============================
OLS linear regression on a numeric time index with optional cyclical
month-of-year encoding to capture seasonal patterns.

Feature engineering
-------------------
t            — monotonically increasing integer index (0, 1, 2, …)
               captures the overall trend (slope of the regression line)

month_sin    — sin(2π × month / 12)  ⎫ cyclical encoding of month-of-year
month_cos    — cos(2π × month / 12)  ⎭ lets the model learn seasonal shapes
               without dummy variables (avoids the dummy-variable trap and
               handles the Jan→Dec boundary naturally)

Using sin+cos together encodes both the phase and amplitude of the
seasonal cycle as a smooth curve — better than 11 binary month dummies
when the dataset is small.

Evaluation
----------
Same hold-out strategy as MovingAverageForecaster for a fair apples-to-apples
MAE / RMSE comparison between models.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

from .metrics import calculate_mae, calculate_rmse


def _build_features(series, with_seasonality=True):
    """
    Construct the feature matrix for a period-indexed revenue series.

    Parameters
    ----------
    series           : pd.Series — DatetimeIndex, values = revenue
    with_seasonality : bool      — include sin/cos month features

    Returns
    -------
    np.ndarray — shape (n_samples, n_features)
    """
    n = len(series)
    t = np.arange(n, dtype=float).reshape(-1, 1)

    if not with_seasonality:
        return t

    months    = np.array([idx.month for idx in series.index], dtype=float).reshape(-1, 1)
    month_sin = np.sin(2 * np.pi * months / 12)
    month_cos = np.cos(2 * np.pi * months / 12)
    return np.hstack([t, month_sin, month_cos])


class LinearRegressionForecaster:
    """
    OLS Linear Regression with optional cyclical seasonal encoding.

    Parameters
    ----------
    with_seasonality : bool — include sin/cos month features (default True)
    """

    def __init__(self, with_seasonality=True):
        self.with_seasonality = with_seasonality
        self._model  = LinearRegression()
        self._scaler = StandardScaler()   # normalise features so trend index
        self._series = None               # doesn't dominate sin/cos columns
        self._n      = 0                  # number of training observations

    # ------------------------------------------------------------------ #
    # Fit
    # ------------------------------------------------------------------ #

    def fit(self, df):
        """
        Fit the regression model on the training DataFrame.

        Parameters
        ----------
        df : pd.DataFrame  — 'revenue' column, DatetimeIndex

        Returns self (for chaining)
        """
        self._series = df["revenue"].copy()
        self._n      = len(self._series)
        X_raw = _build_features(self._series, self.with_seasonality)
        X     = self._scaler.fit_transform(X_raw)   # scale: mean=0, std=1
        y     = self._series.values.astype(float)
        self._model.fit(X, y)
        return self

    # ------------------------------------------------------------------ #
    # Predict
    # ------------------------------------------------------------------ #

    def predict(self, periods):
        """
        Predict `periods` months beyond the end of the training series.

        The time index continues from _n upward so the trend extrapolates
        naturally from where training ended.

        Parameters
        ----------
        periods : int — number of future months to forecast

        Returns
        -------
        list[dict] — [{period: "YYYY-MM", predicted: float}, ...]
        """
        if self._series is None:
            raise RuntimeError("Call fit() before predict().")

        last_period  = self._series.index[-1]
        future_index = pd.date_range(
            start=last_period + pd.DateOffset(months=1),
            periods=periods,
            freq="MS",
        )

        t_future = np.arange(self._n, self._n + periods, dtype=float).reshape(-1, 1)

        if self.with_seasonality:
            months    = np.array([idx.month for idx in future_index], dtype=float).reshape(-1, 1)
            month_sin = np.sin(2 * np.pi * months / 12)
            month_cos = np.cos(2 * np.pi * months / 12)
            X_future  = np.hstack([t_future, month_sin, month_cos])
        else:
            X_future = t_future

        X_future = self._scaler.transform(X_future)   # use fitted scaler
        raw      = self._model.predict(X_future)
        return [
            {
                "period":    p.strftime("%Y-%m"),
                "predicted": round(max(float(v), 0.0), 2),  # clip: revenue ≥ 0
            }
            for p, v in zip(future_index, raw)
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

        self.fit(train)
        predictions = self.predict(holdout_periods)

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
        In-sample fitted values over the training series.
        Displayed as an overlay on the chart to show how well the
        regression line fits historical data.

        Returns
        -------
        list[dict] — [{period: "YYYY-MM", fitted: float}, ...]
        """
        if self._series is None:
            return []
        X_raw  = _build_features(self._series, self.with_seasonality)
        X      = self._scaler.transform(X_raw)
        fitted = self._model.predict(X)
        return [
            {"period": idx.strftime("%Y-%m"), "fitted": round(max(float(v), 0.0), 2)}
            for idx, v in zip(self._series.index, fitted)
        ]

    @property
    def coefficients(self):
        """
        Return regression coefficients for diagnostic display.
        {intercept, trend_slope, [month_sin_coef, month_cos_coef]}
        """
        if self._series is None:
            return {}
        coefs  = self._model.coef_
        result = {
            "intercept":   round(float(self._model.intercept_), 4),
            "trend_slope": round(float(coefs[0]), 4),
        }
        if self.with_seasonality and len(coefs) >= 3:
            result["month_sin_coef"] = round(float(coefs[1]), 4)
            result["month_cos_coef"] = round(float(coefs[2]), 4)
        return result
