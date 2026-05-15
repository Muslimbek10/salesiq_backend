"""
KPI Engine
==========
Computes dashboard KPI cards with period-over-period comparison.
All calculations use Django ORM aggregates — no pandas dependency here.

compute_dashboard_kpis(date_from, date_to)
  Returns the selected period's totals alongside the preceding equal-length
  period, plus percentage growth for each metric.
"""
from datetime import timedelta

from django.db.models import Avg, Count, Sum

from apps.sales.models import Sale
from core.utils import calculate_gross_margin, calculate_growth_rate


def _period_totals(date_from, date_to):
    """Return aggregate KPI totals for a given date range."""
    agg = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .aggregate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
            transactions=Count("id"),
            units=Sum("quantity"),
            avg_order=Avg("total_amount"),
        )
    )
    revenue = float(agg["revenue"] or 0)
    cost    = float(agg["cost"]    or 0)
    profit  = float(agg["profit"]  or 0)
    return {
        "total_revenue":      round(revenue, 2),
        "total_cost":         round(cost, 2),
        "total_profit":       round(profit, 2),
        "total_transactions": agg["transactions"] or 0,
        "total_units_sold":   int(agg["units"] or 0),
        "avg_order_value":    round(float(agg["avg_order"] or 0), 2),
        "gross_margin_pct":   calculate_gross_margin(revenue, cost),
    }


def compute_dashboard_kpis(date_from, date_to):
    """
    Compute KPI cards for the main dashboard.

    Comparison logic:
      The "previous period" is the same duration shifted immediately before
      date_from — e.g. if the window is 30 days, previous = prior 30 days.

    Returns
    -------
    dict with keys: period, previous_period, kpis
    Each KPI entry: {value, previous, growth}
    """
    delta_days = (date_to - date_from).days + 1
    prev_to    = date_from - timedelta(days=1)
    prev_from  = prev_to   - timedelta(days=delta_days - 1)

    current  = _period_totals(date_from, date_to)
    previous = _period_totals(prev_from, prev_to)

    def kpi(key):
        return {
            "value":    current[key],
            "previous": previous[key],
            "growth":   calculate_growth_rate(current[key], previous[key]),
        }

    return {
        "period":          {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "previous_period": {"from": prev_from.isoformat(), "to": prev_to.isoformat()},
        "kpis": {
            "total_revenue":      kpi("total_revenue"),
            "total_profit":       kpi("total_profit"),
            "total_cost":         kpi("total_cost"),
            "total_transactions": kpi("total_transactions"),
            "total_units_sold":   kpi("total_units_sold"),
            "avg_order_value":    kpi("avg_order_value"),
            "gross_margin_pct":   kpi("gross_margin_pct"),
        },
    }
