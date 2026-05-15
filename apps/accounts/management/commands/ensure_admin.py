"""
Management command: ensure_admin
=================================
Creates the default admin user if it does not already exist.
Safe to run multiple times — idempotent.

Usage:
    python manage.py ensure_admin
    python manage.py ensure_admin --username admin --password admin123

Called automatically by docker-compose on every container start,
so the admin account is always available after a fresh database.
"""
import os

from django.core.management.base import BaseCommand

from apps.accounts.models import CustomUser


class Command(BaseCommand):
    help = "Create the default admin superuser if it does not already exist."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.environ.get("ADMIN_USERNAME", "admin"),
            help="Admin username (default: admin)",
        )
        parser.add_argument(
            "--password",
            default=os.environ.get("ADMIN_PASSWORD", "admin123"),
            help="Admin password (default: admin123)",
        )
        parser.add_argument(
            "--email",
            default=os.environ.get("ADMIN_EMAIL", "admin@salesiq.local"),
            help="Admin email (default: admin@salesiq.local)",
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        email    = options["email"]

        if CustomUser.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Admin user '{username}' already exists — skipping creation."
                )
            )
            return

        CustomUser.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name="Admin",
            last_name="User",
            role=CustomUser.Role.ADMIN,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Superuser '{username}' created successfully. "
                f"Login at http://localhost:8000/admin/"
            )
        )
