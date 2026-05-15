"""
Recommendation Engine Runner
=============================
Orchestrates all rule modules in a single atomic transaction.

run_all_rules(**config)
  Calls every rule function in a defined order (stock → sales → branches →
  categories → customers → forecast).  Returns a summary dict showing how
  many recommendations were created per rule group.

  Designed to be called:
    - Via POST /api/recommendations/generate/  (on-demand from the UI)
    - From a management command or scheduled task (cron / Celery beat)

Configuration
-------------
All rule thresholds are keyword-argument overrides.  Defaults reflect
sensible production values and can be changed per-call without code changes.
"""
import logging

from django.db import transaction

from .branch_rules   import check_branch_revenue_decline, check_underperforming_branches
from .category_rules import check_high_margin_categories, check_low_margin_categories
from .customer_rules import check_dormant_regular_customers, check_inactive_vip_customers
from .sales_rules    import check_declining_products, check_forecast_risk, check_high_performers
from .stock_rules    import check_low_stock

logger = logging.getLogger(__name__)


@transaction.atomic
def run_all_rules(
    # --- Stock ---
    # (no configurable params for stock — thresholds live on the Product model)

    # --- Sales ---
    sales_lookback_months=2,
    declining_threshold_pct=20.0,
    growth_threshold_pct=30.0,
    forecast_risk_threshold_pct=15.0,

    # --- Branches ---
    branch_lookback_months=3,
    branch_peer_threshold_pct=70.0,
    branch_decline_threshold_pct=20.0,

    # --- Categories ---
    category_lookback_months=3,
    low_margin_threshold_pct=10.0,
    high_margin_threshold_pct=35.0,

    # --- Customers ---
    vip_inactive_days=30,
    regular_min_purchases=4,
    regular_inactive_days=60,
):
    """
    Run every recommendation rule and return a summary.

    Returns
    -------
    dict — {
        "rule_results": {rule_name: count_created},
        "total_created": int,
    }
    """
    results = {}

    # ------------------------------------------------------------------ #
    # 1. Stock rules
    # ------------------------------------------------------------------ #
    recs = check_low_stock()
    results["low_stock"] = len(recs)
    logger.info("stock_rules.check_low_stock → %d recommendation(s)", len(recs))

    # ------------------------------------------------------------------ #
    # 2. Sales rules
    # ------------------------------------------------------------------ #
    recs = check_declining_products(
        lookback_months=sales_lookback_months,
        decline_threshold_pct=declining_threshold_pct,
    )
    results["declining_sales"] = len(recs)
    logger.info("sales_rules.check_declining_products → %d recommendation(s)", len(recs))

    recs = check_high_performers(
        lookback_months=sales_lookback_months,
        growth_threshold_pct=growth_threshold_pct,
    )
    results["high_performers"] = len(recs)
    logger.info("sales_rules.check_high_performers → %d recommendation(s)", len(recs))

    recs = check_forecast_risk(decline_threshold_pct=forecast_risk_threshold_pct)
    results["forecast_risk"] = len(recs)
    logger.info("sales_rules.check_forecast_risk → %d recommendation(s)", len(recs))

    # ------------------------------------------------------------------ #
    # 3. Branch rules
    # ------------------------------------------------------------------ #
    recs = check_underperforming_branches(
        lookback_months=branch_lookback_months,
        threshold_pct=branch_peer_threshold_pct,
    )
    results["branch_underperformance"] = len(recs)
    logger.info("branch_rules.check_underperforming_branches → %d recommendation(s)", len(recs))

    recs = check_branch_revenue_decline(
        lookback_months=branch_lookback_months,
        decline_threshold_pct=branch_decline_threshold_pct,
    )
    results["branch_decline"] = len(recs)
    logger.info("branch_rules.check_branch_revenue_decline → %d recommendation(s)", len(recs))

    # ------------------------------------------------------------------ #
    # 4. Category rules
    # ------------------------------------------------------------------ #
    recs = check_low_margin_categories(
        lookback_months=category_lookback_months,
        margin_threshold_pct=low_margin_threshold_pct,
    )
    results["low_margin_categories"] = len(recs)
    logger.info("category_rules.check_low_margin_categories → %d recommendation(s)", len(recs))

    recs = check_high_margin_categories(
        lookback_months=category_lookback_months,
        margin_threshold_pct=high_margin_threshold_pct,
    )
    results["high_margin_categories"] = len(recs)
    logger.info("category_rules.check_high_margin_categories → %d recommendation(s)", len(recs))

    # ------------------------------------------------------------------ #
    # 5. Customer rules
    # ------------------------------------------------------------------ #
    recs = check_inactive_vip_customers(inactive_days=vip_inactive_days)
    results["inactive_vip"] = len(recs)
    logger.info("customer_rules.check_inactive_vip_customers → %d recommendation(s)", len(recs))

    recs = check_dormant_regular_customers(
        min_purchases=regular_min_purchases,
        inactive_days=regular_inactive_days,
    )
    results["dormant_regulars"] = len(recs)
    logger.info("customer_rules.check_dormant_regular_customers → %d recommendation(s)", len(recs))

    total = sum(results.values())
    logger.info("Recommendation engine run complete — %d new recommendation(s) total.", total)

    return {
        "rule_results":  results,
        "total_created": total,
    }
