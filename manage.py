#!/usr/bin/env python
"""
Django's command-line utility for administrative tasks.

Usage:
    python manage.py runserver
    python manage.py makemigrations
    python manage.py migrate
    python manage.py createsuperuser
    python manage.py shell

Settings are selected via DJANGO_ENV environment variable:
    DJANGO_ENV=development  ->  config.settings.development  (default)
    DJANGO_ENV=production   ->  config.settings.production
"""
import os
import sys


def main():
    # Select settings module based on DJANGO_ENV environment variable.
    # Default to "development" if not set.
    django_env = os.environ.get("DJANGO_ENV", "development")
    settings_module = f"config.settings.{django_env}"

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Make sure it's installed and your "
            "virtual environment is activated."
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
