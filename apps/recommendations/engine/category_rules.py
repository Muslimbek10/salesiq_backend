"""
Category Rules
==============
Two profitability-focused rules on product categories:

check_low_margin_categories(lookback_months, margin_threshold_pct)
  Categories whose gross margin % falls below the threshold are flagged
  for a COST_OPTIMIZATION recommendation (investigate pricing / supplier costs).

check_high_margin_categories(lookback_months, margin_threshold_pct)
  Categories with excellent margins get a CATEGORY_PROMOTION recommendation
  encouraging the business to expand investment in those lines.
"""
from django.db.models import Sum
from django.utils import timezone

from apps.recommendations.models import Recommendation
from apps.sales.models import Sale

R  = Recommendation
RT = R.RecommendationType
ET = R.EntityType
P  = R.Priority


def _category_financials(date_from, date_to):
    """
    Return {category_id: {revenue, cost, profit, margin_pct, category_name}}
    for categories with at least one sale in the window.
    """
    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .values("product__category_id", "product__category__category_name")
        .annotate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
        )
    )
    result = {}
    for r in rows:
        revenue = float(r["revenue"] or 0)
        cost    = float(r["cost"]    or 0)
        profit  = float(r["profit"]  or 0)
        margin  = round(profit / revenue * 100, 2) if revenue > 0 else 0.0
        result[r["product__category_id"]] = {
            "category_name": r["product__category__category_name"],
            "revenue":       revenue,
            "cost":          cost,
            "profit":        profit,
            "margin_pct":    margin,
        }
    return result


def _already_active(rec_type, category_id):
    return R.objects.filter(
        recommendation_type=rec_type,
        related_entity_type=ET.CATEGORY,
        related_entity_id=category_id,
        is_active=True,
    ).exists()


def _months_ago(months):
    today = timezone.now().date()
    year  = today.year + (today.month - months - 1) // 12
    month = (today.month - months - 1) % 12 + 1
    return today.replace(year=year, month=month, day=1)


# ---------------------------------------------------------------------------
# Rule: Low Margin Categories
# ---------------------------------------------------------------------------

def check_low_margin_categories(lookback_months=3, margin_threshold_pct=10.0):
    """
    Flag categories whose gross margin falls below the threshold.
    Low margins suggest pricing is too aggressive or cost of goods is too high.

    Parameters
    ----------
    margin_threshold_pct : float — margin % below which a category is flagged (default 10)

    Returns
    -------
    list[Recommendation]
    """
    today     = timezone.now().date()
    date_from = _months_ago(lookback_months)
    date_to   = today

    cat_map = _category_financials(date_from, date_to)
    created = []

    for category_id, info in cat_map.items():
        if info["margin_pct"] >= margin_threshold_pct or info["revenue"] <= 0:
            continue
        if _already_active(RT.COST_OPTIMIZATION, category_id):
            continue

        priority = P.HIGH if info["margin_pct"] < 5 else P.MEDIUM

        text = (
            f"Low-margin category alert: '{info['category_name']}' achieved only "
            f"{info['margin_pct']:.1f}% gross margin over the past {lookback_months} month(s) "
            f"(revenue: {info['revenue']:,.2f}, cost: {info['cost']:,.2f}, "
            f"profit: {info['profit']:,.2f}). "
            f"Review supplier costs and selling prices. "
            f"Consider negotiating better purchase terms or adjusting the pricing strategy."
        )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.COST_OPTIMIZATION,
            related_entity_type=ET.CATEGORY,
            related_entity_id=category_id,
            related_entity_name=info["category_name"],
            priority_level=priority,
        )
        created.append(rec)

    return created


# ---------------------------------------------------------------------------
# Rule: High Margin Categories
# ---------------------------------------------------------------------------

def check_high_margin_categories(lookback_months=3, margin_threshold_pct=35.0):
    """
    Identify categories with strong margins and recommend investing more.
    A high margin means the business is pricing well or sourcing cheaply —
    worth expanding product range and marketing spend in this category.

    Parameters
    ----------
    margin_threshold_pct : float — margin % above which a category is flagged (default 35)

    Returns
    -------
    list[Recommendation]
    """
    today     = timezone.now().date()
    date_from = _months_ago(lookback_months)
    date_to   = today

    cat_map = _category_financials(date_from, date_to)
    created = []

    for category_id, info in cat_map.items():
        if info["margin_pct"] < margin_threshold_pct or info["revenue"] <= 0:
            continue
        if _already_active(RT.CATEGORY_PROMOTION, category_id):
            continue

        text = (
            f"High-margin opportunity: '{info['category_name']}' achieved a "
            f"{info['margin_pct']:.1f}% gross margin over the past {lookback_months} month(s) "
            f"(revenue: {info['revenue']:,.2f}, profit: {info['profit']:,.2f}). "
            f"Consider expanding the product range in this category, increasing marketing "
            f"investment, and ensuring adequate stock to capture more demand."
        )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.CATEGORY_PROMOTION,
            related_entity_type=ET.CATEGORY,
            related_entity_id=category_id,
            related_entity_name=info["category_name"],
            priority_level=P.LOW,
        )
        created.append(rec)

    return created
