from django.apps import AppConfig


class SalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sales"
    label = "sales"
    verbose_name = "Sales Transactions"

    def ready(self):
        # Connect signals when the app is ready.
        # This ensures stock adjustment runs on every sale create/update/delete.
        import apps.sales.signals  # noqa: F401
