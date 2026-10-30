from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.storage import get_private_storage
from core.validators import (
    CONCEPT_FILE_VALIDATORS, DOCUMENT_VALIDATORS, IMAGE_VALIDATORS, PRODUCT_FILE_VALIDATORS, UniqueUploadPath,
)
from orders.models import generate_reference


class CapstoneProjectQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=CapstoneProject.Status.PUBLISHED)


class CapstoneProject(models.Model):
    """A custom development service or example project, never an instant-download product."""

    class Field(models.TextChoices):
        WEB = "web", "Web App / System"
        MOBILE = "mobile", "Mobile App"
        DESKTOP = "desktop", "Desktop Application"
        IOT = "iot", "IoT / Embedded"
        DATA_AI = "data_ai", "Data Science / AI"
        GAME = "game", "Game Development"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True, help_text="Leave blank to generate from the title.")
    field = models.CharField("category / field", max_length=20, choices=Field.choices, default=Field.WEB)
    short_description = models.CharField(max_length=220)
    description = models.TextField()
    features = models.TextField(blank=True, help_text="One feature/module per line.")
    tech_stack = models.CharField(max_length=255, blank=True, help_text="Comma-separated.")
    suggested_price = models.DecimalField(
        "starting price", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("1.00"))]
    )
    thumbnail = models.ImageField(
        upload_to=UniqueUploadPath("capstone/thumbnails"), blank=True, validators=IMAGE_VALIDATORS
    )
    source_code = models.FileField(
        upload_to=UniqueUploadPath("capstone/source"),
        storage=get_private_storage,
        validators=PRODUCT_FILE_VALIDATORS,
        blank=True,
        help_text="Optional reference files. Customer-specific builds can be uploaded to each request later.",
    )
    documentation = models.FileField(
        upload_to=UniqueUploadPath("capstone/docs"),
        storage=get_private_storage,
        validators=DOCUMENT_VALIDATORS,
        blank=True,
        help_text="Optional (e.g. Chapters 1–5, user manual).",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CapstoneProjectQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "field"])]
        verbose_name = "project service"
        verbose_name_plural = "project services"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:180] or "capstone"
            slug, n = base, 2
            while CapstoneProject.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("capstone:detail", kwargs={"slug": self.slug})


