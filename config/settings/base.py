"""
Base Settings
Intelligent Sales Analytics & Business Decision Support Platform

All shared configuration lives here.
Development and production settings files import from this module
and override only what they need to change.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# ============================================================
# PATH CONFIGURATION
# ============================================================

# BASE_DIR points to the backend/ directory (where manage.py lives)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env file from backend/.env
load_dotenv(BASE_DIR / ".env")


# ============================================================
# SECURITY
# ============================================================

SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-default-key-change-in-production")

# Defined per environment (development.py / production.py)
DEBUG = False

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")


# ============================================================
# APPLICATION DEFINITION
# ============================================================

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # Enables logout via token blacklist
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

PROJECT_APPS = [
    "apps.accounts",
    "apps.categories",
    "apps.products",
    "apps.customers",
    "apps.branches",
    "apps.sales",
    "apps.analytics",
    "apps.forecasting",
    "apps.recommendations",
    "apps.alerts",
    "apps.reports",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + PROJECT_APPS


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",          # Must be before CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ============================================================
# URL CONFIGURATION
# ============================================================

ROOT_URLCONF = "config.urls"


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ============================================================
# WSGI / ASGI
# ============================================================

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ============================================================
# DATABASE — PostgreSQL
# ============================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "salesiq_db"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "OPTIONS": {
            # Ensures correct timezone handling at the DB level
            "options": "-c timezone=UTC",
        },
        "CONN_MAX_AGE": 60,  # Reuse DB connections for up to 60 seconds
    }
}


# ============================================================
# CUSTOM USER MODEL
# ============================================================

# All authentication uses our CustomUser model in accounts app
AUTH_USER_MODEL = "accounts.CustomUser"


# ============================================================
# PASSWORD VALIDATION
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ============================================================
# INTERNATIONALIZATION
# ============================================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# ============================================================
# STATIC FILES
# ============================================================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# ============================================================
# DEFAULT AUTO FIELD
# ============================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# DJANGO REST FRAMEWORK
# ============================================================

REST_FRAMEWORK = {
    # JWT is the default authentication method for all API views
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",

    # All endpoints require authentication by default.
    # Only the login endpoint explicitly sets AllowAny.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],

    # Filtering, search, and ordering are available on all ViewSets
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],

    # Standard paginated response for all list endpoints
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsPagination",
    "PAGE_SIZE": 25,

    # Custom exception handler formats errors consistently across all APIs
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
}


# ============================================================
# JWT CONFIGURATION (SimpleJWT)
# ============================================================

SIMPLE_JWT = {
    # Access tokens expire after 60 minutes.
    # Frontend should use the refresh token to get a new one silently.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),

    # Refresh tokens are valid for 7 days.
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),

    # When the frontend refreshes, rotate the refresh token
    # (the old one is blacklisted, a new one is issued).
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,

    # Token type labeling
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),

    # Field used to identify users in the token payload
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


# ============================================================
# CORS CONFIGURATION
# ============================================================

# Allow the React dev server to communicate with the Django API.
# Override in production.py with the real domain.
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000"
).split(",")

# Allow credentials (needed for cookie-based sessions if ever used)
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]


# ============================================================
# LOGGING
# ============================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # Our apps log at DEBUG level (visible only when DEBUG=True in development)
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}


# ============================================================
# API DOCUMENTATION (drf-spectacular / Swagger)
# ============================================================

SPECTACULAR_SETTINGS = {
    "TITLE": "Intelligent Sales Analytics Platform API",
    "DESCRIPTION": (
        "Full-stack sales analytics and business decision support platform. "
        "Provides endpoints for sales management, analytics, AI forecasting, "
        "recommendations, alerts, and reporting."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {
        "name": "Muslimbek Gulomnazirov",
        "email": "muslimbekgulomnazirov06@gmail.com",
    },
    "LICENSE": {"name": "Academic use only"},
    "TAGS": [
        {"name": "auth",            "description": "Authentication — login, logout, token refresh, profile"},
        {"name": "products",        "description": "Product catalogue management"},
        {"name": "categories",      "description": "Product categories"},
        {"name": "customers",       "description": "Customer management"},
        {"name": "branches",        "description": "Branch management"},
        {"name": "sales",           "description": "Sales transactions"},
        {"name": "analytics",       "description": "Dashboard KPIs, revenue trends, performance reports"},
        {"name": "forecasting",     "description": "AI revenue forecasting (Moving Average, Linear Regression, Random Forest, ARIMA)"},
        {"name": "recommendations", "description": "Business rule recommendations"},
        {"name": "alerts",          "description": "Automated business alerts"},
        {"name": "reports",         "description": "PDF and CSV report generation"},
    ],
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
}
