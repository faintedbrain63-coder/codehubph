from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from capstone.models import CapstoneProject, CapstoneRequest
from catalog.models import Product, ProductImage
from core.testing import BaseTestCase, png_upload, zip_upload
from orders.services import create_order


class CatalogAdminTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user("catalog-owner", staff=True)
        self.customer = self.make_user("catalog-customer")
        self.client.force_login(self.staff)

    @staticmethod
    def product_data(**extra):
        data = {
            "name": "New Product", "category": "software", "short_description": "Short summary",
            "description": "Full description", "price": "700.00", "version": "1.0", "status": "draft",
            "file": zip_upload(), "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "12",
        }
        data.update(extra)
        return data

    @staticmethod
    def project_data(**extra):
        data = {
            "title": "New Capstone", "field": "web", "short_description": "Short project summary",
            "description": "Full description", "suggested_price": "12000.00", "status": "draft",
            "source_code": zip_upload(), "documentation": SimpleUploadedFile("manual.pdf", b"%PDF-1.4 demo"),
        }
        data.update(extra)
        return data

    def test_all_product_categories_can_be_uploaded_and_published(self):
        for category, filename in (("software", "desktop.exe"), ("mobile_app", "mobile.apk")):
            with self.subTest(category=category):
                response = self.client.post(reverse("dashboard:product_create"), self.product_data(
                    name=f"New {category}", category=category, file=zip_upload(filename), status="published",
                    thumbnail=png_upload(), **{"images-TOTAL_FORMS": "1", "images-0-image": png_upload("screen.png"),
                    "images-0-caption": "Main screen", "images-0-sort_order": "0"},
                ))
                self.assertRedirects(response, reverse("dashboard:product_list"))
                product = Product.objects.get(category=category)
                self.assertEqual(product.images.count(), 1)
                self.assertTrue(product.file.storage.exists(product.file.name))
                self.assertContains(self.client.get(reverse("catalog:list")), product.name)

    def test_create_link_preselects_only_valid_product_categories(self):
        url = reverse("dashboard:product_create")
        self.assertEqual(self.client.get(url, {"category": "mobile_app"}).context["form"]["category"].value(), "mobile_app")
        self.assertEqual(self.client.get(url, {"category": "unknown"}).context["form"]["category"].value(), "software")

    def test_product_search_and_combined_filters(self):
        match = self.make_product("Unusual Name", category="mobile_app", tech_stack="Kotlin")
        self.make_product("Other App", category="software", tech_stack="Kotlin")
        self.make_product("Draft App", status="draft", category="mobile_app", tech_stack="Kotlin")
        url = reverse("dashboard:product_list")
        response = self.client.get(url, {"q": "kOtLiN", "category": "mobile_app", "status": "published"})
        self.assertEqual(list(response.context["products"]), [match])
        self.assertContains(response, "1 product found")
        self.assertEqual(self.client.get(url, {"q": "Unusual Name description"}).context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(url, {"q": "no-such-item"}).context["page_obj"].paginator.count, 0)

    def test_product_pagination_keeps_search_and_filters(self):
        for i in range(21):
            self.make_product(f"Paged {i}", category="mobile_app")
        response = self.client.get(reverse("dashboard:product_list"), {"q": "Paged", "category": "mobile_app", "status": "published", "page": 2})
        self.assertEqual(len(response.context["products"]), 1)
        self.assertContains(response, "q=Paged&amp;category=mobile_app&amp;status=published")

    def test_edit_without_file_keeps_upload_and_updates_product(self):
        product = self.make_product(status="draft")
        original = product.file.name
        data = self.product_data(name="Renamed App", category="mobile_app", status="published")
        data.pop("file")
        response = self.client.post(reverse("dashboard:product_edit", args=[product.pk]), data)
        self.assertRedirects(response, reverse("dashboard:product_list"))
        product.refresh_from_db()
        self.assertEqual((product.name, product.category, product.file.name), ("Renamed App", "mobile_app", original))
        self.assertTrue(product.is_published)

    def test_edit_can_replace_private_file_and_delete_screenshot(self):
        product = self.make_product()
        old = product.file.name
        image = ProductImage.objects.create(product=product, image=png_upload())
        response = self.client.post(reverse("dashboard:product_edit", args=[product.pk]), self.product_data(
            file=zip_upload("updated.zip", b"updated"), **{"images-TOTAL_FORMS": "1", "images-INITIAL_FORMS": "1",
            "images-0-id": str(image.pk), "images-0-DELETE": "on"},
        ))
        self.assertRedirects(response, reverse("dashboard:product_list"))
        product.refresh_from_db()
        self.assertNotEqual(product.file.name, old)
        self.assertEqual(product.file_size, 7)
        self.assertFalse(product.images.exists())

    def test_invalid_form_and_gallery_errors_render_together(self):
        response = self.client.post(reverse("dashboard:product_create"), self.product_data(price="0", **{
            "images-TOTAL_FORMS": "1", "images-0-image": zip_upload("bad.png", b"not an image"),
            "images-0-sort_order": "0",
        }))
        self.assertEqual(response.status_code, 200)
        self.assertIn("price", response.context["form"].errors)
        self.assertIn("image", response.context["formset"].forms[0].errors)
        self.assertFalse(Product.objects.exists())

    @override_settings(MAX_PRODUCT_FILE_MB=0)
    def test_upload_size_limit_is_enforced(self):
        response = self.client.post(reverse("dashboard:product_create"), self.product_data())
        self.assertContains(response, "maximum allowed size")
        self.assertFalse(Product.objects.exists())

    def test_required_upload_cannot_be_skipped(self):
        data = self.product_data()
        data.pop("file")
        self.assertIn("file", self.client.post(reverse("dashboard:product_create"), data).context["form"].errors)
        data = self.project_data()
        data.pop("source_code")
        response = self.client.post(reverse("dashboard:capstone_project_create"), data)
        self.assertRedirects(response, reverse("dashboard:capstone_project_list"))
        self.assertFalse(CapstoneProject.objects.get().source_code)

    def test_delete_unused_product_and_protect_sold_product(self):
        unused = self.make_product("Unused")
        url = reverse("dashboard:product_delete", args=[unused.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse("dashboard:product_list"))
        self.assertFalse(Product.objects.filter(pk=unused.pk).exists())
        sold = self.make_product("Sold")
        order, _ = create_order(self.customer, [sold])
        self.assertRedirects(self.client.post(reverse("dashboard:product_delete", args=[sold.pk])), reverse("dashboard:product_list"))
        sold.refresh_from_db()
        self.assertEqual(sold.status, "draft")
        self.assertEqual(order.items.get().product_id, sold.pk)

    def test_capstone_create_read_update_and_delete(self):
        self.assertRedirects(self.client.post(reverse("dashboard:capstone_project_create"), self.project_data(status="published")), reverse("dashboard:capstone_project_list"))
        project = CapstoneProject.objects.get()
        self.assertContains(self.client.get(reverse("dashboard:capstone_project_detail", args=[project.pk])), project.title)
        self.assertContains(self.client.get(project.get_absolute_url()), project.title)
        original = project.source_code.name
        data = self.project_data(title="Updated Capstone", field="mobile", status="draft")
        data.pop("source_code")
        data.pop("documentation")
        self.assertRedirects(self.client.post(reverse("dashboard:capstone_project_edit", args=[project.pk]), data), reverse("dashboard:capstone_project_list"))
        project.refresh_from_db()
        self.assertEqual((project.title, project.field, project.source_code.name), ("Updated Capstone", "mobile", original))
        self.assertEqual(self.client.get(reverse("dashboard:capstone_project_delete", args=[project.pk])).status_code, 405)
        self.client.post(reverse("dashboard:capstone_project_delete", args=[project.pk]))
        self.assertFalse(CapstoneProject.objects.exists())

    def test_capstone_with_request_is_archived_not_deleted(self):
        project = self.make_capstone_project()
        req = CapstoneRequest.objects.create(customer=self.customer, project=project, school_name="School", program="BSIT", customization_notes="Details")
        self.client.post(reverse("dashboard:capstone_project_delete", args=[project.pk]))
        project.refresh_from_db()
        self.assertEqual(project.status, "draft")
        self.assertTrue(CapstoneRequest.objects.filter(pk=req.pk).exists())

    def test_capstone_search_and_filters(self):
        match = self.make_capstone_project("Inventory", field="web", tech_stack="Django")
        self.make_capstone_project("IoT Sensor", field="iot", tech_stack="Arduino")
        url = reverse("dashboard:capstone_project_list")
        response = self.client.get(url, {"q": "dJaNgO", "field": "web", "status": "published"})
        self.assertEqual(list(response.context["projects"]), [match])
        self.assertContains(response, "1 project found")
        self.assertEqual(self.client.get(url, {"q": "absent"}).context["page_obj"].paginator.count, 0)

    def test_draft_previews_and_uploads_are_staff_only(self):
        product = self.make_product(status="draft")
        project = self.make_capstone_project(with_docs=True)
        project.status = "draft"
        project.save()
        urls = [reverse("dashboard:product_detail", args=[product.pk]), reverse("dashboard:product_file", args=[product.pk]),
                reverse("dashboard:capstone_project_detail", args=[project.pk]),
                reverse("dashboard:capstone_project_file", args=[project.pk, "source"]),
                reverse("dashboard:capstone_project_file", args=[project.pk, "documentation"])]
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 404)
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            if response.streaming:
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertIn("attachment", response["Content-Disposition"])
                self.assertTrue(b"".join(response.streaming_content))
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.customer)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_missing_and_unrecognized_files_return_404(self):
        product = self.make_product()
        product.file.storage.delete(product.file.name)
        self.assertEqual(self.client.get(reverse("dashboard:product_file", args=[product.pk])).status_code, 404)
        project = self.make_capstone_project()
        for kind in ("documentation", "__dict__", "thumbnail"):
            self.assertEqual(self.client.get(reverse("dashboard:capstone_project_file", args=[project.pk, kind])).status_code, 404)

    def test_customer_cannot_write_catalog(self):
        self.client.force_login(self.customer)
        product = self.make_product()
        project = self.make_capstone_project()
        for name, args in (("product_create", []), ("product_edit", [product.pk]), ("product_delete", [product.pk]),
                           ("capstone_project_create", []), ("capstone_project_edit", [project.pk]), ("capstone_project_delete", [project.pk])):
            self.assertEqual(self.client.post(reverse(f"dashboard:{name}", args=args), {}).status_code, 403)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(CapstoneProject.objects.count(), 1)

    def test_csrf_required_for_catalog_writes(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        product = self.make_product()
        response = client.post(reverse("dashboard:product_delete", args=[product.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_sidebar_and_alert_assets_on_django_admin_and_store_console(self):
        superuser = self.make_user("super-owner", staff=True, is_superuser=True)
        self.client.force_login(superuser)
        for url in (reverse("admin:index"), reverse("admin:catalog_product_changelist"), reverse("dashboard:home")):
            response = self.client.get(url)
            self.assertContains(response, "Mobile apps")
            self.assertNotContains(response, "category=web_app")
            self.assertContains(response, "sweetalert2.min.js")
            self.assertContains(response, "js/alerts.js")
        for name in ("core:home", "accounts:login", "accounts:register", "catalog:list"):
            response = self.client.get(reverse(name), follow=True)
            self.assertContains(response, "js/alerts.js")
