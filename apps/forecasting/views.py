"""
Forecasting Views
=================

ForecastRunView          POST /api/forecast/run/
  Validates the request, delegates to the forecasting service,
  returns the saved Forecast with full forecast_data.
  Requires Admin or Manager role (forecasting affects business decisions).

ForecastHistoryListView  GET /api/forecast/history/
  Paginated list of all past forecasts, newest first.
  Supports ?target_type=, ?target_id=, ?model_name= filtering.

ForecastDetailView       GET /api/forecast/history/{id}/
  Full forecast detail including forecast_data for chart rendering.
  Any authenticated user can read forecasts.
"""
import logging

from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdminOrManager

from .engine.service import run_forecast
from .models import Forecast
from .serializers import (
    ForecastListSerializer,
    ForecastRequestSerializer,
    ForecastResponseSerializer,
)

logger = logging.getLogger(__name__)


class ForecastRunView(APIView):
    """
    POST /api/forecast/run/

    Request body (JSON):
      {
        "target_type":             "overall" | "product" | "category" | "branch",
        "target_id":               null | <int>,
        "model_name":              "moving_average" | "linear_regression",
        "forecast_period_months":  1 | 3 | 6,
        "months_back":             24,      ← optional, default 24
        "window":                  3        ← optional, Moving Average only
      }

    Response (201 Created):  ForecastResponseSerializer data
    Response (422):          {error: true, message: "Insufficient data …"}
    """
    permission_classes = [IsAdminOrManager]

    def post(self, request):
        req_serializer = ForecastRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        params = req_serializer.validated_data

        try:
            forecast = run_forecast(
                target_type            = params["target_type"],
                target_id              = params.get("target_id"),
                model_name             = params["model_name"],
                forecast_period_months = int(params["forecast_period_months"]),
                months_back            = params.get("months_back", 24),
                window                 = params.get("window", 3),
            )
        except ValueError as exc:
            return Response(
                {"error": True, "message": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        logger.info(
            "Forecast run by user='%s': id=%s type=%s model=%s",
            request.user.username, forecast.pk,
            forecast.forecast_target_type, forecast.model_name,
        )
        return Response(
            ForecastResponseSerializer(forecast).data,
            status=status.HTTP_201_CREATED,
        )


class ForecastHistoryListView(ListAPIView):
    """
    GET /api/forecast/history/

    Optional query params:
      ?target_type=product
      ?target_id=5
      ?model_name=linear_regression
    """
    serializer_class   = ForecastListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Forecast.objects.order_by("-created_at")

        target_type = self.request.query_params.get("target_type")
        target_id   = self.request.query_params.get("target_id")
        model_name  = self.request.query_params.get("model_name")

        if target_type:
            qs = qs.filter(forecast_target_type=target_type)
        if target_id:
            qs = qs.filter(target_id=target_id)
        if model_name:
            qs = qs.filter(model_name=model_name)

        return qs


class ForecastDetailView(RetrieveAPIView):
    """
    GET /api/forecast/history/{id}/
    Returns full forecast_data suitable for rendering the forecast chart.
    """
    serializer_class   = ForecastResponseSerializer
    permission_classes = [IsAuthenticated]
    queryset           = Forecast.objects.all()
