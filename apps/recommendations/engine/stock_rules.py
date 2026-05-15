"""
Stock Rules
===========
Generates restock recommendations for products at or below their
minimum_stock_level.

Rules
-----
OUT_OF_STOCK  (HIGH)   stock_quantity == 0
CRITICAL_LOW  (HIGH)   0 < stock_quantity <= 50% of minimum_stock_level
LOW_STOCK     (MEDIUM) 50% < stock_quantity <= minimum_stock_level

Deduplication: no new recommendation is created if an identical active
RESTOCK recommendation already exists for the same product.
"""
from django.db.models import F

from apps.products.models import Product
from apps.recommendations.models import Recommendation

R = Recommendation
RT = R.RecommendationType
ET = R.EntityType
P  = R.Priority


def _already_active(product_id):
    return R.objects.filter(
        recommendation_type=RT.RESTOCK,
        related_entity_type=ET.PRODUCT,
        related_entity_id=product_id,
        is_active=True,
    ).exists()


def check_low_stock():
    """
    Scan all active products at or below minimum_stock_level.
    Creates one RESTOCK recommendation per qualifying product
    (skips products that already have an active one).

    Returns
    -------
    list[Recommendation] — newly created records
    """
    products = (
        Product.objects
        .select_related("category")
        .filter(is_active=True, stock_quantity__lte=F("minimum_stock_level"))
        .order_by("stock_quantity")
    )

    created = []
    for product in products:
        if _already_active(product.pk):
            continue

        stock   = product.stock_quantity
        minimum = product.minimum_stock_level
        sku     = product.sku
        name    = product.product_name

        if stock <= 0:
            priority = P.HIGH
            text = (
                f"OUT OF STOCK: '{name}' (SKU: {sku}) has 0 units remaining. "
                f"Immediate restocking is required to prevent lost sales. "
                f"Review supplier lead times and place an urgent purchase order."
            )
        elif minimum > 0 and stock <= minimum * 0.5:
            shortage = minimum - stock
            priority = P.HIGH
            text = (
                f"Critical low stock for '{name}' (SKU: {sku}): only {stock} units left "
                f"(minimum threshold: {minimum} units). "
                f"Order at least {shortage} units immediately to avoid a stockout."
            )
        else:
            shortage = minimum - stock
            priority = P.MEDIUM
            text = (
                f"Low stock warning for '{name}' (SKU: {sku}): {stock} units remaining "
                f"(minimum threshold: {minimum} units). "
                f"Consider ordering {shortage} additional units to restore safe stock levels."
            )

        rec = R.objects.create(
            recommendation_text=text,
            recommendation_type=RT.RESTOCK,
            related_entity_type=ET.PRODUCT,
            related_entity_id=product.pk,
            related_entity_name=name,
            priority_level=priority,
        )
        created.append(rec)

    return created
