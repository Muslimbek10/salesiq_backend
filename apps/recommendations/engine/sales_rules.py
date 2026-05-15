"""
Sales Rules
===========
Three rule groups derived from sales trend analysis:

check_declining_products(lookback_months, decline_threshold_pct)
  Compares each product's revenue in the last N months against the
  preceding N months. Products that declined more than the threshold
  receive a DECLINING_SALES recommendation.

check_high_performers(lookback_months, growth_threshold_pct)
  Products with significant revenue growth get a HIGH_PERFORMER
  recommendation advising the user to capitalise on momentum.

check_forecast_risk(decline_threshold_pct)
  Reads the latest forecast for each target. If the predicted average
  is more than threshold% below the recent actual average, raises a
  FORECAST_RISK recommendation.
"""
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.forecasting.models import Forecast
from apps.recommendations.models import Recommendation
from apps.sales.models import Sale

R  = Recommendation
RT = R.RecommendationType
ET = R.EntityType
P  = R.Priority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _period_revenue_by_product(date_from, date_to):
    """Return {product_id: revenue} for the date window."""
    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .values("product_id", "product__product_name", "product__sku")
        .annotate(revenue=Sum("total_amount"))
    )
    return {
        r["product_id"]: {
            "revenue":      float(r["revenue"] or 0),
            "product_name": r["product__product_name"],
            "sku":          r["product__sku"],
        }
        for r in rows
    }


def _already_active(rec_type, entity_type, entity_id):
    return R.objects.filter(
        recommendation_type=rec_type,
        related_entity_type=entity_type,
        related_entity_id=entity_id,
        is_active=True,
    ).exists()


def _months_ago(months):
    today = timezone.now().date()
    year  = today.year + (today.month - months - 1) // 12
    month = (today.month - months - 1) % 12 + 1
    return today.replace(year=year, month=month, day=1)


# ---------------------------------------------------------------------------
# Rule: Declining Products
# ---------------------------------------------------------------------------

def check_declining_products(lookback_months=2, decline_threshold_pct=20.0):
    """
    Flag products whose revenue dropped by more than `decline_threshold_pct`
    versus the preceding equal-length period.

    Parameters
    ----------
    lookback_months        : int   — length of each comparison window (default 2)
    decline_threshold_pct  : float — minimum % decline to trigger (default 20)

    Returns
    -------
    list[Recommendation]
    """
    today = timezone.now().date()

    current_end   = today
    current_start = _months_ago(lookback_months)
    prev_end      = current_start - timedelta(days=1)
    prev_start    = _months_ago(lookback_months * 2)

    current_map = _period_revenue_by_product(current_start, current_end)
    prev_map    = _period_revenue_by_product(prev_start,    prev_end)

    created = []

    for product_id, cur in current_map.items():
        prv_revenue = prev_map.get(product_id, {}).get("revenue", 0)
        cur_revenue = cur["revenue"]

        if prv_revenue <= 0 or cur_revenue <= 0:
            continue

        decline_pct = (prv_revenue - cur_revenue) / prv_revenue * 100
        if decline_pct < decline_threshold_pct:
            continue

        if _already_active(RT.DECLINING_SALES, ET.PRODUCT, product_id):
            continue

        priority = P.HIGH if decline_pct >= 40 else P.MEDIUM
        text = (
            f"Declining sales detected for '{cur['product_name']}' (SKU: {cur['sku']}): "
            f"revenue fell {decline_pct:.1f}% over the past {lookback_months} month(s) "
            f"(from {prv_revenue:,.2f} to {cur_revenue:,.2f}). "
            f"{'Urgent review recommended — consider promotions, pricing adjustments, or discontinuation.' if decline_pct >= 40 else 'Monitor closely and consider a promotional campaign to stimulate demand.'}"
        )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.DECLINING_SALES,
            related_entity_type=ET.PRODUCT,
            related_entity_id=product_id,
            related_entity_name=cur["product_name"],
            priority_level=priority,
        )
        created.append(rec)

    return created


# ---------------------------------------------------------------------------
# Rule: High Performers
# ---------------------------------------------------------------------------

