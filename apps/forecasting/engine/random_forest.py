"""
Random Forest Forecaster
========================
Uses scikit-learn's RandomForestRegressor with engineered time-series features.

Feature set
-----------
t            — monotonic time index (0, 1, 2, …)         captures trend
month_sin    — sin(2π × month / 12)  ⎫  cyclical month   captures seasonality
month_cos    — cos(2π × month / 12)  ⎭  encoding
lag_1        — revenue t-1 month ago                      short autocorrelation
lag_2        — revenue t-2 months ago
lag_3        — revenue t-3 months ago                     quarterly cycle echo

All features are scaled via StandardScaler before training.

Prediction strategy
-------------------
Recursive (aka "direct rollout"): predict one period at a time, feed the
prediction back as a lag feature for the next period.  This lets the model
propagate its own momentum into the forecast window.

Why Random Forest over Linear Regression here?
- Handles non-linear interactions between trend and seasonal features
- Robust to individual outlier months (majority-vote across trees)
- No assumption of normally distributed residuals
- min_samples_leaf prevents overfitting on small (12-month) datasets

Minimum history required: 9 months (6 train + 3 hold-out), same as
LinearRegressionForecaster, because we need at least 3 lag features.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

from .metrics import calculate_mae, calculate_rmse


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _build_rf_features(series):
    """
    Build feature matrix for a period-indexed revenue series.

    Lag features for the first few observations are back-filled with the
    earliest available value rather than 0 — this avoids artificially
    depressing the model's view of historical revenue at the start.

    Parameters
    ----------
    series : pd.Series — DatetimeIndex, values = monthly revenue

    Returns
    -------
    np.ndarray — shape (n, 6): [t, sin, cos, lag1, lag2, lag3]
    """
    n      = len(series)
    values = series.values.astype(float)

    t         = np.arange(n, dtype=float)
    months    = np.array([idx.month for idx in series.index], dtype=float)
    month_sin = np.sin(2 * np.pi * months / 12)
    month_cos = np.cos(2 * np.pi * months / 12)

    # Lag arrays — pad the beginning with the first observed value
    lag1 = np.empty(n); lag1[0]  = values[0]; lag1[1:]  = values[:-1]
    lag2 = np.empty(n); lag2[:2] = values[0]; lag2[2:]  = values[:-2]
    lag3 = np.empty(n); lag3[:3] = values[0]; lag3[3:]  = values[:-3]

    return np.column_stack([t, month_sin, month_cos, lag1, lag2, lag3])


# ---------------------------------------------------------------------------
# Forecaster class
# ---------------------------------------------------------------------------

class RandomForestForecaster:
    """
    Random Forest forecaster with recursive multi-step prediction.

    Parameters
    ----------
    n_estimators : int — number of trees (default 200; more = more stable)
    max_depth    : int | None — tree depth limit (None = fully grown)
    min_samples_leaf : int — minimum samples per leaf (prevents overfitting)
    """

    def __init__(self, n_estimators=200, max_depth=None, min_samples_leaf=2):
        self.n_estimators     = n_estimators
        self.max_depth        = max_depth
        self.min_samples_leaf = min_samples_leaf

        self._model  = RandomForestRegressor(
            n_estimators     = n_estimators,
            max_depth        = max_depth,
            min_samples_leaf = min_samples_leaf,
            random_state     = 42,            # reproducible results
            n_jobs           = -1,            # use all CPU cores
        )
        self._scaler = StandardScaler()
        self._series = None   # training revenue series (pd.Series)
        self._n      = 0      # training length

    # ------------------------------------------------------------------ #
    # Fit
    # ------------------------------------------------------------------ #

    def fit(self, df):
        """
        Train the Random Forest on the full training DataFrame.

        Parameters
        ----------
        df : pd.DataFrame — 'revenue' column, DatetimeIndex

        Returns self (for chaining)
        """
        self._series = df["revenue"].copy()
        self._n      = len(self._series)
        X_raw = _build_rf_features(self._series)
        X     = self._scaler.fit_transform(X_raw)
        y     = self._series.values.astype(float)
        self._model.fit(X, y)
        return self

    # ------------------------------------------------------------------ #
    # Predict
    # ------------------------------------------------------------------ #

    def predict(self, periods):
        """
        Recursively forecast `periods` months beyond the training data.

        Each predicted value is immediately appended to the rolling history
        buffer so that lag features for subsequent steps use the model's own
        predictions — this allows multi-step momentum to propagate naturally.

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

        # Rolling history buffer — start with training values
        history = list(self._series.values.astype(float))
        predictions = []

        for i, period in enumerate(future_index):
            t_val = float(self._n + i)
            m     = float(period.month)
            sin_m = np.sin(2 * np.pi * m / 12)
            cos_m = np.cos(2 * np.pi * m / 12)

            lag1 = history[-1]
            lag2 = history[-2] if len(history) >= 2 else history[-1]
            lag3 = history[-3] if len(history) >= 3 else history[-1]

            X_raw = np.array([[t_val, sin_m, cos_m, lag1, lag2, lag3]])
            X     = self._scaler.transform(X_raw)
            pred  = max(float(self._model.predict(X)[0]), 0.0)   # revenue ≥ 0

            predictions.append({
                "period":    period.strftime("%Y-%m"),
                "predicted": round(pred, 2),
            })
            history.append(pred)

        return predictions

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
        In-sample fitted values — shows how well the forest tracks history.

        Returns
        -------
        list[dict] — [{period: "YYYY-MM", fitted: float}, ...]
        """
        if self._series is None:
            return []
        X_raw  = _build_rf_features(self._series)
        X      = self._scaler.transform(X_raw)
        fitted = self._model.predict(X)
        return [
            {"period": idx.strftime("%Y-%m"), "fitted": round(max(float(v), 0.0), 2)}
            for idx, v in zip(self._series.index, fitted)
        ]

    @property
    def feature_importances(self):
        """
        Return feature importance scores as a dict (diagnostic / explainability).
        Higher value = more influential in the model's decisions.
        """
        if self._series is None:
            return {}
        names = ["trend", "month_sin", "month_cos", "lag_1", "lag_2", "lag_3"]
        return {
            name: round(float(imp), 4)
            for name, imp in zip(names, self._model.feature_importances_)
        }
