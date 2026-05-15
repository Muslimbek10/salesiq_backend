"""
Branches Model
==============
Physical store locations or business offices.

Design decisions:
  - is_active allows soft-deactivation of a branch without losing
    its historical sales data.
  - branch_name is unique so the branch comparison analytics can use it
    as an unambiguous label in charts.
  - performance_vs_average is a Python method (not annotated) — the
    analytics engine computes comparisons with annotated QuerySets.
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from decimal import Decimal


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------

class BranchQuerySet(models.QuerySet):

    def active(self):
        return self.filter(is_active=True)

    def inactive(self):
        return self.filter(is_active=False)

    def with_revenue(self, date_from=None, date_to=None):
        """Annotate each branch with total revenue over an optional date range."""
        sale_filter = models.Q()
        if date_from:
            sale_filter &= models.Q(sales__sale_date__gte=date_from)
        if date_to:
            sale_filter &= models.Q(sales__sale_date__lte=date_to)

        return self.annotate(
            total_revenue=models.Sum(
                "sales__total_amount",
                filter=sale_filter,
                default=Decimal("0"),
            ),
            total_profit=models.Sum(
                "sales__total_profit",
                filter=sale_filter,
                default=Decimal("0"),
            ),
            total_transactions=models.Count(
                "sales",
                filter=sale_filter,
            ),
        )


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Branch(models.Model):
    """
    A business branch (physical store or office).

    Every Sale is associated with exactly one Branch.
    Branch analytics compare revenue, profit, and transaction count
    across all branches to surface performance gaps.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    branch_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique display name for this branch. Used as a label in analytics charts.",
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Physical address or city of this branch.",
    )
    manager_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Name of the branch manager. Informational only.",
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Inactive branches are hidden from sale entry but retained for historical data.",
    )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BranchQuerySet.as_manager()

    class Meta:
        db_table         = "branches"
        verbose_name     = "Branch"
        verbose_name_plural = "Branches"
        ordering         = ["branch_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch_name"],
                name="uniq_branch_name",
            ),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def clean(self):
        super().clean()
        if self.branch_name:
            self.branch_name = self.branch_name.strip()
        if not self.branch_name:
            raise ValidationError({"branch_name": "Branch name cannot be blank."})

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------
    def __str__(self):
        return self.branch_name

    def __repr__(self):
        return f"<Branch id={self.pk} name={self.branch_name!r} active={self.is_active}>"

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def total_sales_count(self):
        """Total number of sales transactions at this branch."""
        return self.sales.count()

    @property
    def total_revenue(self):
        """Lifetime total revenue at this branch."""
        result = self.sales.aggregate(total=Sum("total_amount"))["total"]
        return result or Decimal("0")

    @property
    def total_profit(self):
        """Lifetime total profit at this branch."""
        result = self.sales.aggregate(total=Sum("total_profit"))["total"]
        return result or Decimal("0")
