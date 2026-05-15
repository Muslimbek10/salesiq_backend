"""
Branch Rules
============
Detects underperforming branches using two complementary signals:

check_underperforming_branches(lookback_months, threshold_pct)
  A branch is underperforming if its revenue for the window is below
  `threshold_pct` of the company-wide average branch revenue.
  Example: threshold=70 → flags any branch earning < 70% of the avg.

check_branch_revenue_decline(lookback_months, decline_threshold_pct)
  Compares each branch's revenue in the current window against the
  preceding equal-length window. Significant declines are flagged
  regardless of how the branch compares to peers.
"""
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.recommendations.models import Recommendation
from apps.sales.models import Sale

R  = Recommendation
RT = R.RecommendationType
ET = R.EntityType
P  = R.Priority


def _branch_revenues(date_from, date_to):
    """
    Return {branch_id: {revenue, branch_name}} for the window.
    Only branches with at least one sale are included.
    """
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


def _already_active(rec_type, branch_id):
    return R.objects.filter(
        recommendation_type=rec_type,
        related_entity_type=ET.BRANCH,
        related_entity_id=branch_id,
        is_active=True,
    ).exists()


def _months_ago(months):
    today = timezone.now().date()
    year  = today.year + (today.month - months - 1) // 12
    month = (today.month - months - 1) % 12 + 1
    return today.replace(year=year, month=month, day=1)


# ---------------------------------------------------------------------------
# Rule: Underperforming vs Peers
# ---------------------------------------------------------------------------

def check_underperforming_branches(lookback_months=3, threshold_pct=70.0):
    """
    Flag branches earning below `threshold_pct` of the average branch revenue.

    Parameters
    ----------
    lookback_months  : int   — comparison window (default 3 months)
    threshold_pct    : float — % of average below which a branch is flagged (default 70)

    Returns
    -------
    list[Recommendation]
    """
    today         = timezone.now().date()
    date_from     = _months_ago(lookback_months)
    date_to       = today

    branch_map    = _branch_revenues(date_from, date_to)
    if len(branch_map) < 2:
        return []   # need at least 2 branches for a meaningful comparison

    revenues  = [v["revenue"] for v in branch_map.values()]
    avg_rev   = sum(revenues) / len(revenues)
    threshold = avg_rev * threshold_pct / 100

    created = []
    for branch_id, info in branch_map.items():
        if info["revenue"] >= threshold:
            continue
        if _already_active(RT.BRANCH_PERFORMANCE, branch_id):
            continue

        gap_pct  = (avg_rev - info["revenue"]) / avg_rev * 100 if avg_rev > 0 else 0
        priority = P.HIGH if info["revenue"] < avg_rev * 0.5 else P.MEDIUM

        text = (
            f"Branch underperformance detected: '{info['branch_name']}' generated "
            f"{info['revenue']:,.2f} in revenue over the past {lookback_months} month(s), "
            f"which is {gap_pct:.1f}% below the company branch average of {avg_rev:,.2f}. "
            f"Investigate operational issues, staffing, local market conditions, "
            f"or consider targeted promotions to boost performance."
        )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.BRANCH_PERFORMANCE,
            related_entity_type=ET.BRANCH,
            related_entity_id=branch_id,
            related_entity_name=info["branch_name"],
            priority_level=priority,
        )
        created.append(rec)

    return created


# ---------------------------------------------------------------------------
# Rule: Period-over-Period Revenue Decline
# ---------------------------------------------------------------------------

def check_branch_revenue_decline(lookback_months=3, decline_threshold_pct=20.0):
    """
    Flag branches where revenue declined significantly vs the prior period.
    Complements check_underperforming_branches — a branch may be above
    average but still declining alarmingly.

    Returns
    -------
    list[Recommendation]
    """
    today = timezone.now().date()

    current_end   = today
    current_start = _months_ago(lookback_months)
    prev_end      = current_start - timedelta(days=1)
    prev_start    = _months_ago(lookback_months * 2)

    current_map = _branch_revenues(current_start, current_end)
    prev_map    = _branch_revenues(prev_start,    prev_end)

    created = []

    for branch_id, cur in current_map.items():
        prv_revenue = prev_map.get(branch_id, {}).get("revenue", 0)
        cur_revenue = cur["revenue"]

        if prv_revenue <= 0 or cur_revenue <= 0:
            continue

        decline_pct = (prv_revenue - cur_revenue) / prv_revenue * 100
        if decline_pct < decline_threshold_pct:
            continue

        # Only create if no underperformance rec already active for this branch
        if _already_active(RT.BRANCH_PERFORMANCE, branch_id):
            continue

        priority = P.HIGH if decline_pct >= 40 else P.MEDIUM

        text = (
            f"Revenue decline at '{cur['branch_name']}': revenue dropped {decline_pct:.1f}% "
            f"over the past {lookback_months} month(s) "
            f"(from {prv_revenue:,.2f} to {cur_revenue:,.2f}). "
            f"Conduct a branch review — investigate product mix, staffing levels, "
            f"local competition, and customer satisfaction."
        )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.BRANCH_PERFORMANCE,
            related_entity_type=ET.BRANCH,
            related_entity_id=branch_id,
            related_entity_name=cur["branch_name"],
            priority_level=priority,
        )
        created.append(rec)

    return created
