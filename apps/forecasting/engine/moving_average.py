"""
Moving Average Forecaster
=========================
Simple Moving Average (SMA) applied to the monthly revenue series.

How it works
------------
1. Fit: compute the average of the last `window` historical months.
2. Predict: every future period receives that same average (flat forecast).
   This is the "naïve" but interpretable baseline — useful when there
   is no strong trend and data is noisy.

Evaluation
----------
A hold-out window is carved out from the end of training data.
The model is trained on everything before it, predicted forward,
and MAE / RMSE are computed against the held-out actuals.
This gives a realistic out-of-sample accuracy estimate.

Fitted values
-------------
fitted_values() returns a rolling SMA over the training series for
chart overlay (shows how well SMA tracks historical data).
"""
import pandas as pd

from .metrics import calculate_mae, calculate_rmse


class MovingAverageForecaster:
    """
    Simple Moving Average (SMA) forecaster.

    Parameters
    ----------
    window : int — number of past months to average (default 3)
    """

    def __init__(self, window=3):
        if window < 1:
            raise ValueError("window must be >= 1")
        self.window   = window
        self._series  = None   # training revenue series (pd.Series)
        self._avg     = None   # the single value used for all future predictions

    # ------------------------------------------------------------------ #
    # Fit
    # ------------------------------------------------------------------ #

    def fit(self, df):
        """
        Store the training series and compute the forecast average.

        Parameters
        ----------
        df : pd.DataFrame  — must have a 'revenue' column, DatetimeIndex

        Returns self (for chaining)
        """
        self._series = df["revenue"].copy()
        tail         = self._series.tail(self.window)
        self._avg    = float(tail.mean()) if len(tail) > 0 else 0.0
        return self

    # ------------------------------------------------------------------ #
    # Predict
    # ------------------------------------------------------------------ #

    def predict(self, periods):
        """
        Predict `periods` months after the end of the training data.

        Parameters
        ----------
        periods : int — number of future months to forecast

        Returns
        -------
        list[dict]  — [{period: "YYYY-MM", predicted: float}, ...]
        """
        if self._series is None:
            raise RuntimeError("Call fit() before predict().")

        last_period    = self._series.index[-1]
        future_periods = pd.date_range(
            start=last_period + pd.DateOffset(months=1),
            periods=periods,
            freq="MS",
        )
        avg_clipped = max(self._avg, 0.0)   # revenue cannot be negative

        return [
            {"period": p.strftime("%Y-%m"), "predicted": round(avg_clipped, 2)}
            for p in future_periods
        ]

    # ------------------------------------------------------------------ #
    # Evaluate (hold-out)
    # ------------------------------------------------------------------ #

    def evaluate(self, df, holdout_periods=3):
        """
        Evaluate forecast quality using a hold-out window.

        Trains on df[:-holdout_periods], predicts `holdout_periods` steps,
        compares predictions against df[-holdout_periods:].

        Parameters
        ----------
        holdout_periods : int — months to withhold from training

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
        Compute rolling SMA over the training series.
        Used as an in-sample fit line on the forecast chart.

        Returns
        -------
        list[dict] — [{period: "YYYY-MM", fitted: float}, ...]
        """
        if self._series is None:
            return []
        rolled = self._series.rolling(window=self.window, min_periods=1).mean()
        return [
            {"period": idx.strftime("%Y-%m"), "fitted": round(max(float(v), 0.0), 2)}
            for idx, v in rolled.items()
        ]
