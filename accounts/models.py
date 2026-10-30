import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

phone_validator = RegexValidator(
    r"^\+?[0-9\s\-()]{7,20}$", "Enter a valid phone number, e.g. +63 917 123 4567."
)


class CustomUserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        return super().normalize_email(email).strip().lower()

    def get_by_natural_key(self, email):
        return self.get(email__iexact=self.normalize_email(email))

    async def aget_by_natural_key(self, email):
        return await self.aget(email__iexact=self.normalize_email(email))

    def create_user(self, email, password=None, **extra_fields):
        if not email or not email.strip():
            raise ValueError("An email address is required.")
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Customer or admin. Admins are users with is_staff=True."""

    username = None
    email = models.EmailField("email address", unique=True)
    phone_number = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    school = models.CharField("school / university", max_length=150, blank=True)
    legal_accepted_at = models.DateTimeField(null=True, blank=True, editable=False)
    privacy_policy_version = models.CharField(max_length=32, blank=True, editable=False)
    license_agreement_version = models.CharField(max_length=32, blank=True, editable=False)
    # Set when the customer finishes or skips the first-login "how buying works" tutorial.
    onboarding_completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    email_verification_required = models.BooleanField(default=False, editable=False)
    email_verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    email_verification_nonce = models.UUIDField(default=uuid.uuid4, editable=False)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_user_email_ci"),
        ]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_admin(self):
        return self.is_staff

    @property
    def role_label(self):
        return "Admin" if self.is_staff else "Customer"

    @property
    def display_name(self):
        return self.get_full_name() or self.email


class AuthEmailRateLimit(models.Model):
    """Shared, atomic limits across web workers; identifiers are keyed hashes."""

    key = models.CharField(max_length=64, primary_key=True)
    started_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)


class AuthEmailJob(models.Model):
    class Purpose(models.TextChoices):
        VERIFY = "verify", "Email verification"
        RESET = "reset", "Password reset"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_email_jobs")
    purpose = models.CharField(max_length=12, choices=Purpose.choices)
    recipient = models.EmailField()
    credential_fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    available_at = models.DateTimeField()
    attempted_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "available_at"], name="auth_email_pending_idx")]
