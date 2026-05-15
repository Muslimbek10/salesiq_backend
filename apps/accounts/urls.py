"""
Accounts URL Configuration
===========================

POST /api/auth/login/             → LoginView
POST /api/auth/logout/            → LogoutView
POST /api/auth/token/refresh/     → SimpleJWT TokenRefreshView
GET  /api/auth/profile/           → ProfileView (retrieve)
PATCH /api/auth/profile/          → ProfileView (update own profile)
POST /api/auth/change-password/   → ChangePasswordView
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import ChangePasswordView, LoginView, LogoutView, ProfileView

urlpatterns = [
    # Authentication
    path("login/",           LoginView.as_view(),          name="auth-login"),
    path("logout/",          LogoutView.as_view(),         name="auth-logout"),
    path("token/refresh/",   TokenRefreshView.as_view(),   name="auth-token-refresh"),

    # Profile management
    path("profile/",         ProfileView.as_view(),        name="auth-profile"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
]
