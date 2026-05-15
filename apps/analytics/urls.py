"""
Analytics URL Configuration
============================

GET /api/analytics/dashboard/   → KPI cards with period-over-period comparison
GET /api/analytics/trends/      → revenue / profit time series (granularity param)
GET /api/analytics/products/    → top, low-performing, and low-stock products
GET /api/analytics/branches/    → per-branch revenue, profit, margin
GET /api/analytics/categories/  → per-category revenue, profit, margin
GET /api/analytics/customers/   → customer segmentation and top spenders
GET /api/analytics/financial/   → monthly financial breakdown + cumulative totals
"""
from django.urls import path

from .views import (
    BranchAnalyticsView,
    CategoryAnalyticsView,
    CustomerAnalyticsView,
    DashboardKPIView,
    FinancialAnalyticsView,
    ProductAnalyticsView,
    SalesTrendView,
)

urlpatterns = [
    path("dashboard/",   DashboardKPIView.as_view(),      name="analytics-dashboard"),
    path("trends/",      SalesTrendView.as_view(),         name="analytics-trends"),
    path("products/",    ProductAnalyticsView.as_view(),   name="analytics-products"),
    path("branches/",    BranchAnalyticsView.as_view(),    name="analytics-branches"),
    path("categories/",  CategoryAnalyticsView.as_view(),  name="analytics-categories"),
    path("customers/",   CustomerAnalyticsView.as_view(),  name="analytics-customers"),
    path("financial/",   FinancialAnalyticsView.as_view(), name="analytics-financial"),
]
