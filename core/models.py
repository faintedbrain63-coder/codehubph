import os
import uuid
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.urls import reverse
from django.utils.text import slugify

from core.validators import IMAGE_VALIDATORS, UniqueUploadPath
from core.storage import get_private_storage

SITE_SETTINGS_CACHE_KEY = "core.site_settings"


class SiteSettings(models.Model):
    """Single-row table with settings the owner can edit from /manage/settings/."""

    site_name = models.CharField(max_length=100, blank=True, help_text="Leave blank to use SITE_NAME from .env.")
    tagline = models.CharField(
        max_length=200, default="Custom web apps, mobile apps and software for students, government and businesses."
    )
    contact_email = models.EmailField(default="ragus.christian1989@gmail.com")
    contact_phone = models.CharField(max_length=30, blank=True)
    paypal_me_url = models.URLField(blank=True, help_text="Leave blank to use PAYPAL_ME_URL from .env.")
    gcash_account_name = models.CharField(max_length=100, blank=True)
    gcash_number = models.CharField(max_length=20, blank=True)
    gcash_qr = models.ImageField(
        upload_to=UniqueUploadPath("site/gcash"), blank=True, validators=IMAGE_VALIDATORS
    )
    payment_instructions = models.TextField(
        blank=True,
        default="Payments are verified within 24 hours (usually much faster). "
        "Always include your order reference in the payment notes.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(SITE_SETTINGS_CACHE_KEY)

    def delete(self, *args, **kwargs):
        pass  # the singleton row is never deleted

    @classmethod
    def load(cls):
        # Payment destinations must reflect edits in every worker immediately.
        # The default process-local cache cannot be invalidated across Gunicorn workers.
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def name(self):
        return self.site_name or settings.SITE_NAME

    @property
    def paypal_link(self):
        return (self.paypal_me_url or settings.PAYPAL_ME_URL).rstrip("/")

    @property
    def gcash_ready(self):
        # A QR code alone is enough: customers scan it (or upload it from their gallery) in the GCash app.
        return bool(self.gcash_number or self.gcash_qr)


class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=150)
    message = models.TextField(max_length=3000)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} — {self.email}"


class PortfolioPresentation(models.Model):
    """Owner-editable introduction and optional developer profile for the portfolio."""

    is_visible = models.BooleanField("show portfolio on the landing page", default=True)
    eyebrow = models.CharField(max_length=60, default="Selected work")
    heading = models.CharField(max_length=160, default="Past and ongoing projects")
    introduction = models.TextField(max_length=600, default="Web applications, mobile apps and software developed around each client's requirements.")
    display_name = models.CharField("your name / studio name", max_length=120, blank=True)
    professional_title = models.CharField(max_length=120, default="Full-stack developer", blank=True)
    about = models.TextField("about you", max_length=1600, blank=True)
    skills = models.CharField(max_length=255, blank=True, help_text="Comma-separated skills or areas of expertise.")
    location = models.CharField(max_length=120, blank=True)
    github_url = models.URLField("GitHub / code repository link", max_length=500, blank=True)
    linkedin_url = models.URLField("LinkedIn / professional profile link", max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "portfolio presentation"
        verbose_name_plural = "portfolio presentation"

    def __str__(self):
        return "Portfolio introduction and developer profile"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def has_profile(self):
        return bool(self.display_name or self.about or self.skills or self.location or self.github_url or self.linkedin_url)


class PortfolioProject(models.Model):
    class ProjectType(models.TextChoices):
        WEB = "web", "Web application"
        MOBILE = "mobile", "Mobile application"
        SOFTWARE = "software", "Software / desktop application"

    class Stage(models.TextChoices):
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    project_type = models.CharField(max_length=20, choices=ProjectType.choices, default=ProjectType.WEB)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.COMPLETED)
    summary = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    industry = models.CharField("sector / project context", max_length=120, blank=True,
                                help_text="For example: Student capstone, Local government, Logistics or Retail.")
    contribution = models.CharField("your contribution", max_length=180, blank=True,
                                    help_text="For example: Full-stack development, UX and deployment.")
    project_year = models.PositiveSmallIntegerField(null=True, blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(9999)])
    challenge = models.TextField(max_length=2000, blank=True)
    solution = models.TextField(max_length=2000, blank=True)
    outcome = models.TextField("result / outcome", max_length=2000, blank=True,
                               help_text="Describe an actual result. Include figures only when you can substantiate them.")
    tech_stack = models.CharField(max_length=255, blank=True, help_text="Comma-separated technologies.")
    project_url = models.URLField("web application link", max_length=500, blank=True,
                                 help_text="For web apps, enter the live project or demo URL. Use http:// or https://.")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="portfolio_projects", help_text="Private association; this customer can review the project.")
    request = models.ForeignKey("capstone.CapstoneRequest", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="portfolio_entries", help_text="Optional related project request. Its customer is linked automatically.")
    is_published = models.BooleanField("publish in portfolio", default=False)
    is_featured = models.BooleanField("featured", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_featured", "-created_at", "-pk"]
        verbose_name = "portfolio project"
        verbose_name_plural = "portfolio projects"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:180] or "project"
            slug, number = base, 2
            while type(self).objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, number = f"{base}-{number}", number + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("core:portfolio_detail", args=[self.slug])

    @property
    def thumbnail(self):
        return next(iter(self.screenshots.all()), None)

    @property
    def project_domain(self):
        return (urlsplit(self.project_url).hostname or "").removeprefix("www.") if self.project_url else ""

    def customer_can_review(self, user):
        if not user.is_authenticated:
            return False
        customer_id = self.customer_id or (self.request.customer_id if self.request_id else None)
        return customer_id == user.pk


