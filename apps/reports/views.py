"""
Reports Views
=============
Structured report endpoints. Each view assembles a focused data package
from the analytics engine modules and returns it as a single JSON response.

All reports accept ?date_from=YYYY-MM-DD and ?date_to=YYYY-MM-DD.
Default window is the last 12 months (enforced by date_range_from_params).

GET /api/reports/daily/    → day-by-day sales breakdown for the selected window
GET /api/reports/monthly/  → month-by-month summary with cumulative totals
GET /api/reports/yearly/   → year-over-year comparison
GET /api/reports/branch/   → branch performance table
GET /api/reports/product/  → top/low product performance table
"""
import logging
from datetime import timedelta

from django.db.models import Avg, Count, Max, Min, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncYear
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sales.models import Sale
from core.utils import calculate_gross_margin, calculate_growth_rate, date_range_from_params

from .generators.helpers import (
    daily_series,
    monthly_series,
    product_performance_table,
    branch_performance_table,
    yearly_comparison,
)

logger = logging.getLogger(__name__)


class DailyReportView(APIView):
    """
    GET /api/reports/daily/
    Day-by-day sales breakdown for the window.
    Best used with a short date range (≤90 days) to keep response size manageable.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "series": daily_series(date_from, date_to),
        })


class MonthlyReportView(APIView):
    """
    GET /api/reports/monthly/
    Month-by-month financial summary with cumulative revenue and profit.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        series = monthly_series(date_from, date_to)

        # Period totals
        grand = Sale.objects.filter(
            sale_date__gte=date_from, sale_date__lte=date_to
        ).aggregate(
            revenue=Sum("total_amount"),
            cost=Sum("total_cost"),
            profit=Sum("total_profit"),
            transactions=Count("id"),
            units=Sum("quantity"),
        )

        revenue = float(grand["revenue"] or 0)
        cost    = float(grand["cost"]    or 0)

        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "series": series,
            "totals": {
                "revenue":          round(revenue, 2),
                "cost":             round(cost, 2),
                "profit":           round(float(grand["profit"] or 0), 2),
                "gross_margin_pct": calculate_gross_margin(revenue, cost),
                "transactions":     grand["transactions"] or 0,
                "units_sold":       int(grand["units"] or 0),
            },
        })


class YearlyReportView(APIView):
    """
    GET /api/reports/yearly/
    Year-over-year revenue, profit, and transaction comparison.
    Ignores date_from/date_to — always shows all available years.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"years": yearly_comparison()})


class BranchReportView(APIView):
    """
    GET /api/reports/branch/
    Branch performance table with revenue, profit, margin, and share.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        return Response({
            "period":   {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "branches": branch_performance_table(date_from, date_to),
        })


class ProductReportView(APIView):
    """
    GET /api/reports/product/
    Product performance table — top and bottom performers by revenue.

    Query params:
      limit  — rows per segment (default 20, max 100)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        try:
            limit = max(1, min(int(request.query_params.get("limit", 20)), 100))
        except (ValueError, TypeError):
            limit = 20

        top, bottom = product_performance_table(date_from, date_to, limit=limit)
        return Response({
            "period":           {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "top_products":     top,
            "bottom_products":  bottom,
        })
