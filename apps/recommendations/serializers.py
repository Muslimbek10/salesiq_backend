"""
Recommendations Serializers
============================

RecommendationSerializer
  Full read serializer. Adds computed properties (priority_color, type_icon,
  is_high_priority) so the frontend doesn't need its own mapping logic.

RecommendationGenerateResponseSerializer
  Minimal write response — just the engine summary after a generate run.
"""
from rest_framework import serializers

from .models import Recommendation


class RecommendationSerializer(serializers.ModelSerializer):
    """
    Read serializer for Recommendation records.
    All computed properties from the model are included.
    """
    priority_color  = serializers.CharField(read_only=True)
    type_icon       = serializers.CharField(read_only=True)
    is_high_priority = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Recommendation
        fields = [
            "id",
            "recommendation_type",
            "recommendation_text",
            "related_entity_type",
            "related_entity_id",
            "related_entity_name",
            "priority_level",
            "priority_color",
            "type_icon",
            "is_high_priority",
            "is_active",
            "generated_at",
            "dismissed_at",
        ]
        read_only_fields = fields
