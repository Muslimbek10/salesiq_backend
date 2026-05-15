"""
ASGI config for the project.
Used if deploying with an ASGI server (e.g., uvicorn, daphne).
"""
import os

from django.core.asgi import get_asgi_application

django_env = os.environ.get("DJANGO_ENV", "development")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{django_env}")

application = get_asgi_application()
