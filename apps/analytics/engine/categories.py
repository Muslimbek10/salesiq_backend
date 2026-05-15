"""
Category Performance Engine
============================
Aggregates per-category revenue, profit, cost, transaction count,
and distinct product count for the category breakdown chart.

compute_category_performance(date_from, date_to)
  Returns each category's totals plus its revenue share.
"""
from django.db.models import Count, Sum

from apps.sales.models import Sale
from core.utils import calculate_gross_margin


def compute_category_performance(date_from, date_to):
    """
    Per-category performance for the selected date range.

    Returns
    -------
    list[dict] — ordered by total_revenue descending
    Each dict includes: category_id, category_name, total_revenue,
    total_profit, total_cost, gross_margin_pct, total_transactions,
    total_units, distinct_products_sold, revenue_share_pct
    """
    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .values("product__category_id", "product__category__category_name")
        .annotate(
            total_revenue=Sum("total_amount"),
            total_profit=Sum("total_profit"),
            total_cost=Sum("total_cost"),
            total_transactions=Count("id"),
            total_units=Sum("quantity"),
            distinct_products=Count("product_id", distinct=True),
        )
        .order_by("-total_revenue")
    )

    data          = list(rows)
    grand_revenue = sum(float(r["total_revenue"] or 0) for r in data)

    result = []
    for r in data:
        revenue = float(r["total_revenue"] or 0)
        cost    = float(r["total_cost"]    or 0)
        profit  = float(r["total_profit"]  or 0)
        result.append({
            "category_id":           r["product__category_id"],
            "category_name":         r["product__category__category_name"],
            "total_revenue":         round(revenue, 2),
            "total_profit":          round(profit, 2),
            "total_cost":            round(cost, 2),
            "gross_margin_pct":      calculate_gross_margin(revenue, cost),
            "total_transactions":    r["total_transactions"] or 0,
            "total_units":           int(r["total_units"] or 0),
            "distinct_products_sold": r["distinct_products"] or 0,
            "revenue_share_pct":     round(revenue / grand_revenue * 100, 2) if grand_revenue else 0.0,
        })
    return result
