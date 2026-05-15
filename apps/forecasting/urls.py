"""
Forecasting URL Configuration
==============================

POST /api/forecast/run/              → run a new forecast (returns full result)
GET  /api/forecast/history/          → paginated list of past forecasts
GET  /api/forecast/history/{id}/     → full forecast detail with forecast_data
"""
from django.urls import path

from .views import ForecastDetailView, ForecastHistoryListView, ForecastRunView

urlpatterns = [
    path("run/",                ForecastRunView.as_view(),         name="forecast-run"),
    path("history/",            ForecastHistoryListView.as_view(), name="forecast-history"),
    path("history/<int:pk>/",   ForecastDetailView.as_view(),      name="forecast-detail"),
]
