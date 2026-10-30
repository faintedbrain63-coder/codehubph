import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product

REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid typos in payment notes


def generate_reference(prefix, length=8):
    return f"{prefix}-" + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(length))


def generate_order_number():
    return generate_reference("FB")


class Order(models.Model):
    """A purchase of one or more digital products. Implements the payable interface used by payments."""

    payable_kind = "order"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AWAITING_VERIFICATION = "awaiting_verification", "Awaiting Verification"
        PAID = "paid", "Paid"
        REJECTED = "rejected", "Rejected"
        REFUNDED = "refunded", "Refunded"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=20, unique=True, default=generate_order_number, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default=settings.CURRENCY)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return self.number

    # ----- payable interface -------------------------------------------------
    @property
    def reference(self):
        return self.number

    @property
    def customer(self):
        return self.user

    @property
    def amount_due(self):
        return self.total

    @property
    def payable_label(self):
        names = [item.product_name for item in self.items.all()]
        return ", ".join(names)[:120] or f"Order {self.number}"

    @property
    def can_be_paid(self):
        return settings.PRODUCT_SALES_ENABLED and self.status in (self.Status.PENDING, self.Status.REJECTED) and self.total > 0

    @property
    def can_be_cancelled(self):
        """Unpaid orders can be cancelled; a payment under review must be resolved first."""
        return self.status in (self.Status.PENDING, self.Status.REJECTED)

    def already_owned_items(self):
        """Items the customer has since bought in another paid order (paying again would charge twice)."""
        owned = set(
            OrderItem.objects.filter(order__user_id=self.user_id, order__status=self.Status.PAID)
            .exclude(order_id=self.pk)
            .values_list("product_id", flat=True)
        )
        return [item for item in self.items.all() if item.product_id in owned]

    @property
    def payment_block_reason(self):
        """None when payment may proceed, otherwise a customer-facing explanation."""
        owned = self.already_owned_items()
        if owned:
            names = ", ".join(item.product_name for item in owned)
            return (
                f"You already own {names} from another order. Cancel this order and check out the remaining "
                "items again so you are not charged twice."
            )
        return None

    def get_absolute_url(self):
        return reverse("orders:detail", kwargs={"number": self.number})

    def get_payment_url(self):
        return reverse("payments:checkout", kwargs={"kind": self.payable_kind, "reference": self.number})

    def on_payment_submitted(self, payment):
        self.status = self.Status.AWAITING_VERIFICATION
        self.save(update_fields=["status", "updated_at"])

    def mark_paid(self, payment):
        """Idempotent: calling it twice never grants access twice or changes paid_at."""
        if self.status == self.Status.PAID:
            return False
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at", "updated_at"])
        self.grant_download_access()
        return True

    def on_payment_rejected(self, payment):
        if self.status == self.Status.AWAITING_VERIFICATION:
            self.status = self.Status.REJECTED
            self.save(update_fields=["status", "updated_at"])

    def on_payment_refunded(self, payment):
        self.status = self.Status.REFUNDED
        self.refunded_at = timezone.now()
        self.save(update_fields=["status", "refunded_at", "updated_at"])

    def cancel(self):
        """Cancel an unpaid order (caller holds the row lock). Raises ValueError when not allowed."""
        from payments.models import Payment

        if not self.can_be_cancelled:
            raise ValueError(f"Order {self.number} is {self.get_status_display().lower()} and cannot be cancelled.")
        attempts = Payment.objects.filter(order=self)
        if attempts.filter(status=Payment.Status.AWAITING_VERIFICATION).exists():
            raise ValueError("A payment for this order is being verified. Contact us if you want to cancel it.")
        attempts.filter(status=Payment.Status.PENDING).update(
            status=Payment.Status.FAILED, admin_notes="Order cancelled by the customer before payment.",
            updated_at=timezone.now(),
        )
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "cancelled_at", "updated_at"])

    # ----- helpers ---------------------------------------------------------
    def recalculate_total(self):
        self.total = sum((item.unit_price for item in self.items.all()), Decimal("0.00"))
        self.save(update_fields=["total", "updated_at"])

    def grant_download_access(self):
        expires = None
        if settings.DOWNLOAD_EXPIRY_DAYS:
            expires = timezone.now() + timedelta(days=settings.DOWNLOAD_EXPIRY_DAYS)
        self.items.update(download_count=0, download_limit=settings.DOWNLOAD_LIMIT, access_expires_at=expires)

    @property
    def is_paid(self):
        return self.status == self.Status.PAID


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    # Snapshot at purchase time so later product edits don't change past receipts.
    product_name = models.CharField(max_length=150)
    product_version = models.CharField(max_length=30, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    download_count = models.PositiveIntegerField(default=0)
    download_limit = models.PositiveIntegerField(default=0, help_text="0 means unlimited.")
    access_expires_at = models.DateTimeField(null=True, blank=True)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["order", "product"], name="unique_product_per_order")]

    def __str__(self):
        return f"{self.product_name} ({self.order.number})"

    @property
    def downloads_left(self):
        if not self.download_limit:
            return None
        return max(self.download_limit - self.download_count, 0)

    @property
    def download_block_reason(self):
        """None when the item can be downloaded, otherwise a customer-friendly reason."""
        if self.order.status != Order.Status.PAID:
            return "Downloads unlock once your payment is confirmed."
        if self.access_expires_at and timezone.now() > self.access_expires_at:
            return "Your download link has expired. Contact us and we will renew it."
        if self.download_limit and self.download_count >= self.download_limit:
            return "You have reached the download limit. Contact us and we will reset it."
        if not self.product.file:
            return "The file is being updated. Please try again later."
        return None

    @property
    def can_download(self):
        return self.download_block_reason is None
