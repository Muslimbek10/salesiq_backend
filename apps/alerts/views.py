"""
Alerts Views
============

AlertListView         GET  /api/alerts/
  Paginated, filterable list of alerts.
  Filters: ?is_active=true, ?priority_level=High, ?alert_type=low_stock, ?entity_type=product

GenerateAlertsView    POST /api/alerts/generate/
  Triggers the alert generator to run all generators.
  Returns a summary of how many alerts were created per generator.
  Requires Admin or Manager role.

AlertDismissView      POST /api/alerts/{id}/dismiss/
  Dismisses a single alert (sets is_active=False).

AlertCountView        GET  /api/alerts/counts/
  Returns unread alert counts by priority — used by the navbar badge.
  No pagination. Fast single-query response.
"""
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdminOrManager

from .engine.alert_generator import run_all_alert_generators
from .models import Alert
from .serializers import AlertSerializer

logger = logging.getLogger(__name__)


class AlertListView(ListAPIView):
    """
    GET /api/alerts/

    Query params:
      ?is_active=true|false
      ?priority_level=High|Medium|Low
      ?alert_type=low_stock|declining_sales|...
      ?entity_type=product|branch|category|overall
    """
    serializer_class   = AlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Alert.objects.priority_ordered()

        is_active   = self.request.query_params.get("is_active")
        priority    = self.request.query_params.get("priority_level")
        alert_type  = self.request.query_params.get("alert_type")
        entity_type = self.request.query_params.get("entity_type")

        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        if priority:
            qs = qs.filter(priority_level=priority)
        if alert_type:
            qs = qs.filter(alert_type=alert_type)
        if entity_type:
            qs = qs.filter(related_entity_type=entity_type)

        return qs


class GenerateAlertsView(APIView):
    """
    POST /api/alerts/generate/
    Triggers all alert generators. Accepts optional JSON body to override thresholds.

    Request body (all optional):
      {
        "sales_lookback_months":     2,
        "declining_sales_threshold": 25.0,
        "branch_lookback_months":    3,
        "branch_threshold_pct":      70.0,
        "sales_drop_days":           14,
        "sales_drop_threshold":      20.0,
        "forecast_risk_threshold":   15.0,
        "high_demand_threshold":     40.0
      }
    """
    permission_classes = [IsAdminOrManager]

    def post(self, request):
        config_keys = {
            "sales_lookback_months", "declining_sales_threshold",
            "branch_lookback_months", "branch_threshold_pct",
            "sales_drop_days", "sales_drop_threshold",
            "forecast_risk_threshold", "high_demand_threshold",
        }
        config = {k: v for k, v in request.data.items() if k in config_keys}

        summary = run_all_alert_generators(**config)
        logger.info(
            "Alert generator triggered by user='%s': %d new alert(s).",
            request.user.username, summary["total_created"],
        )
        return Response(summary, status=status.HTTP_200_OK)


class AlertDismissView(APIView):
    """
    POST /api/alerts/{id}/dismiss/
    Marks the alert as dismissed. Idempotent.
    """
    permission_classes = [IsAdminOrManager]

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk)
        alert.dismiss()
        logger.info(
            "Alert id=%s dismissed by user='%s'.", pk, request.user.username,
        )
        return Response(AlertSerializer(alert).data)


class AlertCountView(APIView):
    """
    GET /api/alerts/counts/
    Returns active alert counts by priority for the navbar badge.
    Single-query response, no pagination.

    Response:
      {
        "total":  int,
        "high":   int,
        "medium": int,
        "low":    int
      }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count, Q
        active_qs = Alert.objects.filter(is_active=True)
        counts = active_qs.aggregate(
            total=Count("id"),
            high=Count("id",   filter=Q(priority_level=Alert.Priority.HIGH)),
            medium=Count("id", filter=Q(priority_level=Alert.Priority.MEDIUM)),
            low=Count("id",    filter=Q(priority_level=Alert.Priority.LOW)),
        )
        return Response({
            "total":  counts["total"]  or 0,
            "high":   counts["high"]   or 0,
            "medium": counts["medium"] or 0,
            "low":    counts["low"]    or 0,
        })
