"""
Branches URL Configuration
===========================

GET    /api/branches/                       → list
POST   /api/branches/                       → create
GET    /api/branches/dropdown/              → id+name list for sale form
GET    /api/branches/{id}/                  → retrieve
PUT    /api/branches/{id}/                  → update
PATCH  /api/branches/{id}/                  → partial update
DELETE /api/branches/{id}/                  → destroy
POST   /api/branches/{id}/toggle_active/    → flip is_active
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BranchViewSet

router = DefaultRouter()
router.register(r"", BranchViewSet, basename="branches")

urlpatterns = [
    path("", include(router.urls)),
]
