"""
Customers Model
===============
Customer master data used in sales transactions and analytics segmentation.

Design decisions:
  - phone and email are optional — anonymous or partial records are common
    in retail scenarios.
  - customer_type drives segmentation analytics and recommendation targeting.
  - region enables geographic trend analysis across branches.
  - The model intentionally has no FK to sales — the relationship is defined
    on the Sale side (Sale.customer FK). This keeps Customer lightweight.
  - days_since_last_purchase is a property used by the customer retention
    recommendation rule to detect dormant high-value customers.
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------

class CustomerQuerySet(models.QuerySet):

    def by_type(self, customer_type):
        return self.filter(customer_type=customer_type)

    def vip(self):
        return self.filter(customer_type=Customer.CustomerType.VIP)

    def corporate(self):
        return self.filter(customer_type=Customer.CustomerType.CORPORATE)

    def wholesale(self):
        return self.filter(customer_type=Customer.CustomerType.WHOLESALE)

    def by_region(self, region):
        return self.filter(region__iexact=region)

    def high_value(self):
        """VIP and Corporate customers combined."""
        return self.filter(
            customer_type__in=[
                Customer.CustomerType.VIP,
                Customer.CustomerType.CORPORATE,
            ]
        )

    def with_purchase_stats(self, date_from=None, date_to=None):
        """
        Annotate each customer with sales aggregates.
        Optionally filtered by date range.
        """
        from decimal import Decimal
        sale_filter = models.Q()
        if date_from:
            sale_filter &= models.Q(sales__sale_date__gte=date_from)
        if date_to:
            sale_filter &= models.Q(sales__sale_date__lte=date_to)

        return self.annotate(
            total_purchases=models.Count("sales",                                  filter=sale_filter),
            total_spent=    models.Sum("sales__total_amount", default=Decimal("0"), filter=sale_filter),
            last_purchase=  models.Max("sales__sale_date",                         filter=sale_filter),
        )

    def with_last_purchase(self):
        """Annotate with the most recent sale date — used by retention rules."""
        return self.annotate(last_purchase=models.Max("sales__sale_date"))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Customer(models.Model):
    """
    A business customer. Sales can be linked to a customer or left anonymous.

    Customer types drive segmentation analytics:
        Retail     → Individual walk-in buyers
        Wholesale  → Bulk purchasers, typically at lower unit prices
        VIP        → High-value retained customers (loyalty programs)
        Corporate  → Business accounts with contracts or credit lines
    """

    class CustomerType(models.TextChoices):
        RETAIL    = "Retail",    "Retail"
        WHOLESALE = "Wholesale", "Wholesale"
        VIP       = "VIP",       "VIP"
        CORPORATE = "Corporate", "Corporate"

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    full_name = models.CharField(
        max_length=255,
        help_text="Customer's full display name.",
    )
    phone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Contact phone number. Optional.",
    )
    email = models.EmailField(
        max_length=255,
        blank=True,
        default="",
        help_text="Contact email address. Optional.",
    )

    # ------------------------------------------------------------------
    # Segmentation
    # ------------------------------------------------------------------
    region = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Geographic sales region (e.g. 'North', 'East', 'Capital'). Used for regional analytics.",
    )
    customer_type = models.CharField(
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.RETAIL,
        db_index=True,
        help_text="Segment drives recommendation targeting and analytics grouping.",
    )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomerQuerySet.as_manager()

    class Meta:
        db_table         = "customers"
        verbose_name     = "Customer"
        verbose_name_plural = "Customers"
        ordering         = ["full_name"]
        indexes = [
            models.Index(fields=["customer_type", "region"], name="idx_customer_type_region"),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def clean(self):
        super().clean()
        if self.full_name:
            self.full_name = self.full_name.strip()
        if not self.full_name:
            raise ValidationError({"full_name": "Customer name cannot be blank."})

        if self.region:
            # Normalize region to title-case ("north" → "North")
            self.region = self.region.strip().title()

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------
    def __str__(self):
        return f"{self.full_name} ({self.customer_type})"

    def __repr__(self):
        return f"<Customer id={self.pk} name={self.full_name!r} type={self.customer_type!r}>"

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def is_high_value(self):
        """True for VIP and Corporate customers."""
        return self.customer_type in (self.CustomerType.VIP, self.CustomerType.CORPORATE)

    @property
    def purchase_count(self):
        """Total number of sales linked to this customer."""
        return self.sales.count()

    @property
    def last_purchase_date(self):
        """Date of most recent sale, or None if no sales exist."""
        latest = self.sales.order_by("-sale_date").values_list("sale_date", flat=True).first()
        return latest

    @property
    def days_since_last_purchase(self):
        """
        Number of days since the most recent purchase.
        Returns None if the customer has never purchased.
        Used by the customer retention recommendation rule.
        """
        last = self.last_purchase_date
        if last is None:
            return None
        return (date.today() - last).days

    @property
    def is_dormant(self):
        """
        True if the customer has not purchased in the last 60 days.
        High-value dormant customers trigger retention recommendations.
        """
        days = self.days_since_last_purchase
        return days is not None and days >= 60
