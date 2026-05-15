"""
Accounts Serializers
====================

LoginSerializer
  Validates username + password credentials.
  Returns a structured response with both JWT tokens and the full user profile
  so the frontend can populate AuthContext in a single request.

UserProfileSerializer
  Read-only representation of the currently authenticated user.
  Exposes safe fields only — password is never included.

UserProfileUpdateSerializer
  Allows users to update their own first_name, last_name, email, avatar_url.
  username and role are intentionally excluded from update (admin-only changes).

ChangePasswordSerializer
  Validates current password before accepting a new one.
  Ensures the new password meets Django's AUTH_PASSWORD_VALIDATORS rules.
"""
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import CustomUser


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginSerializer(serializers.Serializer):
    """
    Accepts username + password.
    Authenticates the user and attaches the user object to validated_data
    so the view can generate tokens without repeating the auth check.
    """
    username = serializers.CharField(
        max_length=150,
        help_text="Your account username.",
    )
    password = serializers.CharField(
        write_only=True,                    # Never echoed back in the response
        style={"input_type": "password"},
        help_text="Your account password.",
    )

    def validate(self, data):
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            raise serializers.ValidationError(
                "Both username and password are required."
            )

        # Django's authenticate checks the password against the hash
        user = authenticate(
            request=self.context.get("request"),
            username=username,
            password=password,
        )

        if user is None:
            raise serializers.ValidationError(
                "Invalid username or password. Please try again."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "This account has been deactivated. Contact an administrator."
            )

        # Attach the authenticated user so the view can access it cleanly
        data["user"] = user
        return data


# ---------------------------------------------------------------------------
# User profile (read)
# ---------------------------------------------------------------------------

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Safe read-only representation of a system user.
    Used in: login response, GET /api/auth/profile/, and admin user list.
    """
    full_name    = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()

    class Meta:
        model  = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "role_display",
            "avatar_url",
            "is_active",
            "date_joined",
            "last_login",
        ]
        read_only_fields = fields   # This serializer is always read-only

    def get_full_name(self, obj):
        return obj.full_name

    def get_role_display(self, obj):
        return obj.get_role_display()


# ---------------------------------------------------------------------------
# User profile (update)
# ---------------------------------------------------------------------------

class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Allows authenticated users to update their own profile.
    Role, username, is_active, and is_staff are intentionally excluded.
    Those fields require Admin-level access managed through the Admin panel.
    """
    class Meta:
        model  = CustomUser
        fields = [
            "first_name",
            "last_name",
            "email",
            "avatar_url",
        ]
        extra_kwargs = {
            "email": {
                "required": False,
                "help_text": "Must be unique across all users.",
            },
        }

    def validate_email(self, value):
        user = self.instance
        if (
            CustomUser.objects
            .filter(email=value)
            .exclude(pk=user.pk)
            .exists()
        ):
            raise serializers.ValidationError(
                "This email address is already in use by another account."
            )
        return value


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

class ChangePasswordSerializer(serializers.Serializer):
    """
    Validates current password before applying a new one.
    Runs Django's full password validators on the new password.
    """
    current_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        help_text="Your current password.",
    )
    new_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        min_length=8,
        help_text="New password. Minimum 8 characters.",
    )
    confirm_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        help_text="Repeat the new password to confirm.",
    )

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "New passwords do not match."}
            )

        # Run Django's AUTH_PASSWORD_VALIDATORS on the new password
        user = self.context["request"].user
        try:
            validate_password(data["new_password"], user=user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"new_password": list(e.messages)})

        return data

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


# ---------------------------------------------------------------------------
# Minimal user reference (used in nested serializers)
# ---------------------------------------------------------------------------

class UserMinimalSerializer(serializers.ModelSerializer):
    """
    Lightweight user representation for embedding in other serializers
    (e.g., created_by fields in audit trails, if ever needed).
    """
    class Meta:
        model  = CustomUser
        fields = ["id", "username", "full_name", "role"]
        read_only_fields = fields

    full_name = serializers.SerializerMethodField()

    def get_full_name(self, obj):
        return obj.full_name