class CapstoneRequest(models.Model):
    """A custom project brief for a student, public institution or business."""

    payable_kind = "capstone"

    class ClientType(models.TextChoices):
        STUDENT = "student", "Student capstone project"
        LGU = "lgu", "Local government unit"
        MILITARY = "military", "Military organization"
        BUSINESS = "business", "Business"
        OTHER = "other", "Other organization / individual"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        QUOTED = "quoted", "Quoted"
        ACCEPTED = "accepted", "Accepted"
        PAID = "paid", "Paid"
        IN_PROGRESS = "in_progress", "In Progress"
        DELIVERED = "delivered", "Delivered"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    # Allowed status changes. Re-quoting is allowed until the customer pays.
    TRANSITIONS = {
        Status.SUBMITTED: {Status.QUOTED, Status.CANCELLED},
        Status.QUOTED: {Status.QUOTED, Status.ACCEPTED, Status.CANCELLED},
        Status.ACCEPTED: {Status.QUOTED, Status.PAID, Status.CANCELLED},
        Status.PAID: {Status.IN_PROGRESS, Status.DELIVERED},
        Status.IN_PROGRESS: {Status.DELIVERED},
        Status.DELIVERED: {Status.COMPLETED, Status.IN_PROGRESS},
        Status.COMPLETED: set(),
        Status.CANCELLED: set(),
    }
    TIMESTAMP_FIELDS = {
        Status.QUOTED: "quoted_at",
        Status.ACCEPTED: "accepted_at",
        Status.PAID: "paid_at",
        Status.DELIVERED: "delivered_at",
        Status.COMPLETED: "completed_at",
        Status.CANCELLED: "cancelled_at",
    }
    UNLOCKED_STATUSES = {Status.PAID, Status.IN_PROGRESS, Status.DELIVERED, Status.COMPLETED}
    STEPS = [Status.SUBMITTED, Status.QUOTED, Status.ACCEPTED, Status.PAID, Status.IN_PROGRESS, Status.DELIVERED, Status.COMPLETED]

    reference = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="capstone_requests")
    project = models.ForeignKey(CapstoneProject, on_delete=models.PROTECT, related_name="requests", null=True, blank=True)
    request_title = models.CharField("project title", max_length=180, blank=True)
    project_type = models.CharField(max_length=20, choices=CapstoneProject.Field.choices, blank=True)
    client_type = models.CharField("client type", max_length=20, choices=ClientType.choices, default=ClientType.STUDENT)
    school_name = models.CharField("school / organization", max_length=150)
    program = models.CharField("course / program", max_length=150, blank=True,
                               help_text="Required for student capstone projects; optional for other clients.")
    group_members = models.TextField(blank=True, help_text="Optional. One name per line.")
    customization_notes = models.TextField(
        "project requirements",
        help_text="Describe your users, workflow, required features, preferred platform and expected deliverables.",
    )
    concept_file = models.FileField(
        "concept or algorithm file",
        upload_to=UniqueUploadPath("capstone/concepts"),
        storage=get_private_storage,
        validators=CONCEPT_FILE_VALIDATORS,
        blank=True,
        help_text="Optional. Attach your concept paper, algorithm or flowchart as a PDF, Word or PowerPoint file.",
    )
    preferred_deadline = models.DateField(null=True, blank=True)
    agreed_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("1.00"))]
    )
    currency = models.CharField(max_length=3, default=settings.CURRENCY)
    quote_notes = models.TextField(blank=True, help_text="What the quote includes, timeline, terms.")
    cancel_reason = models.TextField(blank=True)
    delivered_source = models.FileField(
        "customised source code",
        upload_to=UniqueUploadPath("capstone/deliveries"),
        storage=get_private_storage,
        validators=PRODUCT_FILE_VALIDATORS,
        blank=True,
        help_text="Upload the source code or software build prepared for this customer.",
    )
    delivered_documentation = models.FileField(
        "customised documentation",
        upload_to=UniqueUploadPath("capstone/deliveries"),
        storage=get_private_storage,
        validators=DOCUMENT_VALIDATORS,
        blank=True,
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.SUBMITTED)
    quoted_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "project request"
        verbose_name_plural = "project requests"
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.reference} — {self.title}"

    @property
    def title(self):
        return self.request_title or (self.project.title if self.project_id else "Custom project")

    @property
    def project_type_label(self):
        return self.get_project_type_display() or (self.project.get_field_display() if self.project_id else "Not specified")

    def save(self, *args, **kwargs):
        if not self.reference:
            ref = generate_reference("CAP", 6)
            while CapstoneRequest.objects.filter(reference=ref).exists():
                ref = generate_reference("CAP", 6)
            self.reference = ref
        super().save(*args, **kwargs)

    # ----- workflow ------------------------------------------------------------
    def can_transition_to(self, new_status):
        if new_status in (self.Status.QUOTED, self.Status.CANCELLED) and self.pk:
            if self.payments.filter(status="awaiting_verification").exists():
                return False
        return new_status in self.TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status):
        """Change status if the workflow allows it; raises ValueError otherwise."""
        if not self.can_transition_to(new_status):
            if new_status in (self.Status.QUOTED, self.Status.CANCELLED) and self.payments.filter(
                status="awaiting_verification"
            ).exists():
                raise ValueError("Resolve the payment under review before changing the quote or cancelling this request.")
            raise ValueError(
                f"Cannot move request from {self.get_status_display()} to {self.Status(new_status).label}."
            )
        if new_status == self.Status.QUOTED and not self.agreed_price:
            raise ValueError("Set a price before sending a quote.")
        if new_status == self.Status.DELIVERED and not self.source_file:
            raise ValueError("Upload the project deliverables before marking this request as delivered.")
        self.status = new_status
        fields = ["status", "updated_at"]
        ts_field = self.TIMESTAMP_FIELDS.get(new_status)
        if ts_field:
            setattr(self, ts_field, timezone.now())
            fields.append(ts_field)
        self.save(update_fields=fields)

    @property
    def is_open(self):
        return self.status not in (self.Status.COMPLETED, self.Status.CANCELLED)

    @property
    def can_cancel(self):
        return self.can_transition_to(self.Status.CANCELLED)

    @property
    def files_unlocked(self):
        return self.status in self.UNLOCKED_STATUSES and bool(self.source_file)

    @property
    def source_file(self):
        return self.delivered_source or (self.project.source_code if self.project_id else None)

    @property
    def documentation_file(self):
        return self.delivered_documentation or (self.project.documentation if self.project_id else None)

    @property
    def concept_file_extension(self):
        return self.concept_file.name.rsplit(".", 1)[-1].lower() if self.concept_file else ""

    @property
    def concept_file_is_pdf(self):
        return self.concept_file_extension == "pdf"

    @property
    def concept_file_label(self):
        labels = {"doc": "Word document", "docx": "Word document", "ppt": "PowerPoint", "pptx": "PowerPoint", "pdf": "PDF document"}
        return labels.get(self.concept_file_extension, "Document")

    @property
    def step_index(self):
        return self.STEPS.index(self.status) if self.status in self.STEPS else -1

    # ----- payable interface -------------------------------------------------
    @property
    def amount_due(self):
        return self.agreed_price or Decimal("0.00")

    @property
    def payable_label(self):
        return f"Project service: {self.title}"[:120]

    @property
    def can_be_paid(self):
        return self.status == self.Status.ACCEPTED and bool(self.agreed_price)

    payment_block_reason = None

    def get_absolute_url(self):
        return reverse("capstone:request_detail", kwargs={"reference": self.reference})

    def get_payment_url(self):
        return reverse("payments:checkout", kwargs={"kind": self.payable_kind, "reference": self.reference})

    def on_payment_submitted(self, payment):
        """Status stays Accepted; the pending Payment record shows 'under review'."""

    def mark_paid(self, payment):
        if self.status in self.UNLOCKED_STATUSES:
            return False
        self.transition_to(self.Status.PAID)
        return True

    def on_payment_rejected(self, payment):
        """Nothing to change: the request stays Accepted so the customer can pay again."""

    def on_payment_refunded(self, payment):
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancel_reason = "Payment refunded."
        self.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])


class CapstoneMessage(models.Model):
    request = models.ForeignKey(CapstoneRequest, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message on {self.request.reference} by {self.sender}"

    @property
    def from_admin(self):
        return self.sender.is_staff
