"""
WSGI config for the project.
Used by: gunicorn config.wsgi:application
"""
import os

from django.core.wsgi import get_wsgi_application

django_env = os.environ.get("DJANGO_ENV", "development")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{django_env}")

application = get_wsgi_application()
