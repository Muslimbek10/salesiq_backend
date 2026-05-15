"""
Forecast Accuracy Metrics
==========================
Stateless functions for evaluating forecast quality.

All functions accept parallel lists of equal length.
They return None gracefully when inputs are invalid or empty
rather than raising, so callers don't need try/except around every call.

Functions
---------
calculate_mae(actual, predicted)   → float | None
calculate_rmse(actual, predicted)  → float | None
calculate_mape(actual, predicted)  → float | None
"""
import math


def calculate_mae(actual, predicted):
    """
    Mean Absolute Error — average magnitude of prediction errors.

    MAE = (1/n) * Σ |actual_i - predicted_i|

    Lower is better. Same unit as the target variable (e.g. currency).

    Returns
    -------
    float (rounded to 4 dp) | None if inputs are invalid
    """
    if not actual or not predicted or len(actual) != len(predicted):
        return None
    n = len(actual)
    total = sum(abs(float(a) - float(p)) for a, p in zip(actual, predicted))
    return round(total / n, 4)


def calculate_rmse(actual, predicted):
    """
    Root Mean Squared Error — penalises large errors more than MAE.

    RMSE = sqrt( (1/n) * Σ (actual_i - predicted_i)² )

    Lower is better. Same unit as the target variable.

    Returns
    -------
    float (rounded to 4 dp) | None if inputs are invalid
    """
    if not actual or not predicted or len(actual) != len(predicted):
        return None
    n = len(actual)
    mse = sum((float(a) - float(p)) ** 2 for a, p in zip(actual, predicted)) / n
    return round(math.sqrt(mse), 4)


def calculate_mape(actual, predicted):
    """
    Mean Absolute Percentage Error.

    MAPE = (1/n) * Σ |actual_i - predicted_i| / actual_i  * 100

    Returns a percentage value (e.g. 5.3 means 5.3% average error).
    Returns None if any actual value is 0 (would cause division by zero).

    Returns
    -------
    float (rounded to 4 dp) | None
    """
    if not actual or not predicted or len(actual) != len(predicted):
        return None
    pairs = [(float(a), float(p)) for a, p in zip(actual, predicted) if a != 0]
    if not pairs:
        return None
    pct_errors = [abs((a - p) / a) for a, p in pairs]
    return round(sum(pct_errors) / len(pct_errors) * 100, 4)
