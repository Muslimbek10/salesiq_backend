"""
Customer Analytics Engine
==========================
Provides four customer-focused datasets:

  - Segmentation by customer_type (retail / wholesale / VIP / corporate)
  - Revenue breakdown by region
  - Top-N customers by total spend
  - Walk-in vs identified customer ratio

All queries stay within a single date window and rely only on the sales table
to avoid N+1 fetches against the customers table.

compute_customer_analytics(date_from, date_to, top_n)
"""
from django.db.models import Count, Q, Sum

from apps.sales.models import Sale


def compute_customer_analytics(date_from, date_to, top_n=10):
    """
    Customer analytics for the selected date range.

    Parameters
    ----------
    top_n : int  — number of top customers to include (1–50)

    Returns
    -------
    dict with keys: by_type, by_region, top_customers, walk_in_vs_identified
    """
    base_qs = Sale.objects.filter(sale_date__gte=date_from, sale_date__lte=date_to)

    # ------------------------------------------------------------------ #
    # 1. By customer type (identified customers only)
    # ------------------------------------------------------------------ #
    by_type = (
        base_qs
        .filter(customer__isnull=False)
        .values("customer__customer_type")
        .annotate(transactions=Count("id"), revenue=Sum("total_amount"))
        .order_by("-revenue")
    )

    # ------------------------------------------------------------------ #
    # 2. By region (identified customers only)
    # ------------------------------------------------------------------ #
    by_region = (
        base_qs
        .filter(customer__isnull=False)
        .values("customer__region")
        .annotate(transactions=Count("id"), revenue=Sum("total_amount"))
        .order_by("-revenue")
    )

    # ------------------------------------------------------------------ #
    # 3. Top customers by total spend
    # ------------------------------------------------------------------ #
    top_customers = (
        base_qs
        .filter(customer__isnull=False)
        .values(
            "customer_id",
            "customer__full_name",
            "customer__customer_type",
        )
        .annotate(
            total_spent=Sum("total_amount"),
            total_transactions=Count("id"),
            total_units=Sum("quantity"),
        )
        .order_by("-total_spent")[:top_n]
    )

    # ------------------------------------------------------------------ #
    # 4. Walk-in vs identified — single aggregate pass
    # ------------------------------------------------------------------ #
    walk_in_q     = Q(customer__isnull=True)
    identified_q  = Q(customer__isnull=False)

    ratios = base_qs.aggregate(
        total_transactions=Count("id"),
        walk_in_count=Count("id", filter=walk_in_q),
        identified_count=Count("id", filter=identified_q),
        walk_in_revenue=Sum("total_amount", filter=walk_in_q),
        identified_revenue=Sum("total_amount", filter=identified_q),
    )

    return {
        "by_type": [
            {
                "customer_type": r["customer__customer_type"],
                "transactions":  r["transactions"],
                "revenue":       round(float(r["revenue"] or 0), 2),
            }
            for r in by_type
        ],
        "by_region": [
            {
                "region":       r["customer__region"] or "Unknown",
                "transactions": r["transactions"],
                "revenue":      round(float(r["revenue"] or 0), 2),
            }
            for r in by_region
        ],
        "top_customers": [
            {
                "customer_id":        r["customer_id"],
                "full_name":          r["customer__full_name"],
                "customer_type":      r["customer__customer_type"],
                "total_spent":        round(float(r["total_spent"] or 0), 2),
                "total_transactions": r["total_transactions"],
                "total_units":        int(r["total_units"] or 0),
            }
            for r in top_customers
        ],
        "walk_in_vs_identified": {
            "total_transactions":    ratios["total_transactions"]    or 0,
            "walk_in_transactions":  ratios["walk_in_count"]         or 0,
            "identified_transactions": ratios["identified_count"]    or 0,
            "walk_in_revenue":       round(float(ratios["walk_in_revenue"]    or 0), 2),
            "identified_revenue":    round(float(ratios["identified_revenue"] or 0), 2),
        },
    }
