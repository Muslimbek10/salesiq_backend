"""
Customer Rules
==============
Two customer behaviour rules:

check_inactive_vip_customers(inactive_days)
  VIP and Corporate customers who have not made a purchase in `inactive_days`
  receive a HIGH-priority CUSTOMER_RETENTION recommendation — these customers
  are high-value and their churn is costly.

check_dormant_regular_customers(min_purchases, inactive_days)
  Customers with `min_purchases` or more historical purchases but no activity
  in the last `inactive_days` days receive a MEDIUM-priority recommendation
  suggesting a win-back campaign.
"""
from datetime import timedelta

from django.db.models import Count, Max
from django.utils import timezone

from apps.customers.models import Customer
from apps.recommendations.models import Recommendation

R  = Recommendation
RT = R.RecommendationType
ET = R.EntityType
P  = R.Priority


def _already_active(customer_id):
    return R.objects.filter(
        recommendation_type=RT.CUSTOMER_RETENTION,
        related_entity_type=ET.CUSTOMER,
        related_entity_id=customer_id,
        is_active=True,
    ).exists()


# ---------------------------------------------------------------------------
# Rule: Inactive VIP / Corporate Customers
# ---------------------------------------------------------------------------

def check_inactive_vip_customers(inactive_days=30):
    """
    Flag VIP and Corporate customers with no purchase in the last `inactive_days`.

    These customer types represent the highest revenue per head.
    Losing them is disproportionately costly — the recommendation prompts
    the team to reach out personally or offer retention incentives.

    Returns
    -------
    list[Recommendation]
    """
    cutoff     = timezone.now().date() - timedelta(days=inactive_days)
    vip_types  = [Customer.CustomerType.VIP, Customer.CustomerType.CORPORATE]

    # Customers of these types whose last purchase was before the cutoff,
    # or who have never purchased (last_purchase IS NULL)
    customers = (
        Customer.objects
        .filter(customer_type__in=vip_types)
        .annotate(
            last_purchase=Max("sales__sale_date"),
            num_purchases=Count("sales"),   # renamed: avoids clash with @property purchase_count
        )
        .filter(
            # Either never bought or last buy was before cutoff
            last_purchase__lt=cutoff
        )
        .order_by("last_purchase")
    )

    created = []
    for customer in customers:
        if _already_active(customer.pk):
            continue

        days_inactive = (timezone.now().date() - customer.last_purchase).days
        type_label    = customer.get_customer_type_display()

        text = (
            f"Inactive {type_label} customer: '{customer.full_name}' "
            f"has not made a purchase in {days_inactive} days "
            f"(last purchase: {customer.last_purchase}). "
            f"{type_label} customers represent high-value relationships. "
            f"Consider a personalised outreach, exclusive offer, or loyalty incentive "
            f"to re-engage before they switch to a competitor."
        )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.CUSTOMER_RETENTION,
            related_entity_type=ET.CUSTOMER,
            related_entity_id=customer.pk,
            related_entity_name=customer.full_name,
            priority_level=P.HIGH,
        )
        created.append(rec)

    return created


# ---------------------------------------------------------------------------
# Rule: Dormant Regular Customers
# ---------------------------------------------------------------------------

def check_dormant_regular_customers(min_purchases=4, inactive_days=60):
    """
    Identify regular customers (>= `min_purchases` past transactions)
    who have gone quiet for `inactive_days` or more days.

    Unlike inactive VIP checks, this targets volume-based regulars regardless
    of customer_type. The recommendation suggests a win-back campaign.

    Returns
    -------
    list[Recommendation]
    """
    cutoff = timezone.now().date() - timedelta(days=inactive_days)

    customers = (
        Customer.objects
        .annotate(
            last_purchase=Max("sales__sale_date"),
            num_purchases=Count("sales"),   # renamed: avoids clash with @property purchase_count
        )
        .filter(
            num_purchases__gte=min_purchases,
            last_purchase__lt=cutoff,
        )
        .order_by("last_purchase")
    )

    # Exclude VIP/Corporate (already covered by check_inactive_vip_customers)
    vip_types = [Customer.CustomerType.VIP, Customer.CustomerType.CORPORATE]

    created = []
    for customer in customers:
        if customer.customer_type in vip_types:
            continue
        if _already_active(customer.pk):
            continue

        days_inactive  = (timezone.now().date() - customer.last_purchase).days
        type_label     = customer.get_customer_type_display()
        purchase_count = customer.num_purchases   # use the annotation, not the property

        text = (
            f"Dormant regular customer: '{customer.full_name}' ({type_label}) "
            f"made {purchase_count} purchases historically but has been inactive "
            f"for {days_inactive} days (last purchase: {customer.last_purchase}). "
            f"Launch a targeted win-back campaign — personalised discount, "
            f"newsletter, or loyalty reward — to re-engage this customer."
        )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.CUSTOMER_RETENTION,
            related_entity_type=ET.CUSTOMER,
            related_entity_id=customer.pk,
            related_entity_name=customer.full_name,
            priority_level=P.MEDIUM,
        )
        created.append(rec)

    return created
