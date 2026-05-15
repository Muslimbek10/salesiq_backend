"""
Accounts Models
===============
CustomUser replaces Django's built-in User model.

Design decisions:
  - AbstractBaseUser gives us full control over fields and auth.
  - PermissionsMixin adds groups/user_permissions for Django Admin.
  - Role is stored as a CharField with TextChoices — readable in the DB,
    easy to query, and self-documenting in migrations.
  - Custom QuerySet methods let callers write clean, expressive queries
    (e.g., CustomUser.objects.active().managers()).
  - clean() enforces business rules at the model level so they apply
    regardless of which interface creates or updates a user.
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------

class CustomUserQuerySet(models.QuerySet):
    """Chainable query helpers for CustomUser."""

    def active(self):
        """Return only users that can log in."""
        return self.filter(is_active=True)

    def admins(self):
        return self.filter(role=CustomUser.Role.ADMIN)

    def managers(self):
        return self.filter(role=CustomUser.Role.MANAGER)

    def analysts(self):
        return self.filter(role=CustomUser.Role.ANALYST)

    def with_role(self, role):
        return self.filter(role=role)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class CustomUserManager(BaseUserManager):
    """
    Manager for CustomUser.
    All user creation flows go through create_user() to ensure
    password hashing and field defaults are always applied.
    """

    def get_queryset(self):
        return CustomUserQuerySet(self.model, using=self._db)

    # --- QuerySet proxies ---
    def active(self):
        return self.get_queryset().active()

    def admins(self):
        return self.get_queryset().admins()

    def managers(self):
        return self.get_queryset().managers()

    def analysts(self):
        return self.get_queryset().analysts()

    # --- Creation ---
    def create_user(self, username, email, password=None, **extra_fields):
        """Create and persist a regular user."""
        if not username:
            raise ValueError("A username is required.")
        if not email:
            raise ValueError("An email address is required.")

        email = self.normalize_email(email)
        extra_fields.setdefault("role", CustomUser.Role.ANALYST)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.full_clean()           # Run model-level validation on every creation
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        """Create and persist a superuser (admin + is_staff + is_superuser)."""
        extra_fields.setdefault("role", CustomUser.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, email, password, **extra_fields)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Platform user with role-based access control.

    Role hierarchy (highest → lowest privilege):
        admin    → Full access including user management.
        manager  → CRUD on all business entities. No user management.
        analyst  → Read-only on business data. Full access to intelligence modules.

    Authentication uses username + password.
    Email is stored for contact / notification purposes.
    """

    class Role(models.TextChoices):
        ADMIN   = "admin",   "Administrator"
        MANAGER = "manager", "Manager"
        ANALYST = "analyst", "Analyst"

    # ------------------------------------------------------------------
    # Core identification
    # ------------------------------------------------------------------
    username = models.CharField(
        max_length=150,
        unique=True,
        help_text="Required. 150 characters or fewer. Letters, digits, and @/./+/-/_ only.",
    )
    email = models.EmailField(
        max_length=255,
        unique=True,
        help_text="Used for notifications. Must be unique across the system.",
    )

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------
    first_name = models.CharField(max_length=100, blank=True, default="")
    last_name  = models.CharField(max_length=100, blank=True, default="")
    avatar_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="Optional link to user avatar image.",
    )

    # ------------------------------------------------------------------
    # Role-based access
    # ------------------------------------------------------------------
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.ANALYST,
        db_index=True,
        help_text="Controls which modules and actions this user can access.",
    )

    # ------------------------------------------------------------------
    # Account status
    # ------------------------------------------------------------------
    is_active = models.BooleanField(
        default=True,
        help_text="Deactivated users cannot log in. Preferred over deletion.",
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Grants access to the Django Admin panel.",
    )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    date_joined = models.DateTimeField(default=timezone.now, editable=False)
    updated_at  = models.DateTimeField(auto_now=True)
    last_login  = models.DateTimeField(null=True, blank=True)   # Updated by Django auth

    objects = CustomUserManager()

    USERNAME_FIELD  = "username"
    REQUIRED_FIELDS = ["email"]           # Prompted by createsuperuser

    class Meta:
        db_table         = "users"
        verbose_name     = "User"
        verbose_name_plural = "Users"
        ordering         = ["username"]
        indexes = [
            models.Index(fields=["role", "is_active"], name="idx_users_role_active"),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def clean(self):
        super().clean()
        self.email    = self.__class__.objects.normalize_email(self.email)
        self.username = self.username.strip()
        if not self.username:
            raise ValidationError({"username": "Username cannot be blank."})

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    def __repr__(self):
        return f"<CustomUser id={self.pk} username={self.username!r} role={self.role!r}>"

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def full_name(self):
        """Full name from first + last, falls back to username."""
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.username

    @property
    def display_name(self):
        """Human-friendly label for UI display."""
        return f"{self.full_name} ({self.get_role_display()})"

    # ------------------------------------------------------------------
    # Role-check helpers (used in permission classes and templates)
    # ------------------------------------------------------------------
    def has_admin_role(self):
        return self.role == self.Role.ADMIN

    def has_manager_role(self):
        """True for admin and manager (admin is a superset of manager)."""
        return self.role in (self.Role.ADMIN, self.Role.MANAGER)

    def has_analyst_role(self):
        """True for all authenticated roles (all can access analytics)."""
        return self.role in (self.Role.ADMIN, self.Role.MANAGER, self.Role.ANALYST)
