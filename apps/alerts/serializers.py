"""
Alerts Serializers
==================

AlertSerializer
  Full read serializer. Adds computed properties (priority_color, type_icon,
  is_critical) so the frontend doesn't need its own mapping tables.
"""
from rest_framework import serializers

from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    """Read serializer for Alert records."""
    priority_color = serializers.CharField(read_only=True)
    type_icon      = serializers.CharField(read_only=True)
    is_critical    = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Alert
        fields = [
            "id",
            "alert_type",
            "alert_message",
            "priority_level",
            "priority_color",
            "type_icon",
            "is_critical",
            "related_entity_type",
            "related_entity_id",
            "related_entity_name",
            "is_active",
            "created_at",
            "dismissed_at",
        ]
        read_only_fields = fields
