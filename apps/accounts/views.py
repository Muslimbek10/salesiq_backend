"""
Accounts Views
==============

LoginView
  POST /api/auth/login/
  No authentication required (AllowAny).
  Returns access token, refresh token, and full user profile in one response.

LogoutView
  POST /api/auth/logout/
  Requires authentication.
  Blacklists the provided refresh token so it cannot be used again.

ProfileView
  GET  /api/auth/profile/   → returns current user's profile
  PATCH /api/auth/profile/  → updates current user's own profile fields

ChangePasswordView
  POST /api/auth/change-password/
  Validates current password, applies new password.

TokenRefreshView is used directly from SimpleJWT (no custom wrapper needed).
"""
import logging

from django.contrib.auth import update_session_auth_hash
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginView(APIView):
    """
    POST /api/auth/login/

    Authenticates a user and returns:
      - access_token  : short-lived JWT (60 min) for API requests
      - refresh_token : long-lived JWT (7 days) for obtaining new access tokens
      - user          : full user profile for frontend state initialisation

    No authentication required.
    """
    permission_classes = [AllowAny]
    serializer_class   = LoginSerializer  # For DRF browsable API schema

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        # Generate JWT token pair for this user
        refresh = RefreshToken.for_user(user)
        access  = refresh.access_token

        # Update last_login (Django normally does this in authenticate(),
        # but we do it explicitly here because we use a custom auth flow)
        from django.utils import timezone
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        logger.info("User '%s' (role=%s) logged in.", user.username, user.role)

        return Response(
            {
                "access_token":  str(access),
                "refresh_token": str(refresh),
                "token_type":    "Bearer",
                "expires_in":    int(access.lifetime.total_seconds()),
                "user":          UserProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class LogoutView(APIView):
    """
    POST /api/auth/logout/

    Blacklists the provided refresh_token so it can no longer be used
    to issue new access tokens. The client should also discard the access
    token from local storage on receipt of this response.

    Body: { "refresh_token": "<token>" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh_token")

        if not refresh_token:
            return Response(
                {"error": True, "message": "refresh_token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError as e:
            # Token already blacklisted or invalid — still treat as successful logout
            logger.warning(
                "Logout attempt with invalid/expired token for user '%s': %s",
                request.user.username,
                str(e),
            )

        logger.info("User '%s' logged out.", request.user.username)

        return Response(
            {"message": "Successfully logged out."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Profile — retrieve + update
# ---------------------------------------------------------------------------

class ProfileView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/auth/profile/  → returns the authenticated user's profile
    PATCH /api/auth/profile/  → updates first_name, last_name, email, avatar_url

    Only the currently authenticated user's own profile is accessible here.
    Admin user management is handled through the Django Admin panel.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UserProfileUpdateSerializer
        return UserProfileSerializer

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True        # Always allow partial updates (PATCH behaviour)
        return super().update(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/

    Body: { "current_password": "...", "new_password": "...", "confirm_password": "..." }

    Validates current password, checks new password against validators,
    and applies the change. Invalidates existing sessions (if any).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Keep the current DRF session alive (not strictly needed for JWT,
        # but good practice if Admin panel sessions are also in use)
        update_session_auth_hash(request, request.user)

        logger.info("User '%s' changed their password.", request.user.username)

        return Response(
            {"message": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )
