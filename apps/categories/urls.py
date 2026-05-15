"""
Categories URL Configuration
=============================

GET    /api/categories/             → list
POST   /api/categories/             → create
GET    /api/categories/dropdown/    → unpaginated id+name list (for select inputs)
GET    /api/categories/{id}/        → retrieve
PUT    /api/categories/{id}/        → update
PATCH  /api/categories/{id}/        → partial update
DELETE /api/categories/{id}/        → destroy
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet

router = DefaultRouter()
router.register(r"", CategoryViewSet, basename="categories")

urlpatterns = [
    path("", include(router.urls)),
]
