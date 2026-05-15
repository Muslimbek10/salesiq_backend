"""
Alerts Model
============
Lightweight threshold-based system alerts.

Design decisions:
  - Alerts are lighter than recommendations — they flag a condition
    (e.g., "stock is low") without prescribing a specific action.
    The recommendation engine turns alert conditions into actionable advice.
  - Like recommendations, alerts are never hard-deleted. Dismissed alerts
    are set is_active=False for history.
  - AlertType maps directly to the six alert generator modules.
    Adding a new alert category requires adding it here and in alert_generator.py.
  - Deduplication: the alert engine checks whether an identical active alert
    already exists before creating a new one, preventing alert floods.
  - priority_color and type_icon are model-level helpers so the frontend
    does not need its own mapping logic.
"""
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------

class AlertQuerySet(models.QuerySet):

    def active(self):
        return self.filter(is_active=True)

    def dismissed(self):
        return self.filter(is_active=False)

    def high_priority(self):
        return self.filter(priority_level=Alert.Priority.HIGH)

    def by_type(self, alert_type):
        return self.filter(alert_type=alert_type)

    def low_stock_alerts(self):
        return self.filter(alert_type=Alert.AlertType.LOW_STOCK)

    def for_entity(self, entity_type, entity_id=None):
        qs = self.filter(related_entity_type=entity_type)
        if entity_id is not None:
            qs = qs.filter(related_entity_id=entity_id)
        return qs

    def priority_ordered(self):
        """Order High → Medium → Low, then newest first."""
        return self.annotate(
            priority_order=models.Case(
                models.When(priority_level=Alert.Priority.HIGH,   then=models.Value(1)),
                models.When(priority_level=Alert.Priority.MEDIUM, then=models.Value(2)),
                models.When(priority_level=Alert.Priority.LOW,    then=models.Value(3)),
                default=models.Value(4),
                output_field=models.IntegerField(),
            )
        ).order_by("priority_order", "-created_at")

    def recent(self, days=7):
        """Alerts created within the last N days."""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.filter(created_at__gte=cutoff)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Alert(models.Model):
    """
    A system alert triggered by a threshold violation or detected anomaly.

    Alert types:
        low_stock              → Product stock ≤ minimum_stock_level
        declining_sales        → Product sales declining for N consecutive months
        branch_underperformance→ Branch revenue < threshold% of company average
        sales_drop             → Abnormal week-over-week or month-over-month drop
        forecast_risk          → Forecast shows >20% revenue decline next period
        high_demand            → Product demand growing significantly (positive signal)

    Alert vs Recommendation:
        Alert       → "Something is wrong / notable right now."
        Recommendation → "Here is what you should do about it."
    """

    class AlertType(models.TextChoices):
        LOW_STOCK               = "low_stock",               "Low Stock"
        DECLINING_SALES         = "declining_sales",         "Declining Sales"
        BRANCH_UNDERPERFORMANCE = "branch_underperformance", "Branch Underperformance"
        SALES_DROP              = "sales_drop",              "Abnormal Sales Drop"
        FORECAST_RISK           = "forecast_risk",           "Forecast Risk"
        HIGH_DEMAND             = "high_demand",             "High Demand"

    class Priority(models.TextChoices):
        HIGH   = "High",   "High"
        MEDIUM = "Medium", "Medium"
        LOW    = "Low",    "Low"

    class EntityType(models.TextChoices):
        PRODUCT  = "product",  "Product"
        BRANCH   = "branch",   "Branch"
        CATEGORY = "category", "Category"
        CUSTOMER = "customer", "Customer"
        OVERALL  = "overall",  "Overall Business"

    # ------------------------------------------------------------------
    # Alert content
    # ------------------------------------------------------------------
    alert_type = models.CharField(
        max_length=50,
        choices=AlertType.choices,
        db_index=True,
        help_text="The category of condition that triggered this alert.",
    )
    alert_message = models.TextField(
        help_text="Plain-language description of the alert condition.",
    )

    # ------------------------------------------------------------------
    # Priority and severity
    # ------------------------------------------------------------------
    priority_level = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True,
        help_text="Urgency level: High (critical), Medium (warning), Low (informational).",
    )

    # ------------------------------------------------------------------
    # Related entity (soft polymorphic reference)
    # ------------------------------------------------------------------
    related_entity_type = models.CharField(
        max_length=20,
        choices=EntityType.choices,
        null=True,
        blank=True,
        help_text="Type of entity this alert is about.",
    )
    related_entity_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="PK of the related entity.",
    )
    related_entity_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Cached display name of the entity at alert creation time.",
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="False when dismissed by a user.",
    )
    dismissed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this alert was dismissed.",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    objects = AlertQuerySet.as_manager()

    class Meta:
        db_table         = "alerts"
        verbose_name     = "Alert"
        verbose_name_plural = "Alerts"
        ordering         = ["-created_at"]
        indexes = [
            models.Index(
                fields=["alert_type", "is_active"],
                name="idx_alert_type_active",
            ),
            models.Index(
                fields=["priority_level", "is_active", "created_at"],
                name="idx_alert_priority_active",
            ),
            models.Index(
                fields=["related_entity_type", "related_entity_id"],
                name="idx_alert_entity",
            ),
        ]

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------
    def __str__(self):
        msg_preview = self.alert_message[:70]
        if len(self.alert_message) > 70:
            msg_preview += "…"
        return f"[{self.priority_level}] {self.alert_type}: {msg_preview}"

    def __repr__(self):
        return (
            f"<Alert id={self.pk} type={self.alert_type!r} "
            f"priority={self.priority_level!r} active={self.is_active}>"
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def dismiss(self):
        """Dismiss this alert. Idempotent."""
        if self.is_active:
            self.is_active    = False
            self.dismissed_at = timezone.now()
            self.save(update_fields=["is_active", "dismissed_at"])

    def reactivate(self):
        """Re-activate a dismissed alert."""
        if not self.is_active:
            self.is_active    = True
            self.dismissed_at = None
            self.save(update_fields=["is_active", "dismissed_at"])

    # ------------------------------------------------------------------
    # Deduplication helper (used by the alert generator engine)
    # ------------------------------------------------------------------
    @classmethod
    def already_active(cls, alert_type, entity_type=None, entity_id=None):
        """
        Return True if an identical active alert already exists.
        The alert generator calls this before creating a new alert to prevent
        flooding the user with duplicate notifications.
        """
        qs = cls.objects.filter(alert_type=alert_type, is_active=True)
        if entity_type:
            qs = qs.filter(related_entity_type=entity_type)
        if entity_id is not None:
            qs = qs.filter(related_entity_id=entity_id)
        return qs.exists()

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def is_critical(self):
        """True for high-priority alerts — used for dashboard badge counts."""
        return self.priority_level == self.Priority.HIGH

    @property
    def priority_color(self):
        """Tailwind colour token for the badge in the frontend."""
        colors = {
            self.Priority.HIGH:   "red",
            self.Priority.MEDIUM: "amber",
            self.Priority.LOW:    "blue",
        }
        return colors.get(self.priority_level, "gray")

    @property
    def type_icon(self):
        """Lucide React icon name hint for the frontend."""
        icons = {
            self.AlertType.LOW_STOCK:               "package-x",
            self.AlertType.DECLINING_SALES:         "trending-down",
            self.AlertType.BRANCH_UNDERPERFORMANCE: "building-2",
            self.AlertType.SALES_DROP:              "activity",
            self.AlertType.FORECAST_RISK:           "alert-triangle",
            self.AlertType.HIGH_DEMAND:             "trending-up",
        }
        return icons.get(self.alert_type, "bell")
