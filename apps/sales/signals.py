"""
Sales Signals — Automatic Stock Adjustment

These signals ensure product.stock_quantity stays accurate
whenever a sale is created, updated, or deleted.

Connected in SalesConfig.ready() inside apps.py.

WHY SIGNALS (not overriding save/delete):
  Using signals keeps the Sale model clean and decouples
  the stock adjustment concern from the model definition.
  The analytics engine, serializers, and views don't need
  to know about stock management — signals handle it transparently.

STOCK ADJUSTMENT RULES:
  CREATE: stock -= new_quantity
  UPDATE: stock += old_quantity  (restore)  then  stock -= new_quantity  (re-apply)
  DELETE: stock += deleted_quantity  (restore)
"""
import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.products.models import Product

logger = logging.getLogger(__name__)


# We store the old quantity before an update so we can reconcile the stock delta.
# This dict maps sale_id → old_quantity during the update lifecycle.
_pre_update_quantities = {}


@receiver(pre_save, sender="sales.Sale")
def capture_old_quantity_before_update(sender, instance, **kwargs):
    """
    Before saving a Sale that already exists (update),
    store the current quantity so post_save can calculate the delta.
    """
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            _pre_update_quantities[instance.pk] = old_instance.quantity
        except sender.DoesNotExist:
            pass


@receiver(post_save, sender="sales.Sale")
def adjust_stock_on_save(sender, instance, created, **kwargs):
    """
    After a sale is saved:
      - On CREATE: decrement stock by the new quantity.
      - On UPDATE: restore the old quantity, then decrement by the new quantity.
    All operations run inside a select_for_update transaction to prevent race conditions.
    """
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=instance.product_id)

        if created:
            # New sale — reduce stock
            product.stock_quantity = max(0, product.stock_quantity - instance.quantity)
            logger.debug(
                "Stock adjusted on CREATE: Product #%s, -%s units → %s remaining",
                product.pk, instance.quantity, product.stock_quantity,
            )
        else:
            # Updated sale — reconcile stock delta
            old_qty = _pre_update_quantities.pop(instance.pk, 0)
            delta = instance.quantity - old_qty  # positive = more sold, negative = less sold
            product.stock_quantity = max(0, product.stock_quantity - delta)
            logger.debug(
                "Stock adjusted on UPDATE: Product #%s, old=%s new=%s delta=%s → %s remaining",
                product.pk, old_qty, instance.quantity, delta, product.stock_quantity,
            )

        product.save(update_fields=["stock_quantity"])


@receiver(post_delete, sender="sales.Sale")
def restore_stock_on_delete(sender, instance, **kwargs):
    """
    After a sale is deleted, restore the product stock by the deleted quantity.
    """
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=instance.product_id)
        product.stock_quantity += instance.quantity
        product.save(update_fields=["stock_quantity"])
        logger.debug(
            "Stock restored on DELETE: Product #%s, +%s units → %s remaining",
            product.pk, instance.quantity, product.stock_quantity,
        )
