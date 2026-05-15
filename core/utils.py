"""
Shared Utility Functions
Used across analytics, forecasting, and report modules.
"""
from datetime import date, timedelta

from django.utils import timezone


# ============================================================
# DATE HELPERS
# ============================================================

def date_range_from_params(request):
    """
    Extract and validate date_from / date_to from request query params.

    Returns:
        (date_from, date_to) as date objects.
        Defaults to the last 12 months if not provided.

    Usage:
        date_from, date_to = date_range_from_params(request)
    """
    today = timezone.now().date()
    default_from = today.replace(day=1) - timedelta(days=365)
    default_to = today

    date_from_str = request.query_params.get("date_from", None)
    date_to_str = request.query_params.get("date_to", None)

    date_from = _parse_date(date_from_str) or default_from
    date_to = _parse_date(date_to_str) or default_to

    # Ensure date_from is not after date_to
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    return date_from, date_to


def _parse_date(value):
    """
    Parse a date string in YYYY-MM-DD format.
    Returns None if the string is invalid or missing.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def get_month_series(months_back=12):
    """
    Returns a list of (year, month) tuples for the last N months,
    starting from the oldest and ending with the current month.

    Example for months_back=3 if today is 2025-09:
        [(2025, 7), (2025, 8), (2025, 9)]
    """
    today = timezone.now().date()
    months = []

    for i in range(months_back - 1, -1, -1):
        # Subtract i months from today
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        months.append((year, month))

    return months


# ============================================================
# MATH HELPERS
# ============================================================

def safe_division(numerator, denominator):
    """
    Divide two numbers without raising ZeroDivisionError.
    Returns 0.0 if the denominator is zero.

    Used for margin and growth rate calculations.
    """
    if not denominator:
        return 0.0
    return numerator / denominator


def calculate_growth_rate(current, previous):
    """
    Calculate percentage growth between two values.

    Returns:
        float: growth rate as a percentage (e.g. 12.5 means +12.5%)
               Positive = growth, negative = decline.
               Returns 0.0 if previous value is zero.
    """
    if not previous:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def calculate_gross_margin(revenue, cost):
    """
    Calculate gross margin percentage.

    Formula: (revenue - cost) / revenue * 100
    Returns 0.0 if revenue is zero.
    """
    if not revenue:
        return 0.0
    return round(safe_division(revenue - cost, revenue) * 100, 2)


# ============================================================
# FORMATTING HELPERS
# ============================================================

def format_currency(value):
    """
    Round a float to 2 decimal places for currency display.
    Safely handles None values by returning 0.0.
    """
    if value is None:
        return 0.0
    return round(float(value), 2)


def format_percentage(value):
    """
    Round a float to 2 decimal places for percentage display.
    """
    if value is None:
        return 0.0
    return round(float(value), 2)


def int_or_zero(value):
    """
    Safely convert a value to int. Returns 0 if None or invalid.
    """
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
