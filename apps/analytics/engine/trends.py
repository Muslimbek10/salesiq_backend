"""
Sales Trend Engine
==================
Aggregates sales into a time series at daily / weekly / monthly granularity.
Used for the revenue and profit line charts on the dashboard and analytics pages.

compute_sales_trend(date_from, date_to, granularity)
  Returns a list of period dicts ordered chronologically.
"""
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek

from apps.sales.models import Sale

_TRUNC = {
    "daily":   TruncDay,
    "weekly":  TruncWeek,
    "monthly": TruncMonth,
}

_DATE_FMT = {
    "daily":   "%Y-%m-%d",
    "weekly":  "%Y-%m-%d",   # start-of-week date
    "monthly": "%Y-%m",
}


def compute_sales_trend(date_from, date_to, granularity="monthly"):
    """
    Aggregate sales into a time series.

    Parameters
    ----------
    date_from, date_to : date  — inclusive date range
    granularity        : str   — 'daily' | 'weekly' | 'monthly'

    Returns
    -------
    list[dict] — [{period, revenue, cost, profit, transactions, units_sold}, ...]
    """
    Trunc  = _TRUNC.get(granularity, TruncMonth)
    fmt    = _DATE_FMT.get(granularity, "%Y-%m")

    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .annotate(period=Trunc("sale_date"))
        .values("period")
        .annotate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
            transactions=Count("id"),
            units_sold=Sum("quantity"),
        )
        .order_by("period")
    )

    return [
        {
            "period":       r["period"].strftime(fmt),
            "revenue":      round(float(r["revenue"]  or 0), 2),
            "cost":         round(float(r["cost"]     or 0), 2),
            "profit":       round(float(r["profit"]   or 0), 2),
            "transactions": r["transactions"] or 0,
            "units_sold":   int(r["units_sold"] or 0),
        }
        for r in rows
    ]
