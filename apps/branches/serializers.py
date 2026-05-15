"""
Branches Serializers
====================

BranchListSerializer
  Includes annotated revenue and profit totals for the branch table.
  Reads from queryset annotations to avoid per-row aggregation queries.

BranchDetailSerializer
  Full read representation with all computed financial totals.

BranchCreateUpdateSerializer
  Write serializer. Validates branch_name uniqueness and normalises casing.

BranchDropdownSerializer
  Minimal id + branch_name for the sale form and filter dropdowns.
"""
from rest_framework import serializers

from .models import Branch


# ---------------------------------------------------------------------------
# Read serializers
# ---------------------------------------------------------------------------

class BranchListSerializer(serializers.ModelSerializer):
    """
    Optimised list view. Revenue and profit come from queryset annotations
    injected by the ViewSet, avoiding N+1 on every row.
    """
    total_revenue      = serializers.SerializerMethodField()
    total_profit       = serializers.SerializerMethodField()
    total_transactions = serializers.SerializerMethodField()

    class Meta:
        model  = Branch
        fields = [
            "id",
            "branch_name",
            "location",
            "manager_name",
            "is_active",
            "total_revenue",
            "total_profit",
            "total_transactions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_total_revenue(self, obj):
        # Prefer queryset annotation; fall back to model property
        if hasattr(obj, "ann_revenue"):
            return float(obj.ann_revenue) if obj.ann_revenue else 0.0
        return float(obj.total_revenue)

    def get_total_profit(self, obj):
        if hasattr(obj, "ann_profit"):
            return float(obj.ann_profit) if obj.ann_profit else 0.0
        return float(obj.total_profit)

    def get_total_transactions(self, obj):
        if hasattr(obj, "ann_transactions"):
            return obj.ann_transactions or 0
        return obj.total_sales_count


class BranchDetailSerializer(serializers.ModelSerializer):
    """Full branch detail view."""
    total_revenue      = serializers.SerializerMethodField()
    total_profit       = serializers.SerializerMethodField()
    total_sales_count  = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Branch
        fields = [
            "id",
            "branch_name",
            "location",
            "manager_name",
            "is_active",
            "total_revenue",
            "total_profit",
            "total_sales_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_total_revenue(self, obj):
        return float(obj.total_revenue)

    def get_total_profit(self, obj):
        return float(obj.total_profit)


# ---------------------------------------------------------------------------
# Write serializer
# ---------------------------------------------------------------------------

class BranchCreateUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for create and update."""

    class Meta:
        model  = Branch
        fields = [
            "branch_name",
            "location",
            "manager_name",
            "is_active",
        ]
        extra_kwargs = {
            "location":     {"required": False, "default": ""},
            "manager_name": {"required": False, "default": ""},
            "is_active":    {"required": False, "default": True},
        }

    def validate_branch_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Branch name cannot be blank.")

        qs = Branch.objects.filter(branch_name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A branch named '{value}' already exists."
            )
        return value

    def create(self, validated_data):
        branch = Branch(**validated_data)
        branch.full_clean()
        branch.save()
        return branch

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        return instance

    def to_representation(self, instance):
        return BranchListSerializer(instance, context=self.context).data


# ---------------------------------------------------------------------------
# Dropdown
# ---------------------------------------------------------------------------

class BranchDropdownSerializer(serializers.ModelSerializer):
    """Minimal serializer for sale form and filter dropdowns."""
    class Meta:
        model  = Branch
        fields = ["id", "branch_name", "location", "is_active"]
        read_only_fields = fields
