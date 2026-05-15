"""
Analytics Views
===============
All endpoints are read-only GET views.
Every view accepts ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD query params.
Default window is the last 12 months (enforced by date_range_from_params).

Endpoints
---------
GET /api/analytics/dashboard/   → KPI cards with period-over-period comparison
GET /api/analytics/trends/      → revenue / profit time series
GET /api/analytics/products/    → top, low-performing, and low-stock products
GET /api/analytics/branches/    → per-branch revenue and margin table
GET /api/analytics/categories/  → per-category revenue and margin table
GET /api/analytics/customers/   → customer segmentation and top spenders
GET /api/analytics/financial/   → monthly financial breakdown with cumulative totals
"""
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import date_range_from_params

from .engine.branches   import compute_branch_performance
from .engine.categories import compute_category_performance
from .engine.customers  import compute_customer_analytics
from .engine.financial  import compute_financial_analytics
from .engine.kpis       import compute_dashboard_kpis
from .engine.products   import (
    compute_low_performing_products,
    compute_low_stock_products,
    compute_top_products,
)
from .engine.trends     import compute_sales_trend

logger = logging.getLogger(__name__)


class DashboardKPIView(APIView):
    """
    GET /api/analytics/dashboard/
    KPI cards with current and previous period values + growth rates.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        return Response(compute_dashboard_kpis(date_from, date_to))


class SalesTrendView(APIView):
    """
    GET /api/analytics/trends/
    Time-series data for line charts.

    Extra query params:
      granularity — 'monthly' (default) | 'weekly' | 'daily'
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        granularity = request.query_params.get("granularity", "monthly")
        if granularity not in ("monthly", "weekly", "daily"):
            granularity = "monthly"
        series = compute_sales_trend(date_from, date_to, granularity)
        return Response({"granularity": granularity, "series": series})


class ProductAnalyticsView(APIView):
    """
    GET /api/analytics/products/
    Top products, low-performing products, and low-stock alerts.

    Extra query params:
      metric — 'revenue' (default) | 'profit' | 'units'
      limit  — 1–50, default 10
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)

        metric = request.query_params.get("metric", "revenue")
        if metric not in ("revenue", "profit", "units"):
            metric = "revenue"

        try:
            limit = max(1, min(int(request.query_params.get("limit", 10)), 50))
        except (ValueError, TypeError):
            limit = 10

        return Response({
            "metric":           metric,
            "top_products":     compute_top_products(date_from, date_to, limit=limit, metric=metric),
            "low_performing":   compute_low_performing_products(date_from, date_to, limit=limit),
            "low_stock":        compute_low_stock_products(limit=20),
        })


class BranchAnalyticsView(APIView):
    """
    GET /api/analytics/branches/
    Per-branch revenue, profit, margin, and transaction share.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        return Response({"branches": compute_branch_performance(date_from, date_to)})


class CategoryAnalyticsView(APIView):
    """
    GET /api/analytics/categories/
    Per-category revenue, profit, margin, and distinct product count.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        return Response({"categories": compute_category_performance(date_from, date_to)})


class CustomerAnalyticsView(APIView):
    """
    GET /api/analytics/customers/
    Segmentation by type and region, top spenders, walk-in ratio.

    Extra query params:
      top_n — 1–50, default 10
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        try:
            top_n = max(1, min(int(request.query_params.get("top_n", 10)), 50))
        except (ValueError, TypeError):
            top_n = 10
        return Response(compute_customer_analytics(date_from, date_to, top_n=top_n))


class FinancialAnalyticsView(APIView):
    """
    GET /api/analytics/financial/
    Monthly revenue / cost / profit breakdown with cumulative totals,
    best/worst months, and period-level summary.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = date_range_from_params(request)
        return Response(compute_financial_analytics(date_from, date_to))
