"""
Customers URL Configuration
============================

GET    /api/customers/                          → list
POST   /api/customers/                          → create
GET    /api/customers/dropdown/                 → id+name list for sale form
GET    /api/customers/{id}/                     → retrieve
PUT    /api/customers/{id}/                     → update
PATCH  /api/customers/{id}/                     → partial update
DELETE /api/customers/{id}/                     → destroy
GET    /api/customers/{id}/purchase_history/    → last 50 sales for this customer
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CustomerViewSet

router = DefaultRouter()
router.register(r"", CustomerViewSet, basename="customers")

urlpatterns = [
    path("", include(router.urls)),
]
