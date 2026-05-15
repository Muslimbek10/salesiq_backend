"""
Report Generator Helpers
========================
Pure query functions shared by the report views.
All functions return plain Python lists/dicts — no serializer overhead.
"""
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncYear

from apps.sales.models import Sale
from core.utils import calculate_gross_margin, calculate_growth_rate


# ---------------------------------------------------------------------------
# Time-series helpers
# ---------------------------------------------------------------------------

def daily_series(date_from, date_to):
    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .annotate(day=TruncDay("sale_date"))
        .values("day")
        .annotate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
            transactions=Count("id"),
            units=Sum("quantity"),
        )
        .order_by("day")
    )
    return [
        {
            "date":         r["day"].strftime("%Y-%m-%d"),
            "revenue":      round(float(r["revenue"] or 0), 2),
            "cost":         round(float(r["cost"]    or 0), 2),
            "profit":       round(float(r["profit"]  or 0), 2),
            "transactions": r["transactions"] or 0,
            "units":        int(r["units"] or 0),
        }
        for r in rows
    ]


def monthly_series(date_from, date_to):
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
            units=Sum("quantity"),
        )
        .order_by("month")
    )
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
            "month":               r["month"].strftime("%Y-%m"),
            "revenue":             round(revenue, 2),
            "cost":                round(cost, 2),
            "profit":              round(profit, 2),
            "gross_margin_pct":    calculate_gross_margin(revenue, cost),
            "transactions":        r["transactions"] or 0,
            "units":               int(r["units"] or 0),
            "cumulative_revenue":  round(cumulative_revenue, 2),
            "cumulative_profit":   round(cumulative_profit, 2),
        })
    return series


def yearly_comparison():
    rows = (
        Sale.objects
        .annotate(year=TruncYear("sale_date"))
        .values("year")
        .annotate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
            transactions=Count("id"),
            units=Sum("quantity"),
        )
        .order_by("year")
    )
    data = list(rows)
    result = []
    for i, r in enumerate(data):
        revenue = float(r["revenue"] or 0)
        cost    = float(r["cost"]    or 0)
        profit  = float(r["profit"]  or 0)
        prev_revenue = float(data[i - 1]["revenue"] or 0) if i > 0 else None
        result.append({
            "year":             r["year"].year,
            "revenue":          round(revenue, 2),
            "cost":             round(cost, 2),
            "profit":           round(profit, 2),
            "gross_margin_pct": calculate_gross_margin(revenue, cost),
            "transactions":     r["transactions"] or 0,
            "units":            int(r["units"] or 0),
            "revenue_growth":   calculate_growth_rate(revenue, prev_revenue) if prev_revenue is not None else None,
        })
    return result


# ---------------------------------------------------------------------------
# Dimensional helpers
# ---------------------------------------------------------------------------

def branch_performance_table(date_from, date_to):
    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .values("branch_id", "branch__branch_name", "branch__location")
        .annotate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
            transactions=Count("id"),
            units=Sum("quantity"),
        )
        .order_by("-revenue")
    )
    data          = list(rows)
    grand_revenue = sum(float(r["revenue"] or 0) for r in data)
    result = []
    for r in data:
        revenue = float(r["revenue"] or 0)
        cost    = float(r["cost"]    or 0)
        profit  = float(r["profit"]  or 0)
        result.append({
            "branch_id":        r["branch_id"],
            "branch_name":      r["branch__branch_name"],
            "location":         r["branch__location"],
            "revenue":          round(revenue, 2),
            "cost":             round(cost, 2),
            "profit":           round(profit, 2),
            "gross_margin_pct": calculate_gross_margin(revenue, cost),
            "transactions":     r["transactions"] or 0,
            "units":            int(r["units"] or 0),
            "revenue_share_pct": round(revenue / grand_revenue * 100, 2) if grand_revenue else 0.0,
        })
    return result


def product_performance_table(date_from, date_to, limit=20):
    """Returns (top_products, bottom_products) each as list[dict]."""
    base = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .values(
            "product_id",
            "product__product_name",
            "product__sku",
            "product__category__category_name",
        )
        .annotate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
            transactions=Count("id"),
            units=Sum("quantity"),
        )
    )

    def serialise(row):
        revenue = float(row["revenue"] or 0)
        cost    = float(row["cost"]    or 0)
        profit  = float(row["profit"]  or 0)
        return {
            "product_id":    row["product_id"],
            "product_name":  row["product__product_name"],
            "sku":           row["product__sku"],
            "category":      row["product__category__category_name"],
            "revenue":       round(revenue, 2),
            "cost":          round(cost, 2),
            "profit":        round(profit, 2),
            "margin_pct":    calculate_gross_margin(revenue, cost),
            "transactions":  row["transactions"] or 0,
            "units":         int(row["units"] or 0),
        }

    top    = [serialise(r) for r in base.order_by("-revenue")[:limit]]
    bottom = [serialise(r) for r in base.filter(revenue__gt=0).order_by("profit")[:limit]]
    return top, bottom
