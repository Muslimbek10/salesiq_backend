"""
Production Settings
Overrides base settings for production deployment.

Activate with: DJANGO_ENV=production
"""
from .base import *  # noqa: F401, F403

# ============================================================
# SECURITY — Strict in production
# ============================================================

DEBUG = False

# In production, ALLOWED_HOSTS must be set explicitly in .env
# e.g., ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
ALLOWED_HOSTS = [
    host.strip()
    for host in __import__("os").environ.get("ALLOWED_HOSTS", "").split(",")
    if host.strip()
]

# HTTP security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000          # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True              # Redirect all HTTP to HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Railway (and most PaaS) terminate SSL at the proxy level and forward
# requests to Django over plain HTTP. Without this header Django cannot
# detect that the original request was HTTPS and enters a redirect loop.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# ============================================================
# CORS — Strict in production (set CORS_ALLOWED_ORIGINS in .env)
# ============================================================

CORS_ALLOW_ALL_ORIGINS = False
# CORS_ALLOWED_ORIGINS is already set from base.py via env var


# ============================================================
# STATIC FILES — Serve via WhiteNoise or CDN in production
# ============================================================

# Uncomment if using WhiteNoise:
# MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
# STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ============================================================
# LOGGING — Write to file in production
# ============================================================

LOGGING["handlers"]["file"] = {                 # noqa: F405
    "class": "logging.FileHandler",
    "filename": BASE_DIR / "logs" / "django.log",  # noqa: F405
    "formatter": "verbose",
}
LOGGING["root"]["handlers"] = ["console", "file"]   # noqa: F405
LOGGING["root"]["level"] = "WARNING"                 # noqa: F405


# ============================================================
# DRF — JSON only in production (no browsable API)
# ============================================================

REST_FRAMEWORK = {                               # noqa: F405
    **REST_FRAMEWORK,                            # noqa: F405
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}
