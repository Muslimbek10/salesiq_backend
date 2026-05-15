"""
Data Preprocessor
=================
Loads sales history from the database into a Pandas DataFrame
ready for the forecasting models.

Key responsibilities:
  - Query the sales table filtered by target (overall / product / category / branch)
  - Aggregate to monthly revenue and units via TruncMonth
  - Exclude the current partial month (only complete calendar months are used)
  - Reindex to a complete monthly date range, filling silent months with 0
  - Cap revenue outliers using the IQR method
  - Validate that there is enough history to train a model

Public API
----------
load_monthly_revenue(target_type, target_id, months_back)  → pd.DataFrame
validate_series(df, min_periods)                           → pd.DataFrame (or raises)
"""
import logging
from datetime import date

import pandas as pd
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.forecasting.models import Forecast
from apps.sales.models import Sale

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cap_outliers(series, iqr_multiplier=3.0):
    """
    Cap extreme revenue months using the IQR fence method.

    A month with revenue above Q3 + 3×IQR (or below Q1 - 3×IQR) is likely
    a one-time event (bulk corporate order, data error) that would distort
    the model's learned trend and seasonal pattern.

    The multiplier is set to 3.0 (rather than the usual 1.5) to be
    conservative — we only clip genuinely extreme outliers, not ordinary
    high-sales months.

    Parameters
    ----------
    series          : pd.Series  — monthly revenue values
    iqr_multiplier  : float      — fence width (default 3.0)

    Returns
    -------
    pd.Series — capped series (values are modified, index unchanged)
    """
    if len(series) < 4:
        return series          # too few points to compute meaningful quartiles

    q1  = series.quantile(0.25)
    q3  = series.quantile(0.75)
    iqr = q3 - q1

    if iqr == 0:
        return series          # constant series — nothing to clip

    lower = max(0.0, q1 - iqr_multiplier * iqr)   # revenue is always ≥ 0
    upper = q3 + iqr_multiplier * iqr

    clipped = series.clip(lower=lower, upper=upper)

    n_capped = (series != clipped).sum()
    if n_capped > 0:
        logger.info(
            "Outlier capping: %d month(s) adjusted to [%.2f, %.2f]",
            n_capped, lower, upper,
        )

    return clipped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_monthly_revenue(target_type, target_id=None, months_back=24):
    """
    Load monthly revenue aggregates from the database.

    Only COMPLETE calendar months are included.  The current partial month
    is excluded because its artificially low revenue would bias the trend
    (e.g. 8 days into April looks like a very bad month).

    Parameters
    ----------
    target_type : str
        One of Forecast.TargetType values:
        'overall' | 'product' | 'category' | 'branch'
    target_id   : int | None
        PK of the target entity. None for 'overall'.
    months_back : int
        How many complete months of history to include (default 24).

    Returns
    -------
    pd.DataFrame
        Columns : revenue (float), units (float)
        Index   : period (DatetimeIndex, monthly start, sorted ascending)
        Missing months within the range are filled with 0.
        Revenue outliers are capped via IQR fencing.
    """
    today = timezone.now().date()

    # ── Exclusive upper bound: first day of the CURRENT month ──────────────
    # This guarantees only complete months enter the training set.
    # E.g. on 2026-04-08 we exclude April 2026 (partial) and use up to
    # March 2026 (the last complete month).
    end_exclusive = today.replace(day=1)

    # ── Start date: first day of the month `months_back` ago ───────────────
    # Using Python floor-division which is well-defined for negative numbers.
    offset      = today.month - months_back - 1
    start_year  = today.year  + offset // 12
    start_month = offset % 12 + 1
    start       = date(start_year, start_month, 1)

    qs = Sale.objects.filter(
        sale_date__gte=start,
        sale_date__lt=end_exclusive,      # ← BUG FIX: exclude current partial month
    )

    # Apply target filter
    if target_type == Forecast.TargetType.PRODUCT and target_id:
        qs = qs.filter(product_id=target_id)
    elif target_type == Forecast.TargetType.CATEGORY and target_id:
        qs = qs.filter(product__category_id=target_id)
    elif target_type == Forecast.TargetType.BRANCH and target_id:
        qs = qs.filter(branch_id=target_id)
    # TargetType.OVERALL → no additional filter

    rows = (
        qs
        .annotate(period=TruncMonth("sale_date"))
        .values("period")
        .annotate(revenue=Sum("total_amount"), units=Sum("quantity"))
        .order_by("period")
    )

    raw = list(rows)
    if not raw:
        return pd.DataFrame(columns=["revenue", "units"])

    df = pd.DataFrame(raw)
    df["period"]  = pd.to_datetime(df["period"])
    df = df.set_index("period").sort_index()
    df["revenue"] = df["revenue"].astype(float).fillna(0.0)
    df["units"]   = df["units"].astype(float).fillna(0.0)

    # Ensure a contiguous monthly range — silent months get 0 revenue
    full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq="MS")
    df = df.reindex(full_range, fill_value=0.0)
    df.index.name = "period"

    # Cap extreme outlier months to prevent model distortion
    df["revenue"] = _cap_outliers(df["revenue"])

    return df


def validate_series(df, min_periods=6):
    """
    Raise ValueError if the DataFrame has fewer rows than min_periods
    or if revenue is entirely zero (no real sales data).

    Parameters
    ----------
    df          : pd.DataFrame  — output of load_monthly_revenue
    min_periods : int           — minimum non-empty rows required

    Returns
    -------
    df unchanged (so callers can chain: df = validate_series(df))

    Raises
    ------
    ValueError — series is too short or has no positive revenue
    """
    actual_periods = len(df)
    if df.empty or actual_periods < min_periods:
        raise ValueError(
            f"Insufficient historical data: need at least {min_periods} months "
            f"of sales records, but only {actual_periods} month(s) found. "
            "Add more historical data or reduce the minimum window."
        )

    # Guard against all-zero series (entity with no sales at all)
    if df["revenue"].sum() == 0:
        raise ValueError(
            "No revenue recorded for this target in the selected period. "
            "A forecast cannot be generated from an empty sales history."
        )

    return df
