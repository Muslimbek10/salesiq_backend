"""
Reports URL Configuration
==========================

GET /api/reports/daily/    → day-by-day sales breakdown
GET /api/reports/monthly/  → month-by-month summary with cumulative totals
GET /api/reports/yearly/   → year-over-year comparison
GET /api/reports/branch/   → branch performance table
GET /api/reports/product/  → top and bottom product performance
"""
from django.urls import path

from .views import (
    BranchReportView,
    DailyReportView,
    MonthlyReportView,
    ProductReportView,
    YearlyReportView,
)

urlpatterns = [
    path("daily/",   DailyReportView.as_view(),   name="report-daily"),
    path("monthly/", MonthlyReportView.as_view(),  name="report-monthly"),
    path("yearly/",  YearlyReportView.as_view(),   name="report-yearly"),
    path("branch/",  BranchReportView.as_view(),   name="report-branch"),
    path("product/", ProductReportView.as_view(),  name="report-product"),
]
