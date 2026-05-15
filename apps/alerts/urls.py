"""
Alerts URL Configuration
=========================

GET  /api/alerts/              → paginated list (filters: is_active, priority, type)
GET  /api/alerts/counts/       → active alert counts by priority (for navbar badge)
POST /api/alerts/generate/     → trigger alert generators (Admin/Manager)
POST /api/alerts/{id}/dismiss/ → dismiss an alert
"""
from django.urls import path

from .views import (
    AlertCountView,
    AlertDismissView,
    AlertListView,
    GenerateAlertsView,
)

urlpatterns = [
    path("",                   AlertListView.as_view(),     name="alert-list"),
    path("counts/",            AlertCountView.as_view(),    name="alert-counts"),
    path("generate/",          GenerateAlertsView.as_view(), name="alert-generate"),
    path("<int:pk>/dismiss/",  AlertDismissView.as_view(),  name="alert-dismiss"),
]
