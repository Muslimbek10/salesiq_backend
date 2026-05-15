"""
Sales Model
===========
Core transactional table. Each record is one sold line item.

Design decisions:
  - Financial fields (total_amount, total_cost, total_profit) are stored
    denormalized for analytics performance. Complex aggregations over millions
    of rows do not need to recalculate on every query.
  - calculate_financials() is a model method — a single source of truth for
    the computation logic used by the serializer, Admin, and the seed script.
  - clean() validates stock availability before a sale is persisted. This
    prevents overselling through any interface.
  - DB-level CheckConstraints catch invalid data that bypasses the ORM
    (e.g., direct SQL, migrations, or Admin bulk-edit).
  - The composite index on (branch, sale_date) optimises the most common
    dashboard query: "revenue for branch X between dates A and B".
  - Stock adjustment lives in signals.py, not here. Keeping the model focused
    on data representation, not side effects.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.branches.models import Branch
from apps.customers.models import Customer
from apps.products.models import Product


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------

class SaleQuerySet(models.QuerySet):

    def for_period(self, date_from, date_to):
        """Filter sales within an inclusive date range."""
        return self.filter(sale_date__gte=date_from, sale_date__lte=date_to)

    def for_branch(self, branch_id):
        return self.filter(branch_id=branch_id)

    def for_product(self, product_id):
        return self.filter(product_id=product_id)

    def for_customer(self, customer_id):
        return self.filter(customer_id=customer_id)

    def for_category(self, category_id):
        return self.filter(product__category_id=category_id)

    def with_relations(self):
        """Pre-join all FK tables to prevent N+1 in list views."""
        return self.select_related("product", "product__category", "customer", "branch")

    def totals(self):
        """
        Return a single dict with aggregate totals across the queryset.
        Used by the dashboard KPI endpoint.
        """
        return self.aggregate(
            total_revenue=    models.Sum("total_amount",  default=Decimal("0")),
            total_cost=       models.Sum("total_cost",    default=Decimal("0")),
            total_profit=     models.Sum("total_profit",  default=Decimal("0")),
            total_quantity=   models.Sum("quantity",      default=0),
            transaction_count=models.Count("id"),
        )

    def monthly_summary(self):
        """
        Group sales by calendar month.
        Returns dicts with month, total_revenue, total_profit, total_quantity.
        Used by time-series charts on the dashboard and analytics page.
        """
        from django.db.models.functions import TruncMonth
        return (
            self.annotate(month=TruncMonth("sale_date"))
                .values("month")
                .annotate(
                    total_revenue=  models.Sum("total_amount"),
                    total_profit=   models.Sum("total_profit"),
                    total_quantity= models.Sum("quantity"),
                    transaction_count=models.Count("id"),
                )
                .order_by("month")
        )


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Sale(models.Model):
    """
    A single completed sales transaction.

    Financial calculation rules:
        total_amount = quantity × unit_price
        total_cost   = quantity × product.cost_price  (at time of sale)
        total_profit = total_amount − total_cost

    These are computed by calculate_financials() and stored on save.
    The stored values are used directly by analytics queries for performance.

    Stock management:
        Creating a Sale   → stock decreases by quantity
        Updating a Sale   → stock reconciled for quantity delta
        Deleting a Sale   → stock restored by quantity
        (All via Django signals in sales/signals.py)
    """

    # ------------------------------------------------------------------
    # Foreign keys
    # ------------------------------------------------------------------
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,           # Block deletion of products with sales history
        related_name="sales",
        db_index=True,
        help_text="The product that was sold.",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,          # Preserve sale history if customer is deleted
        null=True,
        blank=True,
        related_name="sales",
        db_index=True,
        help_text="The purchasing customer. Null for anonymous walk-in sales.",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,           # Block deletion of branches with sales history
        related_name="sales",
        db_index=True,
        help_text="The branch where this sale occurred.",
    )

    # ------------------------------------------------------------------
    # Transaction fields
    # ------------------------------------------------------------------
    quantity = models.PositiveIntegerField(
        help_text="Number of units sold. Must be greater than zero.",
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Actual selling price per unit at the time of this sale.",
    )

    # ------------------------------------------------------------------
    # Denormalized financial fields (computed on save)
    # ------------------------------------------------------------------
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="quantity × unit_price. Computed automatically.",
    )
    total_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="quantity × product.cost_price at time of sale. Computed automatically.",
    )
    total_profit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="total_amount − total_cost. Computed automatically.",
    )

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------
    sale_date  = models.DateField(
        db_index=True,
        help_text="The calendar date when the sale took place.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SaleQuerySet.as_manager()

    class Meta:
        db_table         = "sales"
        verbose_name     = "Sale"
        verbose_name_plural = "Sales"
        ordering         = ["-sale_date", "-created_at"]
        indexes = [
            # Optimises "branch revenue between dates" — the most common dashboard filter
            models.Index(fields=["branch",   "sale_date"], name="idx_sales_branch_date"),
            # Optimises product sales trend queries
            models.Index(fields=["product",  "sale_date"], name="idx_sales_product_date"),
            # Optimises customer purchase history queries
            models.Index(fields=["customer", "sale_date"], name="idx_sales_customer_date"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name="chk_sale_quantity_positive",
            ),
            models.CheckConstraint(
                check=models.Q(unit_price__gte=0),
                name="chk_sale_unit_price_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(total_amount__gte=0),
                name="chk_sale_total_amount_non_negative",
            ),
        ]

    # ------------------------------------------------------------------
    # Financial calculation
    # ------------------------------------------------------------------
    def calculate_financials(self):
        """
        Compute and set total_amount, total_cost, and total_profit.

        Called by:
          - The serializer's create() and update() methods.
          - The save() override below as a safety net.
          - The seed data script.

        Requires: self.product, self.quantity, self.unit_price are already set.
        """
        if self.product_id is None or self.quantity is None or self.unit_price is None:
            return  # Cannot compute yet — fields not ready

        qty            = Decimal(str(self.quantity))
        unit_price     = Decimal(str(self.unit_price))
        cost_price     = Decimal(str(self.product.cost_price))

        self.total_amount = qty * unit_price
        self.total_cost   = qty * cost_price
        self.total_profit = self.total_amount - self.total_cost

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def clean(self):
        super().clean()

        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})

        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({"unit_price": "Unit price cannot be negative."})

        # Stock availability check (only on new sales, not updates)
        if self.product_id and self.quantity:
            try:
                product = self.product if hasattr(self, "_product_cache") else Product.objects.get(pk=self.product_id)
            except Product.DoesNotExist:
                raise ValidationError({"product": "Selected product does not exist."})

            if not product.is_active:
                raise ValidationError({"product": f"Product '{product.product_name}' is not active."})

            # On update: only check if new quantity exceeds old quantity + current stock
            existing_qty = 0
            if self.pk:
                try:
                    existing_qty = Sale.objects.get(pk=self.pk).quantity
                except Sale.DoesNotExist:
                    pass

            available = product.stock_quantity + existing_qty
            if self.quantity > available:
                raise ValidationError({
                    "quantity": (
                        f"Insufficient stock for '{product.product_name}'. "
                        f"Available: {available} units, requested: {self.quantity} units."
                    )
                })

    def save(self, *args, **kwargs):
        # Ensure financials are always current when the product FK is loaded
        if self.product_id and hasattr(self, "product"):
            self.calculate_financials()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------
    def __str__(self):
        product_name = self.product.product_name if self.product_id else "?"
        return f"Sale #{self.pk} — {product_name} × {self.quantity} on {self.sale_date}"

    def __repr__(self):
        return (
            f"<Sale id={self.pk} product_id={self.product_id} "
            f"qty={self.quantity} date={self.sale_date}>"
        )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def profit_margin_percentage(self):
        """Margin on this specific sale transaction."""
        if not self.total_amount:
            return Decimal("0")
        return round((self.total_profit / self.total_amount) * 100, 2)

    @property
    def is_profitable(self):
        """True when this sale generated positive profit."""
        return self.total_profit is not None and self.total_profit > 0
