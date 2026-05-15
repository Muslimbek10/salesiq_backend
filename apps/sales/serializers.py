"""
Sales Serializers
=================

SaleListSerializer
  Optimised for the paginated sales table.
  Embeds product_name, category_name, customer_name, branch_name directly
  so the frontend table row never needs to join or look up names separately.

SaleDetailSerializer
  Full nested representation for the single-sale retrieve endpoint.
  Includes full nested product, customer, branch objects.

SaleCreateSerializer
  Write serializer for creating a new sale.
  Responsibilities:
    - Validate quantity > 0 and unit_price >= 0.
    - Check that the product is active.
    - Check that sufficient stock exists.
    - Compute total_amount, total_cost, total_profit via calculate_financials().
    - Save the sale. The post_save signal then decrements product.stock_quantity.

SaleUpdateSerializer
  Write serializer for partial updates (quantity, unit_price, sale_date, customer, branch).
  Intentionally blocks product FK changes — changing the product on an existing sale
  would require complex multi-product stock reconciliation. Cancel + re-create instead.
  The pre_save/post_save signals handle the quantity delta automatically.

KEY SIGNAL INTERACTION:
  - SaleCreateSerializer.create() saves the sale.
  - signals.post_save fires, decrements product stock by sale.quantity.
  - SaleUpdateSerializer.update() saves with new quantity.
  - signals.pre_save captured old quantity before the save.
  - signals.post_save fires, computes delta = new_qty - old_qty, adjusts stock.
  - No stock manipulation happens in the serializer — signals own that concern.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework import serializers

from apps.branches.models import Branch
from apps.customers.models import Customer
from apps.products.models import Product

from .models import Sale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_decimal(value):
    """Safely convert a value to Decimal."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal("0")


# ---------------------------------------------------------------------------
# Read serializers
# ---------------------------------------------------------------------------

