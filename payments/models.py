import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.storage import get_private_storage
from core.validators import IMAGE_VALIDATORS, UniqueUploadPath


class Payment(models.Model):
    """One payment attempt for an Order or a CapstoneRequest (exactly one of the two)."""

    class Method(models.TextChoices):
        PAYPAL = "paypal", "PayPal"
        GCASH = "gcash", "GCash"
        CARD = "card", "Debit / Credit Card"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AWAITING_VERIFICATION = "awaiting_verification", "Awaiting Verification"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )
    capstone_request = models.ForeignKey(
        "capstone.CapstoneRequest", on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CURRENCY)
    method = models.CharField(max_length=10, choices=Method.choices)
    provider = models.CharField(max_length=30, help_text="Provider module that handled this payment.")
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PENDING)
    provider_reference = models.CharField(
        "reference / transaction ID", max_length=100, blank=True,
        help_text="PayPal transaction or order ID, GCash reference number, or gateway ID.",
    )
    capture_id = models.CharField(max_length=100, blank=True)
    proof_image = models.ImageField(
        upload_to=UniqueUploadPath("payments/proofs"),
        storage=get_private_storage,
        validators=IMAGE_VALIDATORS,
        blank=True,
    )
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    raw_response = models.JSONField(default=dict, blank=True)
    admin_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["provider_reference"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(order__isnull=False, capstone_request__isnull=True)
                    | Q(order__isnull=True, capstone_request__isnull=False)
                ),
                name="payment_has_exactly_one_payable",
            ),
            # The same transaction/reference number cannot be claimed twice.
            models.UniqueConstraint(
                fields=["method", "provider_reference"],
                condition=~Q(provider_reference="") & ~Q(status__in=["rejected", "failed"]),
                name="unique_active_provider_reference",
            ),
            models.UniqueConstraint(
                fields=["capture_id"], condition=~Q(capture_id=""), name="unique_gateway_capture",
            ),
        ]

    def __str__(self):
        return f"{self.get_method_display()} {self.amount} {self.currency} for {self.payable.reference}"

    @property
    def payable(self):
        return self.order if self.order_id else self.capstone_request

    @property
    def is_manual(self):
        return self.provider.endswith("_manual")


class WebhookEvent(models.Model):
    """Every verified webhook is stored once; replays of the same event ID are ignored."""

    provider = models.CharField(max_length=30)
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider} {self.event_type} {self.event_id}"
