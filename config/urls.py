"""
Root URL Configuration
Intelligent Sales Analytics & Business Decision Support Platform

All API endpoints are prefixed with /api/.
Each Django app has its own urls.py that is included here.

URL Structure:
    /api/auth/              → accounts app (login, logout, profile, token refresh)
    /api/categories/        → categories app
    /api/products/          → products app
    /api/customers/         → customers app
    /api/branches/          → branches app
    /api/sales/             → sales app
    /api/analytics/         → analytics app (dashboard + all analytics views)
    /api/forecast/          → forecasting app
    /api/recommendations/   → recommendations app
    /api/alerts/            → alerts app
    /api/reports/           → reports app
    /admin/                 → Django Admin panel
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView


def health_check(request):
    """GET /api/health/ — unauthenticated liveness probe."""
    return JsonResponse({"status": "ok"})


def api_root(request):
    """GET / — API index."""
    return JsonResponse({
        "name":    "Intelligent Sales Analytics Platform API",
        "version": "1.0.0",
        "status":  "running",
        "docs": {
            "admin":    "/admin/",
            "health":   "/api/health/",
            "login":    "/api/auth/login/",
            "products": "/api/products/",
            "sales":    "/api/sales/",
            "analytics":"/api/analytics/dashboard/",
        },
        "frontend": "http://localhost:5173",
    })


urlpatterns = [
    # Root index
    path("", api_root, name="api-root"),

    # Liveness probe — no authentication required
    path("api/health/", health_check, name="health-check"),

    # Django Admin — for superuser access and data inspection
    path("admin/", admin.site.urls),

    # ---- API Documentation (Swagger / ReDoc) ----
    path("api/schema/",          SpectacularAPIView.as_view(),        name="schema"),
    path("api/docs/",            SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("docs/",                RedirectView.as_view(url="/api/docs/", permanent=False)),
    path("swagger/",             SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("api/redoc/",           SpectacularRedocView.as_view(url_name="schema"),   name="redoc"),

    # ---- Authentication ----
    path("api/auth/", include("apps.accounts.urls")),

    # ---- Master Data ----
    path("api/categories/", include("apps.categories.urls")),
    path("api/products/", include("apps.products.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/branches/", include("apps.branches.urls")),

    # ---- Transactions ----
    path("api/sales/", include("apps.sales.urls")),

    # ---- Intelligence Layer ----
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/forecast/", include("apps.forecasting.urls")),
    path("api/recommendations/", include("apps.recommendations.urls")),
    path("api/alerts/", include("apps.alerts.urls")),

    # ---- Output ----
    path("api/reports/", include("apps.reports.urls")),
]
