"""
Products URL Configuration
===========================

GET    /api/products/                      → list (filter: category, is_active, stock_status, search)
POST   /api/products/                      → create
GET    /api/products/low_stock/            → products at or below minimum stock
GET    /api/products/dropdown/             → unpaginated id+name list for select inputs
GET    /api/products/{id}/                 → retrieve
PUT    /api/products/{id}/                 → update
PATCH  /api/products/{id}/                 → partial update
DELETE /api/products/{id}/                 → destroy
POST   /api/products/{id}/toggle_active/   → flip is_active
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProductViewSet

router = DefaultRouter()
router.register(r"", ProductViewSet, basename="products")

urlpatterns = [
    path("", include(router.urls)),
]
