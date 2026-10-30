"""Shared helpers for the test suite."""

import atexit
import io
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from capstone.models import CapstoneProject
from catalog.models import Product

TEST_MEDIA = tempfile.mkdtemp(prefix="codehub-tests-")
atexit.register(shutil.rmtree, TEST_MEDIA, ignore_errors=True)

PASSWORD = "S3cure-test-pass!"


def png_upload(name="proof.png"):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "#4f46e5").save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def zip_upload(name="app.zip", content=b"PK\x05\x06" + b"\x00" * 18):
    return SimpleUploadedFile(name, content, content_type="application/zip")


@override_settings(
    SITE_URL="https://testserver",
    # Legacy commerce tests keep exercising historical records and in-flight payments.
    # Service-only tests explicitly use the production value (False).
    PRODUCT_SALES_ENABLED=True,
    PRIVATE_MEDIA_ROOT=f"{TEST_MEDIA}/private",
    MEDIA_ROOT=f"{TEST_MEDIA}/media",
    PAYPAL_CLIENT_ID="",
    PAYPAL_SECRET="",
    PAYPAL_MODE="manual",
    DOWNLOAD_LIMIT=3,
)
class BaseTestCase(TestCase):
    def setUp(self):
        cache.clear()

    def complete_registration(self, email="maria@example.com"):
        """Complete the real activation and login steps in customer journey tests."""
        from accounts.email_security import verification_path
        from django.urls import reverse
        from urllib.parse import parse_qs, urlsplit

        user = get_user_model().objects.get(email=email)
        self.assertNotIn("_auth_user_id", self.client.session)
        confirmed = self.client.post(verification_path(user))
        self.assertEqual(confirmed.status_code, 302)
        next_url = parse_qs(urlsplit(confirmed["Location"]).query).get("next", [""])[0]
        return self.client.post(reverse("accounts:login"), {"email": email, "password": PASSWORD, "next": next_url})

    @staticmethod
    def make_user(name="alice", staff=False, **extra):
        User = get_user_model()
        return User.objects.create_user(
            email=extra.pop("email", f"{name}@example.com"),
            password=PASSWORD,
            first_name=extra.pop("first_name", name.title()),
            is_staff=staff,
            **extra,
        )

    @staticmethod
    def make_product(name="Test App", status=Product.Status.PUBLISHED, price="999.00", **extra):
        return Product.objects.create(
            name=name,
            short_description=f"{name} short description",
            description=f"{name} description",
            price=Decimal(price),
            status=status,
            file=zip_upload(),
            **extra,
        )

    @staticmethod
    def make_capstone_project(title="Thesis Archive", with_docs=False, **extra):
        return CapstoneProject.objects.create(
            title=title,
            short_description="Capstone short description",
            description="Capstone description",
            suggested_price=Decimal("15000.00"),
            status=CapstoneProject.Status.PUBLISHED,
            source_code=zip_upload("source.zip"),
            documentation=SimpleUploadedFile("docs.pdf", b"%PDF-1.4 demo") if with_docs else "",
            **extra,
        )
