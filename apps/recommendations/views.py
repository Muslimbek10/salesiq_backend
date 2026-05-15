"""
Recommendations Views
=====================

RecommendationListView    GET  /api/recommendations/
  Paginated list of recommendations.
  Filters: ?is_active=true, ?priority_level=High, ?recommendation_type=restock
  Default ordering: priority_ordered() (High → Medium → Low, then newest first).

GenerateRecommendationsView  POST /api/recommendations/generate/
  Triggers the rule engine to run all recommendation rules.
  Returns a summary of how many recommendations were created per rule.
  Requires Admin or Manager role.

RecommendationDismissView  POST /api/recommendations/{id}/dismiss/
  Dismisses a single recommendation (sets is_active=False).
  Requires Admin or Manager role.

RecommendationReactivateView  POST /api/recommendations/{id}/reactivate/
  Re-activates a previously dismissed recommendation.
  Requires Admin or Manager role.
"""
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdminOrManager

from .engine.runner import run_all_rules
from .models import Recommendation
from .serializers import RecommendationSerializer

logger = logging.getLogger(__name__)


class RecommendationListView(ListAPIView):
    """
    GET /api/recommendations/

    Query params:
      ?is_active=true|false
      ?priority_level=High|Medium|Low
      ?recommendation_type=restock|declining_sales|...
      ?entity_type=product|branch|category|customer|overall
      ?entity_id=<int>
    """
    serializer_class   = RecommendationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Recommendation.objects.priority_ordered()

        is_active  = self.request.query_params.get("is_active")
        priority   = self.request.query_params.get("priority_level")
        rec_type   = self.request.query_params.get("recommendation_type")
        entity_type = self.request.query_params.get("entity_type")
        entity_id  = self.request.query_params.get("entity_id")

        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        if priority:
            qs = qs.filter(priority_level=priority)
        if rec_type:
            qs = qs.filter(recommendation_type=rec_type)
        if entity_type:
            qs = qs.filter(related_entity_type=entity_type)
        if entity_id:
            qs = qs.filter(related_entity_id=entity_id)

        return qs


class GenerateRecommendationsView(APIView):
    """
    POST /api/recommendations/generate/
    Triggers a full rule engine run. Accepts optional JSON body to override
    default thresholds (all keys optional).

    Request body (all optional):
      {
        "sales_lookback_months":       2,
        "declining_threshold_pct":     20.0,
        "growth_threshold_pct":        30.0,
        "forecast_risk_threshold_pct": 15.0,
        "branch_lookback_months":      3,
        "branch_peer_threshold_pct":   70.0,
        "branch_decline_threshold_pct": 20.0,
        "category_lookback_months":    3,
        "low_margin_threshold_pct":    10.0,
        "high_margin_threshold_pct":   35.0,
        "vip_inactive_days":           30,
        "regular_min_purchases":       4,
        "regular_inactive_days":       60
      }

    Response:
      {
        "rule_results":  { rule_name: count, ... },
        "total_created": int
      }
    """
    permission_classes = [IsAdminOrManager]

    def post(self, request):
        # Allow caller to override thresholds; ignore unknown keys
        config_keys = {
            "sales_lookback_months", "declining_threshold_pct",
            "growth_threshold_pct", "forecast_risk_threshold_pct",
            "branch_lookback_months", "branch_peer_threshold_pct",
            "branch_decline_threshold_pct", "category_lookback_months",
            "low_margin_threshold_pct", "high_margin_threshold_pct",
            "vip_inactive_days", "regular_min_purchases", "regular_inactive_days",
        }
        config = {k: v for k, v in request.data.items() if k in config_keys}

        summary = run_all_rules(**config)
        logger.info(
            "Recommendation engine triggered by user='%s': %d new recommendation(s).",
            request.user.username, summary["total_created"],
        )
        return Response(summary, status=status.HTTP_200_OK)


class RecommendationDismissView(APIView):
    """
    POST /api/recommendations/{id}/dismiss/
    Sets is_active=False and records dismissed_at timestamp.
    Idempotent — dismissing an already-dismissed recommendation is a no-op.
    """
    permission_classes = [IsAdminOrManager]

    def post(self, request, pk):
        rec = get_object_or_404(Recommendation, pk=pk)
        rec.dismiss()
        logger.info(
            "Recommendation id=%s dismissed by user='%s'.",
            pk, request.user.username,
        )
        return Response(RecommendationSerializer(rec).data)


class RecommendationReactivateView(APIView):
    """
    POST /api/recommendations/{id}/reactivate/
    Re-activates a dismissed recommendation.
    """
    permission_classes = [IsAdminOrManager]

    def post(self, request, pk):
        rec = get_object_or_404(Recommendation, pk=pk)
        rec.reactivate()
        return Response(RecommendationSerializer(rec).data)
