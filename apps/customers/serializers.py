"""
Customers Serializers
=====================

CustomerListSerializer
  Optimised for the customer table. Includes purchase stats
  when the queryset has been annotated (avoids N+1).

CustomerDetailSerializer
  Full read representation for the single-customer retrieve endpoint.
  Includes purchase history summary and dormancy status.

CustomerCreateUpdateSerializer
  Write serializer for create and update.

CustomerDropdownSerializer
  Minimal id + full_name for populating the customer select in the sale form.
"""
from rest_framework import serializers

from .models import Customer


# ---------------------------------------------------------------------------
# Read serializers
# ---------------------------------------------------------------------------

class CustomerListSerializer(serializers.ModelSerializer):
    """
    Optimised list view serializer.
    Computed fields (purchase stats) are read from annotations if available,
    or from model properties as a fallback.
    """
    customer_type_display = serializers.SerializerMethodField()
    is_high_value         = serializers.BooleanField(read_only=True)
    total_purchases       = serializers.SerializerMethodField()
    total_spent           = serializers.SerializerMethodField()
    last_purchase_date    = serializers.SerializerMethodField()
    is_dormant            = serializers.SerializerMethodField()

    class Meta:
        model  = Customer
        fields = [
            "id",
            "full_name",
            "phone",
            "email",
            "region",
            "customer_type",
            "customer_type_display",
            "is_high_value",
            "total_purchases",
            "total_spent",
            "last_purchase_date",
            "is_dormant",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_customer_type_display(self, obj):
        return obj.get_customer_type_display()

    def get_total_purchases(self, obj):
        # Use annotation if available (set by the view's annotated queryset)
        if hasattr(obj, "total_purchases_ann"):
            return obj.total_purchases_ann
        return obj.purchase_count

    def get_total_spent(self, obj):
        if hasattr(obj, "total_spent_ann"):
            return float(obj.total_spent_ann) if obj.total_spent_ann else 0.0
        return 0.0

    def get_last_purchase_date(self, obj):
        if hasattr(obj, "last_purchase_ann"):
            return obj.last_purchase_ann
        return obj.last_purchase_date

    def get_is_dormant(self, obj):
        return obj.is_dormant


class CustomerDetailSerializer(serializers.ModelSerializer):
    """Full customer detail including all computed fields."""
    customer_type_display = serializers.SerializerMethodField()
    is_high_value         = serializers.BooleanField(read_only=True)
    purchase_count        = serializers.IntegerField(read_only=True)
    last_purchase_date    = serializers.SerializerMethodField()
    days_since_last_purchase = serializers.IntegerField(read_only=True, allow_null=True)
    is_dormant            = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Customer
        fields = [
            "id",
            "full_name",
            "phone",
            "email",
            "region",
            "customer_type",
            "customer_type_display",
            "is_high_value",
            "purchase_count",
            "last_purchase_date",
            "days_since_last_purchase",
            "is_dormant",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_customer_type_display(self, obj):
        return obj.get_customer_type_display()

    def get_last_purchase_date(self, obj):
        return obj.last_purchase_date


# ---------------------------------------------------------------------------
# Write serializer
# ---------------------------------------------------------------------------

class CustomerCreateUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for create and update."""

    class Meta:
        model  = Customer
        fields = [
            "full_name",
            "phone",
            "email",
            "region",
            "customer_type",
        ]
        extra_kwargs = {
            "phone":         {"required": False, "default": ""},
            "email":         {"required": False, "default": ""},
            "region":        {"required": False, "default": ""},
            "customer_type": {"required": False, "default": Customer.CustomerType.RETAIL},
        }

    def validate_full_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Customer name cannot be blank.")
        return value.strip()

    def validate_customer_type(self, value):
        valid_types = [c.value for c in Customer.CustomerType]
        if value not in valid_types:
            raise serializers.ValidationError(
                f"Invalid customer type. Choose from: {', '.join(valid_types)}"
            )
        return value

    def create(self, validated_data):
        customer = Customer(**validated_data)
        customer.full_clean()
        customer.save()
        return customer

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        return instance

    def to_representation(self, instance):
        return CustomerListSerializer(instance, context=self.context).data


# ---------------------------------------------------------------------------
# Dropdown
# ---------------------------------------------------------------------------

class CustomerDropdownSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for the customer select in the sale form.
    Includes customer_type so the form can show type badges.
    """
    class Meta:
        model  = Customer
        fields = ["id", "full_name", "customer_type", "region"]
        read_only_fields = fields
