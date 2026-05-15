"""
Products Model
==============
The product catalog is the central reference table for both sales and analytics.

Design decisions:
  - cost_price and selling_price use DecimalField (never FloatField for money).
  - DB-level CheckConstraints enforce non-negative prices and quantities so
    bad data cannot be inserted by any path — ORM, raw SQL, or Admin.
  - stock_quantity is managed automatically by signals in the sales app.
    It must NEVER be decremented directly except through that signal.
  - is_active soft-deletes products. Historical sales still reference them.
  - StockStatus enum centralises stock health logic used by the alert engine,
    the recommendation engine, and the dashboard.
  - clean() validates that selling_price >= cost_price to prevent negative
    margins from being persisted.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from apps.categories.models import Category


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------

class ProductQuerySet(models.QuerySet):

    def active(self):
        """Products available for sale."""
        return self.filter(is_active=True)

    def inactive(self):
        return self.filter(is_active=False)

    def low_stock(self):
        """Products where current stock is at or below the minimum threshold."""
        return self.filter(stock_quantity__lte=models.F("minimum_stock_level"))

    def out_of_stock(self):
        return self.filter(stock_quantity=0)

    def by_category(self, category_id):
        return self.filter(category_id=category_id)

    def with_sales_totals(self, date_from=None, date_to=None):
        """
        Annotate each product with aggregate sales figures.
        Optionally filtered by date range.
        """
        sale_filter = models.Q()
        if date_from:
            sale_filter &= models.Q(sales__sale_date__gte=date_from)
        if date_to:
            sale_filter &= models.Q(sales__sale_date__lte=date_to)

        return self.annotate(
            total_units_sold=models.Sum("sales__quantity",    filter=sale_filter, default=0),
            total_revenue=   models.Sum("sales__total_amount", filter=sale_filter, default=Decimal("0")),
            total_profit=    models.Sum("sales__total_profit", filter=sale_filter, default=Decimal("0")),
        )

    def select_with_category(self):
        """Eagerly load category to avoid N+1 in list views."""
        return self.select_related("category")


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Product(models.Model):
    """
    A single product in the business catalog.

    Stock lifecycle:
        1. Created with an initial stock_quantity.
        2. Each Sale decrements stock via a post_save signal.
        3. Editing or deleting a Sale reconciles the stock delta.
        4. When stock_quantity <= minimum_stock_level → StockStatus.LOW.
        5. When stock_quantity == 0 → StockStatus.OUT.

    Pricing:
        cost_price    = what the business pays per unit.
        selling_price = what the customer pays per unit.
        margin        = (selling_price - cost_price) / selling_price * 100
    """

    class StockStatus(models.TextChoices):
        OK      = "ok",       "In Stock"
        LOW     = "low",      "Low Stock"
        OUT     = "out",      "Out of Stock"

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------
    product_name = models.CharField(
        max_length=255,
        help_text="Full display name of the product.",
    )
    sku = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        null=True,
        help_text="Stock Keeping Unit — unique product code. Optional.",
    )

    # ------------------------------------------------------------------
    # Categorisation
    # ------------------------------------------------------------------
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,       # Prevent orphaning products by deleting their category
        related_name="products",
        db_index=True,
        help_text="The product category this item belongs to.",
    )

    # ------------------------------------------------------------------
    # Pricing — always use Decimal for money
    # ------------------------------------------------------------------
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Per-unit purchase or production cost. Must be ≥ 0.",
    )
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Per-unit retail price charged to the customer. Must be ≥ cost_price.",
    )

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------
    stock_quantity = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Current available stock units. "
            "Do NOT update this directly — it is managed automatically by sale signals."
        ),
    )
    minimum_stock_level = models.PositiveIntegerField(
        default=10,
        help_text=(
            "When stock_quantity falls to or below this value, "
            "a low-stock alert and restock recommendation are generated."
        ),
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=(
            "Inactive products are hidden from sale entry forms "
            "but are preserved for historical sales data integrity."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        db_table         = "products"
        verbose_name     = "Product"
        verbose_name_plural = "Products"
        ordering         = ["product_name"]
        indexes = [
            models.Index(fields=["category", "is_active"],   name="idx_products_cat_active"),
            models.Index(fields=["is_active", "stock_quantity"], name="idx_products_active_stock"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(cost_price__gte=0),
                name="chk_product_cost_price_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(selling_price__gte=0),
                name="chk_product_selling_price_non_negative",
            ),
            # stock_quantity is PositiveIntegerField — DB ≥ 0 is implicit.
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def clean(self):
        super().clean()

        if self.cost_price is not None and self.cost_price < 0:
            raise ValidationError({"cost_price": "Cost price cannot be negative."})

        if self.selling_price is not None and self.selling_price < 0:
            raise ValidationError({"selling_price": "Selling price cannot be negative."})

        if (
            self.cost_price is not None
            and self.selling_price is not None
            and self.selling_price < self.cost_price
        ):
            raise ValidationError({
                "selling_price": (
                    f"Selling price ({self.selling_price}) cannot be less than "
                    f"cost price ({self.cost_price}). This would result in a negative margin."
                )
            })

        if self.minimum_stock_level is not None and self.minimum_stock_level < 0:
            raise ValidationError({
                "minimum_stock_level": "Minimum stock level cannot be negative."
            })

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------
    def __str__(self):
        sku_label = f"SKU: {self.sku}" if self.sku else "No SKU"
        return f"{self.product_name} ({sku_label})"

    def __repr__(self):
        return (
            f"<Product id={self.pk} name={self.product_name!r} "
            f"stock={self.stock_quantity} active={self.is_active}>"
        )

    # ------------------------------------------------------------------
    # Stock status
    # ------------------------------------------------------------------
    @property
    def stock_status(self):
        """
        Three-state stock health indicator.
        Used by alert engine, recommendation engine, and dashboard badges.
        """
        if self.stock_quantity == 0:
            return self.StockStatus.OUT
        if self.stock_quantity <= self.minimum_stock_level:
            return self.StockStatus.LOW
        return self.StockStatus.OK

    @property
    def is_low_stock(self):
        """True when stock is at or below the minimum threshold (includes out-of-stock)."""
        return self.stock_quantity <= self.minimum_stock_level

    @property
    def is_out_of_stock(self):
        return self.stock_quantity == 0

    @property
    def stock_shortage(self):
        """
        How many units below minimum the product currently is.
        Returns 0 if stock is healthy.
        """
        return max(0, self.minimum_stock_level - self.stock_quantity)

    # ------------------------------------------------------------------
    # Pricing & margin
    # ------------------------------------------------------------------
    @property
    def margin_amount(self):
        """Gross profit per unit in currency."""
        if self.selling_price is None or self.cost_price is None:
            return Decimal("0")
        return self.selling_price - self.cost_price

    @property
    def margin_percentage(self):
        """
        Gross margin as a percentage of selling price.
        Returns 0 when selling_price is zero to avoid ZeroDivisionError.
        """
        if not self.selling_price:
            return Decimal("0")
        return round(
            (self.margin_amount / self.selling_price) * 100,
            2,
        )

    # ------------------------------------------------------------------
    # Sales summary helpers (used in analytics views)
    # ------------------------------------------------------------------
    def total_revenue(self, date_from=None, date_to=None):
        """Total revenue generated by this product over an optional date range."""
        qs = self.sales.all()
        if date_from:
            qs = qs.filter(sale_date__gte=date_from)
        if date_to:
            qs = qs.filter(sale_date__lte=date_to)
        return qs.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")

    def total_units_sold(self, date_from=None, date_to=None):
        """Total units sold over an optional date range."""
        qs = self.sales.all()
        if date_from:
            qs = qs.filter(sale_date__gte=date_from)
        if date_to:
            qs = qs.filter(sale_date__lte=date_to)
        return qs.aggregate(total=Sum("quantity"))["total"] or 0
