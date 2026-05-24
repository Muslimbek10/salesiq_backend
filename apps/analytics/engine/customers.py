"""
Customer Analytics Engine
==========================
Returns the shape the frontend CustomersTab expects:

  total_customers  — distinct identified customers with sales in period
  new_customers    — customers whose first-ever sale falls in this period
  repeat_rate      — % of period-customers who bought more than once
  avg_order_value  — average total_amount across all sales (incl. walk-ins)
  segments         — [{customer_type, count, total_spent, avg_order, avg_purchases}]
  top_customers    — top-N by total spend
  walk_in_vs_identified — raw walk-in / identified split

compute_customer_analytics(date_from, date_to, top_n)
"""
from django.db.models import Avg, Count, Min, Q, Sum

from apps.sales.models import Sale


def compute_customer_analytics(date_from, date_to, top_n=10):
    base_qs       = Sale.objects.filter(sale_date__gte=date_from, sale_date__lte=date_to)
    identified_qs = base_qs.filter(customer__isnull=False)

    # ------------------------------------------------------------------
    # 1. Total distinct customers with at least one sale in the period
    # ------------------------------------------------------------------
    total_customers = identified_qs.values("customer_id").distinct().count()

    # ------------------------------------------------------------------
    # 2. New customers — first sale EVER falls inside this period
    # ------------------------------------------------------------------
    first_sales = (
        Sale.objects
        .filter(customer__isnull=False)
        .values("customer_id")
        .annotate(first=Min("sale_date"))
    )
    new_customers = sum(
        1 for row in first_sales
        if date_from <= row["first"] <= date_to
    )

    # ------------------------------------------------------------------
    # 3. Repeat rate — % of period-customers with more than 1 purchase
    # ------------------------------------------------------------------
    purchase_counts = (
        identified_qs
        .values("customer_id")
        .annotate(purchases=Count("id"))
    )
    repeat_count = sum(1 for row in purchase_counts if row["purchases"] > 1)
    repeat_rate  = round((repeat_count / total_customers * 100) if total_customers else 0, 1)

    # ------------------------------------------------------------------
    # 4. Avg order value (all sales including walk-ins)
    # ------------------------------------------------------------------
    avg_order_value = float(
        base_qs.aggregate(avg=Avg("total_amount"))["avg"] or 0
    )

    # ------------------------------------------------------------------
    # 5. Segments by customer type
    # ------------------------------------------------------------------
    by_type_raw = (
        identified_qs
        .values("customer__customer_type")
        .annotate(
            distinct_customers=Count("customer_id", distinct=True),
            total_spent=Sum("total_amount"),
            avg_order=Avg("total_amount"),
            total_purchases=Count("id"),
        )
        .order_by("-total_spent")
    )

    segments = []
    for r in by_type_raw:
        count          = r["distinct_customers"] or 0
        total_purchases = r["total_purchases"] or 0
        segments.append({
            "customer_type": r["customer__customer_type"],
            "count":         count,
            "total_spent":   round(float(r["total_spent"] or 0), 2),
            "avg_order":     round(float(r["avg_order"]   or 0), 2),
            "avg_purchases": round(total_purchases / count, 1) if count else 0,
        })

    # ------------------------------------------------------------------
    # 6. Top customers by total spend
    # ------------------------------------------------------------------
    top_customers_qs = (
        identified_qs
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

    # ------------------------------------------------------------------
    # 7. Walk-in vs identified split
    # ------------------------------------------------------------------
    walk_in_q    = Q(customer__isnull=True)
    identified_q = Q(customer__isnull=False)
    ratios = base_qs.aggregate(
        total_transactions=Count("id"),
        walk_in_count=Count("id", filter=walk_in_q),
        identified_count=Count("id", filter=identified_q),
        walk_in_revenue=Sum("total_amount", filter=walk_in_q),
        identified_revenue=Sum("total_amount", filter=identified_q),
    )

    return {
        "total_customers": total_customers,
        "new_customers":   new_customers,
        "repeat_rate":     repeat_rate,
        "avg_order_value": round(avg_order_value, 2),
        "segments": segments,
        "top_customers": [
            {
                "customer_id":        r["customer_id"],
                "full_name":          r["customer__full_name"],
                "customer_type":      r["customer__customer_type"],
                "total_spent":        round(float(r["total_spent"] or 0), 2),
                "total_transactions": r["total_transactions"],
                "total_units":        int(r["total_units"] or 0),
            }
            for r in top_customers_qs
        ],
        "walk_in_vs_identified": {
            "total_transactions":      ratios["total_transactions"]    or 0,
            "walk_in_transactions":    ratios["walk_in_count"]         or 0,
            "identified_transactions": ratios["identified_count"]      or 0,
            "walk_in_revenue":         round(float(ratios["walk_in_revenue"]    or 0), 2),
            "identified_revenue":      round(float(ratios["identified_revenue"] or 0), 2),
        },
    }
