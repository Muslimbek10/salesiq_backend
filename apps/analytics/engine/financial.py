"""
Financial Analytics Engine
===========================
Monthly financial breakdown with cumulative totals and summary stats.

compute_financial_analytics(date_from, date_to)
  Returns a monthly series of revenue, cost, profit, and gross margin
  plus cumulative running totals, best/worst months, and period summary.
"""
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth

from apps.sales.models import Sale
from core.utils import calculate_gross_margin


def compute_financial_analytics(date_from, date_to):
    """
    Monthly financial breakdown for the selected date range.

    Returns
    -------
    dict with keys:
      period          — {from, to}
      monthly_series  — [{period, revenue, cost, profit, gross_margin_pct,
                          cumulative_revenue, cumulative_profit, transactions}]
      best_month      — the month with highest revenue
      worst_month     — the month with lowest revenue (among months with sales)
      totals          — period-level aggregates
    """
    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .annotate(month=TruncMonth("sale_date"))
        .values("month")
        .annotate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
            transactions=Count("id"),
        )
        .order_by("month")
    )

    # Build series with cumulative totals
    cumulative_revenue = 0.0
    cumulative_profit  = 0.0
    series = []
    for r in rows:
        revenue = float(r["revenue"] or 0)
        cost    = float(r["cost"]    or 0)
        profit  = float(r["profit"]  or 0)
        cumulative_revenue += revenue
        cumulative_profit  += profit
        series.append({
            "period":              r["month"].strftime("%Y-%m"),
            "revenue":             round(revenue, 2),
            "cost":                round(cost, 2),
            "profit":              round(profit, 2),
            "gross_margin_pct":    calculate_gross_margin(revenue, cost),
            "cumulative_revenue":  round(cumulative_revenue, 2),
            "cumulative_profit":   round(cumulative_profit, 2),
            "transactions":        r["transactions"] or 0,
        })

    best_month  = max(series, key=lambda x: x["revenue"]) if series else None
    worst_month = min(series, key=lambda x: x["revenue"]) if series else None

    # Single-pass totals for the whole period
    grand = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .aggregate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
        )
    )
    grand_revenue = float(grand["revenue"] or 0)
    grand_cost    = float(grand["cost"]    or 0)
    grand_profit  = float(grand["profit"]  or 0)

    return {
        "period":         {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "monthly_series": series,
        "best_month":     best_month,
        "worst_month":    worst_month,
        "totals": {
            "total_revenue":    round(grand_revenue, 2),
            "total_cost":       round(grand_cost, 2),
            "total_profit":     round(grand_profit, 2),
            "gross_margin_pct": calculate_gross_margin(grand_revenue, grand_cost),
        },
    }
