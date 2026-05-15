"""
Categories Serializers
======================

CategorySerializer
  Full CRUD serializer. Used for create, retrieve, update, and destroy.
  Includes computed product counts for the list view.

CategoryDropdownSerializer
  Minimal id + name serializer used in product forms and filter dropdowns.
  Returned without pagination so the frontend can populate a <select>.
"""
from rest_framework import serializers

from .models import Category


class CategorySerializer(serializers.ModelSerializer):
    """
    Full category representation for CRUD operations.

    product_count and active_product_count are read-only computed fields
    derived from the related Product queryset. They are only meaningful on
    retrieve/list — on create/update they are ignored.
    """
    product_count        = serializers.SerializerMethodField()
    active_product_count = serializers.SerializerMethodField()

    class Meta:
        model  = Category
        fields = [
            "id",
            "category_name",
            "description",
            "product_count",
            "active_product_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "product_count", "active_product_count", "created_at", "updated_at"]

    def get_product_count(self, obj):
        # Avoids N+1 if the queryset is already annotated
        if hasattr(obj, "annotated_product_count"):
            return obj.annotated_product_count
        return obj.product_count

    def get_active_product_count(self, obj):
        if hasattr(obj, "annotated_active_product_count"):
            return obj.annotated_active_product_count
        return obj.active_product_count

    def validate_category_name(self, value):
        """
        Ensure uniqueness is checked case-insensitively.
        The model's clean() normalises to title-case, but we validate here
        so the error is raised before clean() runs.
        """
        normalised = value.strip().title()
        qs = Category.objects.filter(category_name__iexact=normalised)

        # On update, exclude the current instance from the uniqueness check
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                f"A category named '{normalised}' already exists."
            )
        return value

    def create(self, validated_data):
        category = Category(**validated_data)
        category.full_clean()       # Triggers model-level clean() for normalisation
        category.save()
        return category

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        return instance


class CategoryDropdownSerializer(serializers.ModelSerializer):
    """
    Minimal serializer used for populating select/dropdown fields in the frontend.
    Returned as an unpaginated list from a dedicated endpoint.
    """
    class Meta:
        model  = Category
        fields = ["id", "category_name"]
        read_only_fields = fields
