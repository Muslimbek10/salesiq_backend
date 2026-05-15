"""
Categories Model
================
Product categories group products and drive category-level analytics.

Design decisions:
  - category_name is unique and case-normalized in clean() so "Electronics"
    and "electronics" cannot coexist.
  - product_count is a Python property (not annotated) to keep the model
    simple; the analytics engine always fetches counts via annotation.
  - The model is deliberately lean — categories rarely need more than a
    name and description.
"""
from django.core.exceptions import ValidationError
from django.db import models


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------

class CategoryQuerySet(models.QuerySet):
    """Chainable helpers for Category queries."""

    def with_product_count(self):
        """Annotate each category with the number of active products it has."""
        from django.db.models import Count
        return self.annotate(
            active_product_count=Count(
                "products",
                filter=models.Q(products__is_active=True),
            )
        )

    def non_empty(self):
        """Categories that have at least one active product."""
        from django.db.models import Count
        return self.annotate(
            active_product_count=Count(
                "products",
                filter=models.Q(products__is_active=True),
            )
        ).filter(active_product_count__gt=0)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Category(models.Model):
    """
    A product category.

    Each Product belongs to exactly one Category (FK on Product side).
    Deleting a category that has products is blocked at the DB level
    via PROTECT on the Product.category FK.

    Examples: Electronics, Clothing, Food & Beverages, Office Supplies
    """

    category_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique display name for the category. Case-normalized on save.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional extended description of what this category covers.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        db_table         = "categories"
        verbose_name     = "Category"
        verbose_name_plural = "Categories"
        ordering         = ["category_name"]
        constraints = [
            # PostgreSQL will use this for uniqueness — already covered by unique=True
            # but the constraint name makes the DB error message readable.
            models.UniqueConstraint(
                fields=["category_name"],
                name="uniq_category_name",
            ),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def clean(self):
        super().clean()
        if self.category_name:
            # Title-case normalize: "ELECTRONICS" → "Electronics"
            self.category_name = self.category_name.strip().title()
        if not self.category_name:
            raise ValidationError({"category_name": "Category name cannot be blank."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------
    def __str__(self):
        return self.category_name

    def __repr__(self):
        return f"<Category id={self.pk} name={self.category_name!r}>"

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def product_count(self):
        """Total number of products in this category (active + inactive)."""
        return self.products.count()

    @property
    def active_product_count(self):
        """Number of currently active products in this category."""
        return self.products.filter(is_active=True).count()
