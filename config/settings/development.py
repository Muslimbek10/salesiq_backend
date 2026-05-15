"""
Development Settings
Overrides base settings for local development.

Activate with: DJANGO_ENV=development (this is the default in manage.py)
"""
from .base import *  # noqa: F401, F403

# ============================================================
# SECURITY — Relaxed for development
# ============================================================

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]


# ============================================================
# INSTALLED APPS — Development extras
# ============================================================

# django-extensions gives useful dev tools: shell_plus, show_urls, etc.
# Install with: pip install django-extensions
# INSTALLED_APPS += ["django_extensions"]  # Uncomment if installed


# ============================================================
# DATABASE — Use local PostgreSQL
# ============================================================

# Database config is inherited from base.py and reads from .env.
# Ensure your .env has the correct local DB credentials.
# DB_NAME=salesiq_db, DB_USER=postgres, DB_PASSWORD=..., DB_HOST=localhost


# ============================================================
# EMAIL — Print to console in development
# ============================================================

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# ============================================================
# CORS — Allow all localhost origins in development
# ============================================================

CORS_ALLOW_ALL_ORIGINS = True  # Only safe because DEBUG=True


# ============================================================
# LOGGING — More verbose in development
# ============================================================

LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405
LOGGING["root"]["level"] = "DEBUG"              # noqa: F405


# ============================================================
# DRF BROWSABLE API — Enable in development for easy testing
# ============================================================

REST_FRAMEWORK = {                              # noqa: F405
    **REST_FRAMEWORK,                           # noqa: F405
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",  # HTML API browser
    ],
}
