"""
Branch Performance Engine
=========================
Aggregates per-branch revenue, profit, cost, and transaction count
for the branch comparison table and chart.

compute_branch_performance(date_from, date_to)
  Returns each branch's totals plus its share of overall revenue.
"""
from django.db.models import Count, Sum

from apps.sales.models import Sale
from core.utils import calculate_gross_margin


def compute_branch_performance(date_from, date_to):
    """
    Per-branch performance for the selected date range.

    Returns
    -------
    list[dict] — ordered by total_revenue descending
    Each dict includes: branch_id, branch_name, location,
    total_revenue, total_profit, total_cost, gross_margin_pct,
    total_transactions, total_units, revenue_share_pct
    """
    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .values("branch_id", "branch__branch_name", "branch__location")
        .annotate(
            total_revenue=Sum("total_amount"),
            total_profit=Sum("total_profit"),
            total_cost=Sum("total_cost"),
            total_transactions=Count("id"),
            total_units=Sum("quantity"),
        )
        .order_by("-total_revenue")
    )

    data         = list(rows)
    grand_revenue = sum(float(r["total_revenue"] or 0) for r in data)

    result = []
    for r in data:
        revenue = float(r["total_revenue"] or 0)
        cost    = float(r["total_cost"]    or 0)
        profit  = float(r["total_profit"]  or 0)
        result.append({
            "branch_id":          r["branch_id"],
            "branch_name":        r["branch__branch_name"],
            "location":           r["branch__location"],
            "total_revenue":      round(revenue, 2),
            "total_profit":       round(profit, 2),
            "total_cost":         round(cost, 2),
            "gross_margin_pct":   calculate_gross_margin(revenue, cost),
            "total_transactions": r["total_transactions"] or 0,
            "total_units":        int(r["total_units"] or 0),
            "revenue_share_pct":  round(revenue / grand_revenue * 100, 2) if grand_revenue else 0.0,
        })
    return result