class PortfolioScreenshot(models.Model):
    project = models.ForeignKey(PortfolioProject, on_delete=models.CASCADE, related_name="screenshots")
    image = models.ImageField(upload_to=UniqueUploadPath("portfolio/screenshots"), storage=get_private_storage,
                              validators=IMAGE_VALIDATORS)
    caption = models.CharField(max_length=150, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]

    def __str__(self):
        return self.caption or f"Screenshot of {self.project}"

    def get_absolute_url(self):
        return reverse("core:portfolio_image", args=[self.pk])


class TestimonialQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(status=Testimonial.Status.APPROVED).filter(
            models.Q(portfolio_project__isnull=True) | models.Q(portfolio_project__is_published=True)
        )


class Testimonial(models.Model):
    """A customer comment shown on the landing page once staff approve it."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        HIDDEN = "hidden", "Hidden"

    RATING_CHOICES = [
        (5, "5 — Excellent"),
        (4, "4 — Very good"),
        (3, "3 — Good"),
        (2, "2 — Fair"),
        (1, "1 — Poor"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="testimonials",
        help_text="Set when the comment was written by a registered customer.",
    )
    portfolio_project = models.ForeignKey(PortfolioProject, on_delete=models.CASCADE, null=True, blank=True,
                                         related_name="testimonials", help_text="Optional project for this customer's feedback.")
    publication_consented_at = models.DateTimeField(null=True, blank=True, editable=False)
    name = models.CharField(max_length=100)
    role = models.CharField(
        "school or company", max_length=120, blank=True,
        help_text="Shown under the name, e.g. “BSIT student, PUP” or “Owner, Santos Pharmacy”.",
    )
    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES, default=5, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    message = models.TextField("comment", max_length=600)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    is_featured = models.BooleanField("featured", default=False, help_text="Featured comments show first.")
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TestimonialQuerySet.as_manager()

    class Meta:
        ordering = ["-is_featured", "-approved_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(user__isnull=False, portfolio_project__isnull=True),
                name="one_testimonial_per_customer"
            ),
            models.UniqueConstraint(fields=["user", "portfolio_project"],
                                    condition=models.Q(user__isnull=False, portfolio_project__isnull=False),
                                    name="one_testimonial_per_project_customer"),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="testimonial_rating_1_to_5"),
        ]

    def __str__(self):
        return f"{self.name} ({self.rating}★)"

    def save(self, *args, **kwargs):
        if self.status == self.Status.APPROVED and not self.approved_at:
            self.approved_at = timezone.now()
        elif self.status != self.Status.APPROVED:
            self.approved_at = None
        super().save(*args, **kwargs)

    @property
    def is_verified_customer(self):
        if self.portfolio_project_id:
            return self.user_id is not None and self.portfolio_project.customer_can_review(self.user)
        return self.user_id is not None and self.customer_is_eligible(self.user)

    @staticmethod
    def customer_is_eligible(user):
        """Only customers with at least one paid order or paid capstone request may leave a comment."""
        from capstone.models import CapstoneRequest
        from orders.models import Order

        if not user.is_authenticated:
            return False
        return (
            Order.objects.filter(user=user, status=Order.Status.PAID).exists()
            or CapstoneRequest.objects.filter(
                customer=user, status__in=CapstoneRequest.UNLOCKED_STATUSES
            ).exists()
        )


class ChunkedUpload(models.Model):
    """A large private file being uploaded in pieces (see core/chunked_uploads.py).

    Bytes are appended to a .part file under PRIVATE_MEDIA_ROOT/chunked/. When a form that
    references the upload is saved, the file is moved into the field's normal storage location.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    target = models.CharField(max_length=80, help_text="app_label.Model.field the file is destined for.")
    filename = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField()
    received = models.PositiveBigIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "completed_at"]), models.Index(fields=["updated_at"])]

    def __str__(self):
        return f"{self.filename} ({self.received}/{self.size} bytes)"

    @property
    def part_path(self):
        return os.path.join(settings.PRIVATE_MEDIA_ROOT, "chunked", f"{self.pk.hex}.part")

    @property
    def is_complete(self):
        return self.completed_at is not None

    def discard(self):
        """Delete the partial file (if it was not moved into storage) and this record."""
        try:
            os.remove(self.part_path)
        except FileNotFoundError:
            pass
        self.delete()


class VisitorCounter(models.Model):
    """Single-row running total of unique visitors (see core/visitors.py).

    Kept apart from SiteSettings so saving the settings form never overwrites the count.
    """

    total = models.PositiveBigIntegerField(default=0)

    def __str__(self):
        return f"{self.total} visitors"

    @classmethod
    def increment(cls):
        if not cls.objects.filter(pk=1).update(total=models.F("total") + 1):
            obj, created = cls.objects.get_or_create(pk=1, defaults={"total": 1})
            if not created:
                cls.objects.filter(pk=1).update(total=models.F("total") + 1)

    @classmethod
    def current(cls):
        return cls.objects.filter(pk=1).values_list("total", flat=True).first() or 0


class VisitorCountry(models.Model):
    """Unique visitors per country (ISO 3166-1 alpha-2), counted alongside VisitorCounter."""

    code = models.CharField(max_length=2, unique=True)
    visitors = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-visitors", "code"]
        verbose_name_plural = "visitor countries"

    def __str__(self):
        return f"{self.code}: {self.visitors}"

    @classmethod
    def increment(cls, code):
        if not cls.objects.filter(code=code).update(visitors=models.F("visitors") + 1):
            obj, created = cls.objects.get_or_create(code=code, defaults={"visitors": 1})
            if not created:
                cls.objects.filter(code=code).update(visitors=models.F("visitors") + 1)
