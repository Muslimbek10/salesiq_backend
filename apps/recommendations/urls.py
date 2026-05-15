"""
Recommendations URL Configuration
===================================

GET  /api/recommendations/                     → paginated list (filters: is_active, priority, type)
POST /api/recommendations/generate/            → trigger rule engine (Admin/Manager)
POST /api/recommendations/{id}/dismiss/        → dismiss a recommendation
POST /api/recommendations/{id}/reactivate/     → reactivate a dismissed recommendation
"""
from django.urls import path

from .views import (
    GenerateRecommendationsView,
    RecommendationDismissView,
    RecommendationListView,
    RecommendationReactivateView,
)

urlpatterns = [
    path("",                          RecommendationListView.as_view(),        name="recommendation-list"),
    path("generate/",                 GenerateRecommendationsView.as_view(),   name="recommendation-generate"),
    path("<int:pk>/dismiss/",         RecommendationDismissView.as_view(),     name="recommendation-dismiss"),
    path("<int:pk>/reactivate/",      RecommendationReactivateView.as_view(),  name="recommendation-reactivate"),
]