def check_high_performers(lookback_months=2, growth_threshold_pct=30.0):
    """
    Identify products with significant revenue growth.
    Generates HIGH_PERFORMER recommendations encouraging the user to
    capitalise on momentum (ensure stock, promote further, etc.).

    Returns
    -------
    list[Recommendation]
    """
    today = timezone.now().date()

    current_end   = today
    current_start = _months_ago(lookback_months)
    prev_end      = current_start - timedelta(days=1)
    prev_start    = _months_ago(lookback_months * 2)

    current_map = _period_revenue_by_product(current_start, current_end)
    prev_map    = _period_revenue_by_product(prev_start,    prev_end)

    created = []

    for product_id, cur in current_map.items():
        prv_revenue = prev_map.get(product_id, {}).get("revenue", 0)
        cur_revenue = cur["revenue"]

        if prv_revenue <= 0 or cur_revenue <= 0:
            continue

        growth_pct = (cur_revenue - prv_revenue) / prv_revenue * 100
        if growth_pct < growth_threshold_pct:
            continue

        if _already_active(RT.HIGH_PERFORMER, ET.PRODUCT, product_id):
            continue

        text = (
            f"High performer: '{cur['product_name']}' (SKU: {cur['sku']}) grew revenue "
            f"{growth_pct:.1f}% over the past {lookback_months} month(s) "
            f"(from {prv_revenue:,.2f} to {cur_revenue:,.2f}). "
            f"Ensure sufficient stock to meet demand and consider expanding marketing efforts."
        )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.HIGH_PERFORMER,
            related_entity_type=ET.PRODUCT,
            related_entity_id=product_id,
            related_entity_name=cur["product_name"],
            priority_level=P.LOW,
        )
        created.append(rec)

    return created


# ---------------------------------------------------------------------------
# Rule: Forecast Risk
# ---------------------------------------------------------------------------

def check_forecast_risk(decline_threshold_pct=15.0):
    """
    Read the most recent forecast for each target. If the average predicted
    revenue is more than `decline_threshold_pct` below the average of the
    historical actuals in that forecast's data, raise a FORECAST_RISK
    recommendation.

    Parameters
    ----------
    decline_threshold_pct : float — threshold % decline to flag (default 15)

    Returns
    -------
    list[Recommendation]
    """
    # Only inspect the latest forecast per (target_type, target_id, model_name)
    recent_forecasts = list(Forecast.objects.latest_per_target())
    created = []

    for forecast in recent_forecasts:
        data = forecast.forecast_data
        if not data:
            continue

        actual_values    = [d["actual"]    for d in data if d.get("actual")    is not None]
        predicted_values = [d["predicted"] for d in data if d.get("predicted") is not None]

        if not actual_values or not predicted_values:
            continue

        avg_actual    = sum(actual_values)    / len(actual_values)
        avg_predicted = sum(predicted_values) / len(predicted_values)

        if avg_actual <= 0:
            continue

        decline_pct = (avg_actual - avg_predicted) / avg_actual * 100
        if decline_pct < decline_threshold_pct:
            continue

        # Map forecast target type → recommendation entity type
        target_entity_map = {
            Forecast.TargetType.PRODUCT:  ET.PRODUCT,
            Forecast.TargetType.CATEGORY: ET.CATEGORY,
            Forecast.TargetType.BRANCH:   ET.BRANCH,
            Forecast.TargetType.OVERALL:  ET.OVERALL,
        }
        entity_type = target_entity_map.get(forecast.forecast_target_type, ET.OVERALL)
        entity_id   = forecast.target_id  # None for OVERALL

        if _already_active(RT.FORECAST_RISK, entity_type, entity_id):
            continue

        priority = P.HIGH if decline_pct >= 30 else P.MEDIUM
        model_label = forecast.get_model_name_display()
        target_label = (
            f"target #{entity_id}"
            if entity_id else
            f"overall business ({forecast.get_forecast_target_type_display()})"
        )

        text = (
            f"Forecast risk detected for {target_label}: "
            f"the {model_label} model predicts an average revenue of {avg_predicted:,.2f} "
            f"per month, which is {decline_pct:.1f}% below recent actuals ({avg_actual:,.2f}). "
            f"Review pricing, marketing, and inventory strategies proactively."
        )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.FORECAST_RISK,
            related_entity_type=entity_type,
            related_entity_id=entity_id,
            related_entity_name=target_label,
            priority_level=priority,
        )
        created.append(rec)

    return created
