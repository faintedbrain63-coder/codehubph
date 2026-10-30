import os
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from capstone.models import CapstoneProject, CapstoneRequest
from catalog.models import Product
from core.testing import PASSWORD, BaseTestCase, zip_upload
from orders.models import Order
from orders.services import create_order
from payments.models import Payment
from payments.providers import get_provider
from payments.services import PaymentError, approve_payment, submit_manual_payment


@override_settings(PRODUCT_SALES_ENABLED=False)
class ProjectServiceTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_user("project-client")
        self.staff = self.make_user("project-owner", staff=True)

    def payload(self, **overrides):
        data = {"request_title": "Community records portal", "project_type": "web", "client_type": "lgu",
                "school_name": "Example Municipality", "program": "", "group_members": "",
                "customization_notes": "A records portal with staff roles, reporting and status updates.",
                "preferred_deadline": ""}
        data.update(overrides)
        return data

    def create_request(self, **overrides):
        self.client.force_login(self.customer)
        response = self.client.post(reverse("capstone:request_new"), self.payload(**overrides))
        self.assertEqual(response.status_code, 302)
        req = CapstoneRequest.objects.latest("pk")
        self.assertRedirects(response, req.get_absolute_url())
        return req

    def test_public_pages_offer_custom_services_and_all_client_groups(self):
        response = self.client.get(reverse("core:home"))
        for text in ("Web applications", "Mobile applications", "Software systems", "Student capstone projects",
                     "Local government units", "Military organizations", "Businesses", "Start a project"):
            self.assertContains(response, text)
        for text in ('href="/products/', 'href="/cart/', "Buy now", "Browse products", "Ready-to-use"):
            self.assertNotContains(response, text)
        response = self.client.get(reverse("capstone:list"))
        self.assertContains(response, "Request a custom project")
        self.assertNotContains(response, 'href="/cart/')

    def test_old_catalog_cart_and_buy_urls_cannot_create_orders(self):
        product = self.make_product()
        for url in (reverse("catalog:list"), product.get_absolute_url(), reverse("orders:cart")):
            self.assertRedirects(self.client.get(url), reverse("capstone:list"))
        for user in (None, self.customer):
            if user:
                self.client.force_login(user)
            for name in ("orders:cart_add", "orders:cart_remove", "orders:buy_now", "orders:cart_checkout"):
                url = reverse(name) if name == "orders:cart_checkout" else reverse(name, args=[product.slug])
                self.assertRedirects(self.client.post(url), reverse("capstone:list"))
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())
        with self.assertRaisesMessage(ValueError, "sales have ended"):
            create_order(self.customer, [product])

    def test_legacy_sign_in_intent_cannot_resume_a_purchase(self):
        import time
        product = self.make_product()
        session = self.client.session
        session["purchase_intent"] = {"product": product.slug, "at": int(time.time())}
        session.save()
        self.client.post(reverse("accounts:login"), {"email": self.customer.email, "password": PASSWORD})
        self.assertFalse(Order.objects.exists())
        self.assertNotIn("purchase_intent", self.client.session)

    def test_past_paid_downloads_and_receipts_are_preserved_but_new_payments_are_closed(self):
        product = self.make_product()
        with override_settings(PRODUCT_SALES_ENABLED=True):
            order, _ = create_order(self.customer, [product])
        self.assertFalse(order.can_be_paid)
        with self.assertRaises(PaymentError):
            submit_manual_payment(order, self.customer, get_provider("paypal_manual"), "LEGACY-CLOSED")
        self.client.force_login(self.customer)
        self.assertNotContains(self.client.get(order.get_payment_url()), 'name="provider_reference"')
        order.mark_paid(None)
        item = order.items.get()
        response = self.client.get(reverse("orders:download", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        self.assertEqual(self.client.get(reverse("orders:invoice", args=[order.number])).status_code, 200)
        self.assertContains(self.client.get(reverse("accounts:dashboard")), "Previous purchases")

    def test_payment_submitted_before_retirement_can_still_be_verified(self):
        with override_settings(PRODUCT_SALES_ENABLED=True):
            order, _ = create_order(self.customer, [self.make_product()])
            payment = submit_manual_payment(order, self.customer, get_provider("paypal_manual"), "OLD-PAID-REFERENCE")
        approve_payment(payment.pk, self.staff)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_custom_request_requires_account(self):
        response = self.client.get(reverse("capstone:request_new"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:register"), response["Location"])

    def test_all_client_groups_can_request_all_three_platforms_without_a_service_listing(self):
        self.client.force_login(self.customer)
        for client_type in ("student", "lgu", "military", "business"):
            for platform in ("web", "mobile", "desktop"):
                with self.subTest(client=client_type, platform=platform):
                    req = self.create_request(client_type=client_type, project_type=platform,
                                              program="BSIT" if client_type == "student" else "")
                    self.assertIsNone(req.project_id)
                    self.assertEqual(req.client_type, client_type)
                    self.assertEqual(req.project_type, platform)
                    self.assertEqual(req.customer, self.customer)
                    self.assertEqual(req.status, "submitted")
        self.assertEqual(CapstoneRequest.objects.count(), 12)
        self.assertFalse(Payment.objects.exists())

    def test_invalid_briefs_are_not_saved_and_student_program_is_required(self):
        self.client.force_login(self.customer)
        invalid = ({"request_title": ""}, {"project_type": "invalid"}, {"client_type": "invalid"},
                   {"school_name": ""}, {"customization_notes": ""},
                   {"client_type": "student", "program": ""}, {"preferred_deadline": "2000-01-01"})
        for changes in invalid:
            response = self.client.post(reverse("capstone:request_new"), self.payload(**changes))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertFalse(CapstoneRequest.objects.exists())

    def test_brief_cannot_choose_another_customer_price_or_status(self):
        req = self.create_request(customer=self.staff.pk, status="paid", agreed_price="1.00", project="999")
        self.assertEqual(req.customer_id, self.customer.pk)
        self.assertEqual(req.status, "submitted")
        self.assertIsNone(req.agreed_price)
        self.assertIsNone(req.project_id)

    def test_form_prefills_only_allowed_client_and_platform_values(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("capstone:request_new") + "?client_type=business&project_type=mobile")
        self.assertEqual(response.context["form"]["client_type"].value(), "business")
        self.assertEqual(response.context["form"]["project_type"].value(), "mobile")

    def test_custom_project_quote_payment_delivery_and_messages_work(self):
        req = self.create_request()
        self.client.force_login(self.staff)
        self.client.post(reverse("dashboard:capstone_request_quote", args=[req.reference]),
                         {"agreed_price": "5000.00", "quote_notes": "Portal, source code and setup guide."})
        self.client.force_login(self.customer)
        self.client.post(reverse("capstone:request_accept", args=[req.reference]))
        req.refresh_from_db()
        self.assertEqual(req.status, "accepted")
        self.assertContains(self.client.get(req.get_payment_url()), req.title)
        payment = submit_manual_payment(req, self.customer, get_provider("paypal_manual"), "PROJECT-PAYMENT-123")
        approve_payment(payment.pk, self.staff)
        req.refresh_from_db()
        self.assertEqual(req.status, "paid")
        self.assertFalse(req.files_unlocked)
        self.assertIsNone(req.source_file)
        self.assertEqual(self.client.get(reverse("capstone:request_download", args=[req.reference, "source"])).status_code, 302)
        self.client.post(reverse("capstone:request_message", args=[req.reference]), {"body": "Please include a staff role."})
        self.assertEqual(req.messages.count(), 1)
        self.client.force_login(self.staff)
        self.client.post(reverse("dashboard:capstone_request_status", args=[req.reference]), {"action": "delivered"})
        req.refresh_from_db()
        self.assertEqual(req.status, "paid")
        self.client.post(reverse("dashboard:capstone_request_deliverables", args=[req.reference]),
                         {"delivered_source": zip_upload("custom-portal.zip")})
        self.client.post(reverse("dashboard:capstone_request_status", args=[req.reference]), {"action": "delivered"})
        req.refresh_from_db()
        self.assertEqual(req.status, "delivered")
        self.client.force_login(self.customer)
        response = self.client.get(reverse("capstone:request_download", args=[req.reference, "source"]))
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        self.client.post(reverse("capstone:request_complete", args=[req.reference]))
        req.refresh_from_db()
        self.assertEqual(req.status, "completed")

    def test_custom_brief_is_private_and_searchable_by_title(self):
        req = self.create_request()
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("dashboard:search") + "?q=Community"), req.title)
        self.assertContains(self.client.get(reverse("dashboard:capstone_request_list") + "?q=Community"), req.reference)
        other = self.make_user("unrelated")
        self.client.force_login(other)
        self.assertEqual(self.client.get(req.get_absolute_url()).status_code, 404)
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse("capstone:my_requests") + "?q=Community"), req.reference)

    def test_customer_and_admin_workspaces_focus_on_project_services(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertTemplateUsed(response, "accounts/projects_dashboard.html")
        self.assertContains(response, "Recent project requests")
        self.assertNotContains(response, "Browse products")
        self.assertNotContains(response, "Products owned")
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "Project services")
        self.assertNotContains(response, "All digital products")
        self.assertNotContains(response, "New product")
        self.assertEqual(self.client.post(reverse("dashboard:product_create"), {}).status_code, 302)
        self.assertFalse(Product.objects.exists())

    def test_service_listing_can_be_created_without_prebuilt_files(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("dashboard:capstone_project_create"), {
            "title": "Custom mobile application", "field": "mobile", "short_description": "An app for your organization.",
            "description": "We define and build your mobile app around an agreed project scope.",
            "suggested_price": "5000.00", "status": "published",
        })
        self.assertEqual(response.status_code, 302)
        project = CapstoneProject.objects.get(title="Custom mobile application")
        self.assertFalse(project.source_code)
        self.assertContains(self.client.get(project.get_absolute_url()), project.title)

    def test_production_service_pages_render_and_optional_previews(self):
        pages = {"public-storefront": reverse("core:home"), "public-services": reverse("capstone:list"),
                 "public-login": reverse("accounts:login"), "public-register": reverse("accounts:register")}
        root = Path(settings.BASE_DIR) / ".qa/site"
        if os.environ.get("CODEHUB_RENDER_SERVICES") == "1":
            (root / "previews").mkdir(parents=True, exist_ok=True)
            shutil.copytree(Path(settings.BASE_DIR) / "static", root / "static", dirs_exist_ok=True)
        for user, extra in ((None, {}), (self.customer, {"customer-account": reverse("accounts:dashboard"),
                            "customer-project-request": reverse("capstone:request_new"),
                            "customer-settings": reverse("accounts:settings")}),
                            (self.staff, {"overview": reverse("dashboard:home"), "settings": reverse("dashboard:settings"),
                                          "service-form": reverse("dashboard:capstone_project_create")})):
            if user:
                get_user_model().objects.filter(pk=user.pk).update(onboarding_completed_at="2026-10-24T00:00:00Z")
                self.client.force_login(user)
            for name, url in (pages if user is None else extra).items():
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                if os.environ.get("CODEHUB_RENDER_SERVICES") == "1":
                    (root / "previews" / f"{name}.html").write_bytes(response.content)
