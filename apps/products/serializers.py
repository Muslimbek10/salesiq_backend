"""
Products Serializers
====================

ProductListSerializer
  Lightweight read serializer for the paginated list endpoint.
  Includes category_name inline (no extra FK lookup), stock_status badge,
  and margin_percentage. Optimised for table rows in the frontend.

ProductDetailSerializer
  Full representation for the single-product retrieve endpoint.
  Includes the full nested category object.

ProductCreateUpdateSerializer
  Write serializer for create and update.
  Accepts category as category_id (integer FK).
  Validates price consistency and delegates to model.full_clean()
  for business rule enforcement.

ProductDropdownSerializer
  Minimal id + name + sku for populating sale form product selects.
"""
from decimal import Decimal

from rest_framework import serializers

from apps.categories.serializers import CategorySerializer

from .models import Product


# ---------------------------------------------------------------------------
# Read serializers
# ---------------------------------------------------------------------------

class ProductListSerializer(serializers.ModelSerializer):
    """
    Optimised for the product list table.
    category_name is a direct field to avoid nested object overhead.
    """
    category_name      = serializers.CharField(source="category.category_name", read_only=True)
    stock_status       = serializers.CharField(read_only=True)
    stock_status_label = serializers.SerializerMethodField()
    margin_percentage  = serializers.DecimalField(
        max_digits=6, decimal_places=2, read_only=True
    )
    is_low_stock       = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Product
        fields = [
            "id",
            "product_name",
            "sku",
            "category_id",
            "category_name",
            "cost_price",
            "selling_price",
            "margin_percentage",
            "stock_quantity",
            "minimum_stock_level",
            "stock_status",
            "stock_status_label",
            "is_low_stock",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_stock_status_label(self, obj):
        labels = {
            Product.StockStatus.OK:  "In Stock",
            Product.StockStatus.LOW: "Low Stock",
            Product.StockStatus.OUT: "Out of Stock",
        }
        return labels.get(obj.stock_status, "Unknown")


class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Full product detail with nested category and all computed fields.
    """
    category          = CategorySerializer(read_only=True)
    stock_status      = serializers.CharField(read_only=True)
    margin_amount     = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    margin_percentage = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    is_low_stock      = serializers.BooleanField(read_only=True)
    is_out_of_stock   = serializers.BooleanField(read_only=True)
    stock_shortage    = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Product
        fields = [
            "id",
            "product_name",
            "sku",
            "category",
            "cost_price",
            "selling_price",
            "margin_amount",
            "margin_percentage",
            "stock_quantity",
            "minimum_stock_level",
            "stock_status",
            "is_low_stock",
            "is_out_of_stock",
            "stock_shortage",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Write serializer
# ---------------------------------------------------------------------------

class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Write serializer for product create and update.
    Accepts category_id as a plain integer.
    Returns a ProductListSerializer representation after save.
    """

    class Meta:
        model  = Product
        fields = [
            "product_name",
            "sku",
            "category",          # DRF resolves FK by PrimaryKeyRelatedField
            "cost_price",
            "selling_price",
            "stock_quantity",
            "minimum_stock_level",
            "is_active",
        ]
        extra_kwargs = {
            "sku":               {"required": False, "allow_null": True},
            "stock_quantity":    {"required": False, "default": 0},
            "minimum_stock_level": {"required": False, "default": 10},
            "is_active":         {"required": False, "default": True},
        }

    def validate_cost_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Cost price cannot be negative.")
        return value

    def validate_selling_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Selling price cannot be negative.")
        return value

    def validate(self, data):
        cost_price    = data.get("cost_price",    getattr(self.instance, "cost_price",    None))
        selling_price = data.get("selling_price", getattr(self.instance, "selling_price", None))

        if cost_price is not None and selling_price is not None:
            if selling_price < cost_price:
                raise serializers.ValidationError({
                    "selling_price": (
                        f"Selling price ({selling_price}) must be ≥ cost price ({cost_price}). "
                        "A negative margin is not allowed."
                    )
                })

        # SKU uniqueness check excluding self on update
        sku = data.get("sku")
        if sku:
            qs = Product.objects.filter(sku=sku)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"sku": f"A product with SKU '{sku}' already exists."}
                )

        return data

    def create(self, validated_data):
        product = Product(**validated_data)
        product.full_clean()
        product.save()
        return product

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        return instance

    def to_representation(self, instance):
        """Return a full ProductListSerializer view after write operations."""
        return ProductListSerializer(instance, context=self.context).data


# ---------------------------------------------------------------------------
# Dropdown
# ---------------------------------------------------------------------------

class ProductDropdownSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for populating the product select in the sale create form.
    Includes selling_price so the form can pre-fill unit_price.
    """
    class Meta:
        model  = Product
        fields = ["id", "product_name", "sku", "selling_price", "stock_quantity", "is_active"]
        read_only_fields = fields
