from django.urls import reverse

from catalog.models import Product
from core.testing import BaseTestCase, png_upload, zip_upload


class AdminPortalTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user("owner", staff=True)
        self.customer = self.make_user("shopper")

    def test_portal_requires_staff(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertIn(reverse("accounts:login"), response["Location"])
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 200)

    def test_create_product_publishes_to_store(self):
        self.client.force_login(self.staff)
        data = {
            "name": "Brand New Tool",
            "slug": "",
            "category": "mobile_app",
            "short_description": "A new tool",
            "description": "Longer description",
            "features": "One\nTwo",
            "price": "750.00",
            "version": "1.0.0",
            "tech_stack": "Django",
            "demo_url": "",
            "status": "published",
            "thumbnail": png_upload("thumb.png"),
            "file": zip_upload("tool.zip"),
            "images-TOTAL_FORMS": "0",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "12",
        }
        response = self.client.post(reverse("dashboard:product_create"), data)
        self.assertRedirects(response, reverse("dashboard:product_list"))
        product = Product.objects.get(name="Brand New Tool")
        self.assertEqual(product.slug, "brand-new-tool")
        self.assertTrue(product.file.name.startswith("products/files/"))
        self.assertNotIn("tool", product.file.name)  # stored under a random name
        self.client.logout()
        self.assertContains(self.client.get(reverse("catalog:list")), "Brand New Tool")

    def test_upload_rejects_disallowed_extension(self):
        self.client.force_login(self.staff)
        data = {
            "name": "Bad Upload", "category": "software", "short_description": "x", "description": "x",
            "price": "10.00", "version": "1", "status": "draft",
            "file": zip_upload("evil.php", b"<?php echo 1; ?>"),
            "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "12",
        }
        response = self.client.post(reverse("dashboard:product_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not allowed")
        self.assertFalse(Product.objects.filter(name="Bad Upload").exists())

    def test_settings_update(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:settings"),
            {"site_name": "", "tagline": "New tagline", "contact_email": "hello@example.com",
             "contact_phone": "", "paypal_me_url": "", "gcash_account_name": "Owner",
             "gcash_number": "09171234567", "payment_instructions": "Pay within 24 hours."},
        )
        self.assertRedirects(response, reverse("dashboard:settings"))
        self.assertContains(self.client.get(reverse("core:home")), "New tagline")
