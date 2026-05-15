"""
Alert Generator
===============
Generates lightweight Alert records for threshold-based system conditions.
Alerts are "something is wrong right now" — the recommendation engine turns
them into "here is what to do about it."

Each generator function:
  1. Queries the relevant data.
  2. Checks Alert.already_active() for deduplication before creating.
  3. Creates Alert records and returns the list of newly created instances.

Generators
----------
generate_low_stock_alerts()
  One alert per out-of-stock or critically low product.

generate_declining_sales_alerts(lookback_months, decline_threshold_pct)
  Alerts for products whose revenue dropped significantly vs prior period.

generate_branch_underperformance_alerts(lookback_months, threshold_pct)
  Alerts for branches below peer average or in sharp decline.

generate_sales_drop_alerts(days, drop_threshold_pct)
  Week-over-week or configurable-period overall sales drop alert.

generate_forecast_risk_alerts(decline_threshold_pct)
  Alerts when a stored forecast predicts a significant revenue decline.

generate_high_demand_alerts(lookback_months, growth_threshold_pct)
  Positive signal — products with fast-growing demand need stock attention.

run_all_alert_generators(**config)
  Calls all generators in one atomic transaction. Returns a summary dict.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.alerts.models import Alert
from apps.forecasting.models import Forecast
from apps.products.models import Product
from apps.sales.models import Sale

logger = logging.getLogger(__name__)

A  = Alert
AT = A.AlertType
ET = A.EntityType
P  = A.Priority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _months_ago(months):
    today = timezone.now().date()
    year  = today.year + (today.month - months - 1) // 12
    month = (today.month - months - 1) % 12 + 1
    return today.replace(year=year, month=month, day=1)


def _branch_revenues(date_from, date_to):
    rows = (
        Sale.objects
        .filter(sale_date__gte=date_from, sale_date__lte=date_to)
        .values("branch_id", "branch__branch_name")
        .annotate(revenue=Sum("total_amount"))
    )
    return {
        r["branch_id"]: {
            "revenue":     float(r["revenue"] or 0),
            "branch_name": r["branch__branch_name"],
        }
        for r in rows
    }


def _product_revenues(date_from, date_to):
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


# ---------------------------------------------------------------------------
# Generator: Low Stock
# ---------------------------------------------------------------------------

def generate_low_stock_alerts():
    """
    Create LOW_STOCK alerts for active products at or below minimum stock level.
    Deduplication: skips products that already have an active LOW_STOCK alert.
    """
    from django.db.models import F
    products = (
        Product.objects
        .filter(is_active=True, stock_quantity__lte=F("minimum_stock_level"))
        .order_by("stock_quantity")
    )

    created = []
    for p in products:
        if A.already_active(AT.LOW_STOCK, ET.PRODUCT, p.pk):
            continue

        priority = P.HIGH if p.stock_quantity <= 0 else P.MEDIUM
        message  = (
            f"{'OUT OF STOCK' if p.stock_quantity <= 0 else 'Low stock'}: "
            f"'{p.product_name}' (SKU: {p.sku}) — "
            f"{p.stock_quantity} units remaining (minimum: {p.minimum_stock_level})."
        )

        alert = A.objects.create(
            alert_type=AT.LOW_STOCK,
            alert_message=message,
            priority_level=priority,
            related_entity_type=ET.PRODUCT,
            related_entity_id=p.pk,
            related_entity_name=p.product_name,
        )
        created.append(alert)

    return created


# ---------------------------------------------------------------------------
# Generator: Declining Sales (per product)
# ---------------------------------------------------------------------------

def generate_declining_sales_alerts(lookback_months=2, decline_threshold_pct=25.0):
    """
    Alert for products whose revenue dropped more than the threshold
    vs the preceding equal-length window.
    """
    today = timezone.now().date()

    current_start = _months_ago(lookback_months)
    prev_end      = current_start - timedelta(days=1)
    prev_start    = _months_ago(lookback_months * 2)

    current_map = _product_revenues(current_start, today)
    prev_map    = _product_revenues(prev_start, prev_end)

    created = []
    for product_id, cur in current_map.items():
        prv = prev_map.get(product_id, {}).get("revenue", 0)
        if prv <= 0 or cur["revenue"] <= 0:
            continue

        decline_pct = (prv - cur["revenue"]) / prv * 100
        if decline_pct < decline_threshold_pct:
            continue

        if A.already_active(AT.DECLINING_SALES, ET.PRODUCT, product_id):
            continue

        priority = P.HIGH if decline_pct >= 40 else P.MEDIUM
        message  = (
            f"Sales decline: '{cur['product_name']}' (SKU: {cur['sku']}) "
            f"revenue fell {decline_pct:.1f}% vs the prior {lookback_months}-month period "
            f"({prv:,.2f} → {cur['revenue']:,.2f})."
        )

        alert = A.objects.create(
            alert_type=AT.DECLINING_SALES,
            alert_message=message,
            priority_level=priority,
            related_entity_type=ET.PRODUCT,
            related_entity_id=product_id,
            related_entity_name=cur["product_name"],
        )
        created.append(alert)

    return created


# ---------------------------------------------------------------------------
# Generator: Branch Underperformance
# ---------------------------------------------------------------------------

def generate_branch_underperformance_alerts(lookback_months=3, threshold_pct=70.0):
    """
    Alert for branches earning below `threshold_pct` of the peer average.
    """
    today     = timezone.now().date()
    date_from = _months_ago(lookback_months)

    branch_map = _branch_revenues(date_from, today)
    if len(branch_map) < 2:
        return []

    revenues  = [v["revenue"] for v in branch_map.values()]
    avg_rev   = sum(revenues) / len(revenues)
    threshold = avg_rev * threshold_pct / 100

    created = []
    for branch_id, info in branch_map.items():
        if info["revenue"] >= threshold:
            continue
        if A.already_active(AT.BRANCH_UNDERPERFORMANCE, ET.BRANCH, branch_id):
            continue

        gap_pct  = (avg_rev - info["revenue"]) / avg_rev * 100 if avg_rev > 0 else 0
        priority = P.HIGH if info["revenue"] < avg_rev * 0.5 else P.MEDIUM
        message  = (
            f"Branch underperformance: '{info['branch_name']}' revenue "
            f"({info['revenue']:,.2f}) is {gap_pct:.1f}% below the branch average "
            f"({avg_rev:,.2f}) over the past {lookback_months} month(s)."
        )

        alert = A.objects.create(
            alert_type=AT.BRANCH_UNDERPERFORMANCE,
            alert_message=message,
            priority_level=priority,
            related_entity_type=ET.BRANCH,
            related_entity_id=branch_id,
            related_entity_name=info["branch_name"],
        )
        created.append(alert)

    return created


# ---------------------------------------------------------------------------
# Generator: Overall Sales Drop
# ---------------------------------------------------------------------------

def generate_sales_drop_alerts(days=14, drop_threshold_pct=20.0):
    """
    Alert when overall company revenue dropped more than the threshold
    vs the immediately preceding equal-length window.
    """
    today = timezone.now().date()

    current_start = today - timedelta(days=days)
    prev_end      = current_start - timedelta(days=1)
    prev_start    = prev_end - timedelta(days=days - 1)

    def period_revenue(d_from, d_to):
        agg = Sale.objects.filter(
            sale_date__gte=d_from, sale_date__lte=d_to
        ).aggregate(revenue=Sum("total_amount"))
        return float(agg["revenue"] or 0)

    current_rev = period_revenue(current_start, today)
    prev_rev    = period_revenue(prev_start, prev_end)

    if prev_rev <= 0 or current_rev <= 0:
        return []

    drop_pct = (prev_rev - current_rev) / prev_rev * 100
    if drop_pct < drop_threshold_pct:
        return []

    if A.already_active(AT.SALES_DROP):
        return []

    priority = P.HIGH if drop_pct >= 35 else P.MEDIUM
    message  = (
        f"Overall sales drop detected: company-wide revenue fell {drop_pct:.1f}% "
        f"over the past {days} days "
        f"(from {prev_rev:,.2f} to {current_rev:,.2f}). "
        f"Investigate immediately."
    )

    alert = A.objects.create(
        alert_type=AT.SALES_DROP,
        alert_message=message,
        priority_level=priority,
        related_entity_type=ET.OVERALL,
        related_entity_id=None,
        related_entity_name="Overall Business",
    )
    return [alert]


# ---------------------------------------------------------------------------
# Generator: Forecast Risk
# ---------------------------------------------------------------------------

def generate_forecast_risk_alerts(decline_threshold_pct=15.0):
    """
    Alert when the latest forecast for any target predicts a significant
    revenue decline vs the historical actuals embedded in that forecast.
    """
    recent_forecasts = list(Forecast.objects.latest_per_target())
    created = []

    target_entity_map = {
        Forecast.TargetType.PRODUCT:  ET.PRODUCT,
        Forecast.TargetType.CATEGORY: ET.CATEGORY,
        Forecast.TargetType.BRANCH:   ET.BRANCH,
        Forecast.TargetType.OVERALL:  ET.OVERALL,
    }

    for forecast in recent_forecasts:
        data = forecast.forecast_data
        if not data:
            continue

        actual_vals    = [d["actual"]    for d in data if d.get("actual")    is not None]
        predicted_vals = [d["predicted"] for d in data if d.get("predicted") is not None]

        if not actual_vals or not predicted_vals:
            continue

        avg_actual    = sum(actual_vals)    / len(actual_vals)
        avg_predicted = sum(predicted_vals) / len(predicted_vals)

        if avg_actual <= 0:
            continue

        decline_pct = (avg_actual - avg_predicted) / avg_actual * 100
        if decline_pct < decline_threshold_pct:
            continue

        entity_type = target_entity_map.get(forecast.forecast_target_type, ET.OVERALL)
        entity_id   = forecast.target_id

        if A.already_active(AT.FORECAST_RISK, entity_type, entity_id):
            continue

        priority = P.HIGH if decline_pct >= 30 else P.MEDIUM
        target_label = (
            f"target #{entity_id}"
            if entity_id else
            f"overall ({forecast.get_forecast_target_type_display()})"
        )
        message = (
            f"Forecast risk for {target_label}: "
            f"{forecast.get_model_name_display()} model predicts "
            f"{avg_predicted:,.2f}/month vs recent actuals of {avg_actual:,.2f}/month "
            f"(−{decline_pct:.1f}%)."
        )

        alert = A.objects.create(
            alert_type=AT.FORECAST_RISK,
            alert_message=message,
            priority_level=priority,
            related_entity_type=entity_type,
            related_entity_id=entity_id,
            related_entity_name=target_label,
        )
        created.append(alert)

    return created


# ---------------------------------------------------------------------------
# Generator: High Demand (positive signal)
# ---------------------------------------------------------------------------

def generate_high_demand_alerts(lookback_months=2, growth_threshold_pct=40.0):
    """
    Positive alert: a product's revenue is growing fast.
    Flags it as HIGH_DEMAND so staff know to ensure sufficient stock.
    """
    today = timezone.now().date()

    current_start = _months_ago(lookback_months)
    prev_end      = current_start - timedelta(days=1)
    prev_start    = _months_ago(lookback_months * 2)

    current_map = _product_revenues(current_start, today)
    prev_map    = _product_revenues(prev_start, prev_end)

    created = []
    for product_id, cur in current_map.items():
        prv = prev_map.get(product_id, {}).get("revenue", 0)
        if prv <= 0 or cur["revenue"] <= 0:
            continue

        growth_pct = (cur["revenue"] - prv) / prv * 100
        if growth_pct < growth_threshold_pct:
            continue

        if A.already_active(AT.HIGH_DEMAND, ET.PRODUCT, product_id):
            continue

        message = (
            f"High demand signal: '{cur['product_name']}' (SKU: {cur['sku']}) "
            f"revenue grew {growth_pct:.1f}% vs the prior period "
            f"({prv:,.2f} → {cur['revenue']:,.2f}). "
            f"Verify stock levels to avoid a stockout."
        )

        alert = A.objects.create(
            alert_type=AT.HIGH_DEMAND,
            alert_message=message,
            priority_level=P.LOW,
            related_entity_type=ET.PRODUCT,
            related_entity_id=product_id,
            related_entity_name=cur["product_name"],
        )
        created.append(alert)

    return created


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

@transaction.atomic
def run_all_alert_generators(
    sales_lookback_months=2,
    declining_sales_threshold=25.0,
    branch_lookback_months=3,
    branch_threshold_pct=70.0,
    sales_drop_days=14,
    sales_drop_threshold=20.0,
    forecast_risk_threshold=15.0,
    high_demand_threshold=40.0,
):
    """
    Run all alert generators atomically and return a summary.

    Returns
    -------
    dict — {rule_results: {generator_name: count}, total_created: int}
    """
    results = {}

    r = generate_low_stock_alerts()
    results["low_stock"] = len(r)
    logger.info("alert: low_stock → %d", len(r))

    r = generate_declining_sales_alerts(
        lookback_months=sales_lookback_months,
        decline_threshold_pct=declining_sales_threshold,
    )
    results["declining_sales"] = len(r)
    logger.info("alert: declining_sales → %d", len(r))

    r = generate_branch_underperformance_alerts(
        lookback_months=branch_lookback_months,
        threshold_pct=branch_threshold_pct,
    )
    results["branch_underperformance"] = len(r)
    logger.info("alert: branch_underperformance → %d", len(r))

    r = generate_sales_drop_alerts(
        days=sales_drop_days,
        drop_threshold_pct=sales_drop_threshold,
    )
    results["sales_drop"] = len(r)
    logger.info("alert: sales_drop → %d", len(r))

    r = generate_forecast_risk_alerts(decline_threshold_pct=forecast_risk_threshold)
    results["forecast_risk"] = len(r)
    logger.info("alert: forecast_risk → %d", len(r))

    r = generate_high_demand_alerts(growth_threshold_pct=high_demand_threshold)
    results["high_demand"] = len(r)
    logger.info("alert: high_demand → %d", len(r))

    total = sum(results.values())
    logger.info("Alert generator run complete — %d new alert(s) total.", total)

    return {"rule_results": results, "total_created": total}
