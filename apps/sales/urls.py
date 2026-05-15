"""
Sales URL Configuration
=======================

GET    /api/sales/              → list   (filters: product, branch, customer, category, date range)
POST   /api/sales/              → create
GET    /api/sales/export/       → CSV export (filtered)
GET    /api/sales/summary/      → aggregate KPI totals (filtered)
GET    /api/sales/{id}/         → retrieve
PUT    /api/sales/{id}/         → update
PATCH  /api/sales/{id}/         → partial update
DELETE /api/sales/{id}/         → destroy
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SaleViewSet

router = DefaultRouter()
router.register(r"", SaleViewSet, basename="sales")

urlpatterns = [
    path("", include(router.urls)),
]