class SaleListSerializer(serializers.ModelSerializer):
    """
    Flat list serializer optimised for the sales table.
    All FK names are resolved as flat string fields — no nested objects.
    Avoids N+1 because the queryset uses select_related().
    """
    product_name    = serializers.CharField(source="product.product_name",  read_only=True)
    category_name   = serializers.CharField(source="product.category.category_name", read_only=True)
    sku             = serializers.CharField(source="product.sku",           read_only=True)
    customer_name   = serializers.SerializerMethodField()
    branch_name     = serializers.CharField(source="branch.branch_name",    read_only=True)
    profit_margin   = serializers.SerializerMethodField()

    class Meta:
        model  = Sale
        fields = [
            "id",
            "product_id",
            "product_name",
            "sku",
            "category_name",
            "customer_id",
            "customer_name",
            "branch_id",
            "branch_name",
            "quantity",
            "unit_price",
            "total_amount",
            "total_cost",
            "total_profit",
            "profit_margin",
            "sale_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_customer_name(self, obj):
        """Returns customer full_name or 'Walk-in' for anonymous sales."""
        if obj.customer_id and obj.customer:
            return obj.customer.full_name
        return "Walk-in"

    def get_profit_margin(self, obj):
        """Gross margin percentage for this sale."""
        if obj.total_amount and obj.total_amount > 0:
            return float(round(obj.total_profit / obj.total_amount * 100, 2))
        return 0.0


class SaleDetailSerializer(serializers.ModelSerializer):
    """
    Full nested detail view for a single sale.
    Used on retrieve — not on list (would cause N+1).
    """
    product = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    branch = serializers.SerializerMethodField()
    profit_margin = serializers.SerializerMethodField()
    is_profitable = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Sale
        fields = [
            "id",
            "product",
            "customer",
            "branch",
            "quantity",
            "unit_price",
            "total_amount",
            "total_cost",
            "total_profit",
            "profit_margin",
            "is_profitable",
            "sale_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_product(self, obj):
        return {
            "id":            obj.product.pk,
            "product_name":  obj.product.product_name,
            "sku":           obj.product.sku,
            "category_id":   obj.product.category_id,
            "category_name": obj.product.category.category_name,
            "cost_price":    float(obj.product.cost_price),
            "selling_price": float(obj.product.selling_price),
        }

    def get_customer(self, obj):
        if not obj.customer_id:
            return None
        return {
            "id":            obj.customer.pk,
            "full_name":     obj.customer.full_name,
            "customer_type": obj.customer.customer_type,
            "region":        obj.customer.region,
        }

    def get_branch(self, obj):
        return {
            "id":          obj.branch.pk,
            "branch_name": obj.branch.branch_name,
            "location":    obj.branch.location,
        }

    def get_profit_margin(self, obj):
        return float(obj.profit_margin_percentage)


# ---------------------------------------------------------------------------
# Write serializers
# ---------------------------------------------------------------------------

class SaleCreateSerializer(serializers.Serializer):
    """
    Write serializer for creating a new sale.

    Accepts FK ids (product_id, customer_id, branch_id) not nested objects.
    Validates stock availability before allowing the save.
    Computes all financial fields via Sale.calculate_financials().
    """
    product_id    = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source="product",
        help_text="ID of the product being sold.",
    )
    customer_id   = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        source="customer",
        required=False,
        allow_null=True,
        default=None,
        help_text="ID of the customer. Null for anonymous walk-in sales.",
    )
    branch_id     = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(),
        source="branch",
        help_text="ID of the branch where the sale occurred.",
    )
    quantity      = serializers.IntegerField(min_value=1, help_text="Number of units sold.")
    unit_price    = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"),
        help_text="Selling price per unit for this transaction.",
    )
    sale_date     = serializers.DateField(help_text="Date the sale occurred (YYYY-MM-DD).")

    def validate(self, data):
        product  = data["product"]
        quantity = data["quantity"]

        # Product must be active
        if not product.is_active:
            raise serializers.ValidationError({
                "product_id": f"'{product.product_name}' is inactive and cannot be sold."
            })

        # Check stock availability
        if product.stock_quantity < quantity:
            raise serializers.ValidationError({
                "quantity": (
                    f"Insufficient stock for '{product.product_name}'. "
                    f"Available: {product.stock_quantity} units, "
                    f"requested: {quantity} units."
                )
            })

        return data

    @transaction.atomic
    def create(self, validated_data):
        """
        Create the Sale, compute financial fields, and save.
        Stock adjustment happens automatically via the post_save signal.
        """
        sale = Sale(
            product    = validated_data["product"],
            customer   = validated_data.get("customer"),
            branch     = validated_data["branch"],
            quantity   = validated_data["quantity"],
            unit_price = validated_data["unit_price"],
            sale_date  = validated_data["sale_date"],
            # Temporary zeros — overwritten by calculate_financials below
            total_amount = Decimal("0"),
            total_cost   = Decimal("0"),
            total_profit = Decimal("0"),
        )
        sale.calculate_financials()
        sale.save()
        return sale

    def to_representation(self, instance):
        """Return a full SaleListSerializer view after creation."""
        instance_with_relations = (
            Sale.objects
            .select_related("product", "product__category", "customer", "branch")
            .get(pk=instance.pk)
        )
        return SaleListSerializer(instance_with_relations, context=self.context).data


class SaleUpdateSerializer(serializers.Serializer):
    """
    Write serializer for updating an existing sale.

    Deliberately excludes product_id — changing the sold product on an existing
    sale creates complex multi-product stock reconciliation that is error-prone.
    The correct workflow is: delete the wrong sale and create a new one.

    The signals handle quantity delta reconciliation automatically:
      pre_save  captures old_quantity
      post_save adjusts stock by (new_quantity - old_quantity)
    """
    customer_id = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        source="customer",
        required=False,
        allow_null=True,
    )
    branch_id   = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(),
        source="branch",
        required=False,
    )
    quantity    = serializers.IntegerField(min_value=1, required=False)
    unit_price  = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    sale_date   = serializers.DateField(required=False)

    def validate(self, data):
        instance = self.instance
        new_qty  = data.get("quantity", instance.quantity)
        product  = instance.product

        # Stock check: available = current stock + old quantity (which will be restored by signal)
        available = product.stock_quantity + instance.quantity
        if new_qty > available:
            raise serializers.ValidationError({
                "quantity": (
                    f"Insufficient stock for '{product.product_name}'. "
                    f"Effective available: {available} units, "
                    f"requested: {new_qty} units."
                )
            })

        return data

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        Apply validated fields to the instance and recompute financials.
        The pre_save signal captured old_quantity before this call.
        The post_save signal will reconcile the stock delta after save().
        """
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.calculate_financials()
        instance.save()
        return instance

    def to_representation(self, instance):
        instance_with_relations = (
            Sale.objects
            .select_related("product", "product__category", "customer", "branch")
            .get(pk=instance.pk)
        )
        return SaleListSerializer(instance_with_relations, context=self.context).data
