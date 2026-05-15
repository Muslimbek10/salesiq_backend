"""
Product Analytics Engine
========================
Provides three product-focused datasets:

compute_top_products(date_from, date_to, limit, metric)
  Ranks products by revenue, profit, or units sold.

compute_low_performing_products(date_from, date_to, limit)
  Ranks products by lowest total profit in the period.

compute_low_stock_products(limit)
  Returns active products at or below their minimum_stock_level,
  ordered by urgency (most critical first).
"""
from django.db.models import Count, F, Sum

from apps.products.models import Product
from apps.sales.models import Sale

# Maps API metric name → the annotation key used for ordering
_METRIC_ANNOTATION = {
    "revenue": "total_revenue",
    "profit":  "total_profit",
    "units":   "total_units",
}


def compute_top_products(date_from, date_to, limit=10, metric="revenue"):
    """
    Top-N products ranked by the selected metric.

    Parameters
    ----------
    metric : str  'revenue' | 'profit' | 'units'

    Returns
    -------
    list[dict]
    """
    order_by = f"-{_METRIC_ANNOTATION.get(metric, 'total_revenue')}"

    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .values(
            "product_id",
            "product__product_name",
            "product__sku",
            "product__category__category_name",
        )
        .annotate(
            total_revenue=Sum("total_amount"),
            total_profit=Sum("total_profit"),
            total_units=Sum("quantity"),
            total_transactions=Count("id"),
        )
        .order_by(order_by)[:limit]
    )

    return [
        {
            "product_id":         r["product_id"],
            "product_name":       r["product__product_name"],
            "sku":                r["product__sku"],
            "category_name":      r["product__category__category_name"],
            "total_revenue":      round(float(r["total_revenue"] or 0), 2),
            "total_profit":       round(float(r["total_profit"]  or 0), 2),
            "total_units":        int(r["total_units"] or 0),
            "total_transactions": r["total_transactions"] or 0,
        }
        for r in rows
    ]


def compute_low_performing_products(date_from, date_to, limit=10):
    """
    Bottom-N products by total profit (lowest profit first).
    Only considers products that had at least one sale in the period.

    Returns
    -------
    list[dict] with profit_margin_pct included
    """
    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .values(
            "product_id",
            "product__product_name",
            "product__sku",
            "product__category__category_name",
        )
        .annotate(
            total_revenue=Sum("total_amount"),
            total_profit=Sum("total_profit"),
            total_units=Sum("quantity"),
        )
        .filter(total_revenue__gt=0)
        .order_by("total_profit")[:limit]
    )

    result = []
    for r in rows:
        revenue = float(r["total_revenue"] or 0)
        profit  = float(r["total_profit"]  or 0)
        margin  = round(profit / revenue * 100, 2) if revenue > 0 else 0.0
        result.append({
            "product_id":        r["product_id"],
            "product_name":      r["product__product_name"],
            "sku":               r["product__sku"],
            "category_name":     r["product__category__category_name"],
            "total_revenue":     round(revenue, 2),
            "total_profit":      round(profit, 2),
            "profit_margin_pct": margin,
            "total_units":       int(r["total_units"] or 0),
        })
    return result


def compute_low_stock_products(limit=20):
    """
    Active products at or below their minimum_stock_level, ordered by
    ascending stock_quantity so the most urgent appear first.

    Returns
    -------
    list[dict]
    """
    products = (
        Product.objects
        .select_related("category")
        .filter(is_active=True, stock_quantity__lte=F("minimum_stock_level"))
        .order_by("stock_quantity")[:limit]
    )
    return [
        {
            "product_id":          p.pk,
            "product_name":        p.product_name,
            "sku":                 p.sku,
            "category_name":       p.category.category_name,
            "stock_quantity":      p.stock_quantity,
            "minimum_stock_level": p.minimum_stock_level,
            "stock_status":        p.stock_status.value,
            "shortage":            p.stock_shortage,
        }
        for p in products
    ]
