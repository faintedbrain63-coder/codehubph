from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.storage import get_private_storage
from core.validators import IMAGE_VALIDATORS, PRODUCT_FILE_VALIDATORS, UniqueUploadPath


class ProductQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Product.Status.PUBLISHED)


class Product(models.Model):
    class Category(models.TextChoices):
        # Web apps are sold as capstone projects (CapstoneProject.Field.WEB), not as downloads.
        SOFTWARE = "software", "Software"
        MOBILE_APP = "mobile_app", "Mobile App"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True, help_text="Leave blank to generate from the name.")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SOFTWARE)
    short_description = models.CharField(max_length=220, help_text="One or two sentences shown on product cards.")
    description = models.TextField(help_text="Full description shown on the product page.")
    features = models.TextField(blank=True, help_text="One feature per line.")
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("1.00"))]
    )
    thumbnail = models.ImageField(
        upload_to=UniqueUploadPath("products/thumbnails"), blank=True, validators=IMAGE_VALIDATORS
    )
    file = models.FileField(
        "digital file",
        upload_to=UniqueUploadPath("products/files"),
        storage=get_private_storage,
        validators=PRODUCT_FILE_VALIDATORS,
        help_text="The file customers download after payment (zip, apk, exe, ...). Stored privately.",
    )
    file_size = models.PositiveBigIntegerField(default=0, editable=False)
    version = models.CharField(max_length=30, default="1.0.0")
    demo_url = models.URLField("demo URL", blank=True)
    tech_stack = models.CharField(max_length=255, blank=True, help_text="Comma-separated, e.g. Django, PostgreSQL, Bootstrap")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    is_featured = models.BooleanField("featured", default=False, help_text="Featured products show first in the catalog's newest sort.")
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["status", "-published_at"]),
            models.Index(fields=["status", "is_featured"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        if self.file:
            try:
                self.file_size = self.file.size
            except (FileNotFoundError, OSError):
                pass
        super().save(*args, **kwargs)

    def _unique_slug(self):
        base = slugify(self.name)[:150] or "product"
        slug, n = base, 2
        while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug, n = f"{base}-{n}", n + 1
        return slug

    def get_absolute_url(self):
        return reverse("catalog:detail", kwargs={"slug": self.slug})

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    @property
    def category_icon(self):
        return {"software": "pc-display", "mobile_app": "phone"}.get(self.category, "box")


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=UniqueUploadPath("products/screenshots"), validators=IMAGE_VALIDATORS)
    caption = models.CharField(max_length=150, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.caption or f"Screenshot of {self.product}"
