"""Workspace UX contracts and isolated, optional rendering fixtures."""
import os
import shutil
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import RequestFactory
from django.urls import resolve, reverse
from django.utils import timezone

from capstone.models import CapstoneRequest
from catalog.models import Product
from core.models import ContactMessage, Testimonial
from core.testing import BaseTestCase, zip_upload
from dashboard.context_processors import workspace
from orders.models import Order
from orders.services import create_order
from payments.models import Payment


class WorkspaceTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user("workspace-owner", staff=True)
        self.customer = self.make_user("workspace-customer")
        self.product = self.make_product("Inventory Desktop")
        self.project = self.make_capstone_project("Research Archive")
        self.order, _ = create_order(self.customer, [self.product])
        self.req = CapstoneRequest.objects.create(customer=self.customer, project=self.project,
            school_name="Example University", program="BSIT", customization_notes="Example requirements")
        self.payment = Payment.objects.create(customer=self.customer, order=self.order,
            amount=self.order.total, currency="PHP", method="gcash", provider="gcash_manual",
            status="awaiting_verification", provider_reference="WS-12345")
        self.message = ContactMessage.objects.create(name="Customer", email=self.customer.email,
            subject="Installation help", message="Please send the installation steps.")
        self.review = Testimonial.objects.create(name="Customer", message="Helpful software", status="pending")
        self.client.force_login(self.staff)

    def test_workspace_shell_and_section_pages(self):
        paths = {
            "overview": reverse("dashboard:home"), "products": reverse("dashboard:product_list"),
            "product-form": reverse("dashboard:product_create"), "payments": reverse("dashboard:payment_list"),
            "orders": reverse("dashboard:order_list"), "requests": reverse("dashboard:capstone_request_list"),
            "request-detail": reverse("dashboard:capstone_request_detail", args=[self.req.reference]),
            "customers": reverse("dashboard:customer_list"), "messages": reverse("dashboard:message_list"),
            "reviews": reverse("dashboard:testimonial_list"), "settings": reverse("dashboard:settings"),
            "search": reverse("dashboard:search") + "?q=Inventory",
        }
        for name, url in paths.items():
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "css/manage.css")
                self.assertContains(response, "js/manage.js")
                self.assertContains(response, 'id="manageSidebar"')
                self.assertNotContains(response, 'aria-label="Main navigation"')
                self.assertContains(response, "Support inbox")
                self.assertContains(response, 'vendor/bootstrap/bootstrap.bundle.min.js')
                self.assertNotContains(response, "cdn.jsdelivr.net")
                if os.environ.get("CODEHUB_RENDER_PREVIEW") == "1":
                    # Test-only artifacts: fake customers/products, no production records or sessions.
                    site_root = Path(settings.BASE_DIR) / ".qa" / "site"
                    directory = site_root / "previews"
                    directory.mkdir(parents=True, exist_ok=True)
                    if name == "overview":
                        shutil.copytree(Path(settings.BASE_DIR) / "static", site_root / "static", dirs_exist_ok=True)
                    html = response.content.decode().replace("</body>", PREVIEW_CHECKS + "</body>")
                    (directory / f"{name}.html").write_text(html, encoding="utf-8")
        if os.environ.get("CODEHUB_RENDER_PREVIEW") == "1":
            self.client.logout()
            public_pages = {"storefront": "core:home", "catalog": "catalog:list", "capstones": "capstone:list",
                            "privacy": "core:privacy", "login": "accounts:login", "register": "accounts:register"}
            for name, route in public_pages.items():
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                (directory / f"public-{name}.html").write_bytes(response.content)
            self.client.force_login(self.customer)
            # First-login tutorial, then the remaining pages as a returning customer.
            (directory / "customer-onboarding.html").write_bytes(self.client.get(reverse("accounts:dashboard")).content)
            type(self.customer).objects.filter(pk=self.customer.pk).update(onboarding_completed_at=timezone.now())
            for name, url in {"account": reverse("accounts:dashboard"), "settings": reverse("accounts:settings"),
                              "orders": reverse("orders:list"),
                              "checkout": self.order.get_payment_url(),
                              "invoice": reverse("orders:invoice", args=[self.order.number])}.items():
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                (directory / f"customer-{name}.html").write_bytes(response.content)

    def test_sidebar_counts_and_current_section_are_real(self):
        response = self.client.get(reverse("dashboard:payment_list"))
        self.assertEqual(response.context["workspace_counts"], {"payments": 1, "requests": 1, "messages": 1, "reviews": 1})
        self.assertEqual(response.context["workspace_attention"], 4)
        self.assertEqual(response.context["workspace_section"], "Payments")
        response = self.client.get(reverse("dashboard:product_edit", args=[self.product.pk]))
        self.assertEqual(response.context["workspace_parent"]["url"], reverse("dashboard:product_list"))

    def test_workspace_processor_does_no_work_on_customer_or_public_pages(self):
        request = RequestFactory().get(reverse("catalog:list"))
        request.resolver_match = resolve(request.path)
        request.user = self.staff
        with self.assertNumQueries(0):
            self.assertEqual(workspace(request), {})

    def test_dashboard_period_is_bounded_and_uses_real_amounts(self):
        self.payment.status = "completed"
        self.payment.verified_at = timezone.now()
        self.payment.save()
        for days in ("7", "14", "30", "nonsense", "100000"):
            response = self.client.get(reverse("dashboard:home"), {"days": days})
            expected = int(days) if days in {"7", "14", "30"} else 14
            self.assertEqual(len(response.context["chart"]), expected)
            self.assertEqual(response.context["stats"]["period_revenue"], self.payment.amount)
            self.assertContains(response, "Partial refunds are not deducted")
        self.payment.verified_at = timezone.now() - timedelta(days=31)
        self.payment.save()
        self.assertEqual(self.client.get(reverse("dashboard:home")).context["stats"]["period_revenue"], Decimal("0"))

    def test_global_search_is_staff_only_and_includes_drafts(self):
        draft = self.make_product("Private Inventory", status="draft")
        response = self.client.get(reverse("dashboard:search"), {"q": "Inventory"})
        self.assertContains(response, draft.name)
        self.assertContains(response, reverse("dashboard:product_detail", args=[draft.pk]))
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("dashboard:search"), {"q": "Inventory"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:search")).status_code, 302)

    def test_global_search_limits_each_section_and_handles_empty_queries(self):
        for index in range(7):
            self.make_product(f"Searchable {index}")
        response = self.client.get(reverse("dashboard:search"), {"q": "Searchable"})
        self.assertEqual(len(response.context["groups"][0]["rows"]), 5)
        for q in ("", "a"):
            self.assertEqual(self.client.get(reverse("dashboard:search"), {"q": q}).context["groups"], [])
        response = self.client.get(reverse("dashboard:search"), {"q": '<script>alert("x")</script>'})
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "No matches found")

    def test_admin_page_sizes_use_an_allowlist(self):
        url = reverse("dashboard:product_list")
        for value, expected in (("20", 20), ("50", 50), ("100", 100), ("0", 20), ("-1", 20), ("999999", 20), ("bad", 20)):
            self.assertEqual(self.client.get(url, {"per_page": value}).context["page_obj"].paginator.per_page, expected)

    def test_payment_filters_combine_reference_status_and_method(self):
        url = reverse("dashboard:payment_list")
        response = self.client.get(url, {"q": "WS-12345", "status": "all", "method": "gcash"})
        self.assertEqual(list(response.context["payments"]), [self.payment])
        self.assertEqual(self.client.get(url, {"q": "WS-12345", "method": "paypal"}).context["page_obj"].paginator.count, 0)
        self.assertEqual(self.client.get(url, {"q": self.order.number}).context["page_obj"].paginator.count, 1)

    def test_inbox_search_and_resolution_keep_state(self):
        ContactMessage.objects.create(name="Other", email="closed@example.com", subject="Done", message="Closed issue", is_resolved=True)
        url = reverse("dashboard:message_list")
        self.assertEqual(self.client.get(url).context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(url, {"resolution": "all"}).context["page_obj"].paginator.count, 2)
        self.assertEqual(self.client.get(url, {"q": "installation"}).context["page_obj"].paginator.count, 1)
        target = url + "?resolution=resolved&q=help"
        response = self.client.post(reverse("dashboard:message_resolve", args=[self.message.pk]), {"next": target})
        self.assertRedirects(response, target)
        self.message.refresh_from_db()
        self.assertTrue(self.message.is_resolved)

    def test_missing_messages_and_external_next_are_not_silently_accepted(self):
        self.assertEqual(self.client.post(reverse("dashboard:message_resolve", args=[999999])).status_code, 404)
        response = self.client.post(reverse("dashboard:message_resolve", args=[self.message.pk]), {"next": "https://evil.example"})
        self.assertRedirects(response, reverse("dashboard:message_list"))

    def test_comment_search_and_invalid_replies_show_feedback(self):
        response = self.client.get(reverse("dashboard:testimonial_list"), {"q": "helpful", "status": "pending"})
        self.assertEqual(list(response.context["testimonials"]), [self.review])
        response = self.client.post(reverse("dashboard:capstone_request_message", args=[self.req.reference]), {"body": ""}, follow=True)
        self.assertContains(response, "Write a reply within the allowed length")
        self.assertFalse(self.req.messages.exists())

    def test_save_and_continue_keeps_editing_the_saved_object(self):
        data = {"name": "Draft Editor", "category": "software", "short_description": "Summary", "description": "Details",
                "price": "900", "version": "1", "status": "draft", "file": zip_upload(), "save_action": "continue",
                "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0", "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "12"}
        response = self.client.post(reverse("dashboard:product_create"), data)
        product = Product.objects.get(name="Draft Editor")
        self.assertRedirects(response, reverse("dashboard:product_edit", args=[product.pk]))
        data = {"title": "Capstone Editor", "field": "web", "short_description": "Summary", "description": "Details",
                "suggested_price": "1000", "source_code": zip_upload(), "status": "draft", "save_action": "continue"}
        response = self.client.post(reverse("dashboard:capstone_project_create"), data)
        self.assertRedirects(response, reverse("dashboard:capstone_project_edit", args=[self.project.__class__.objects.get(title="Capstone Editor").pk]))

    def test_form_errors_have_actionable_summary_and_gallery_controls(self):
        response = self.client.post(reverse("dashboard:product_create"), {})
        self.assertContains(response, "Your changes have not been saved")
        self.assertContains(response, 'href="#id_name"')
        self.assertContains(response, 'id="screenshot-empty-form"')
        self.assertContains(response, "data-add-screenshot")
        self.assertContains(response, "data-dirty-form")


# Isolated snapshots may be opened by a headless test browser without authenticating
# or interacting with the user's actual browser, profile, data or production server.
PREVIEW_CHECKS = """<script>
window.addEventListener('load', function () {
  if (location.hash === '#dark') { document.documentElement.setAttribute('data-bs-theme', 'dark'); window.dispatchEvent(new Event('themechange')); }
  if (location.hash === '#menu-open') document.querySelector('[data-sidebar-open]').click();
  const report = document.createElement('pre'); report.id = 'qa-report'; report.hidden = true;
  const sidebar = document.getElementById('manageSidebar');
  report.textContent = JSON.stringify({width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
    sidebarVisible: getComputedStyle(sidebar).visibility, sidebarWidth: sidebar.getBoundingClientRect().width,
    menuExpanded: document.querySelector('[data-sidebar-open]').getAttribute('aria-expanded'),
    mainInert: document.querySelector('.manage-main').inert,
    stylesheetLoaded: getComputedStyle(sidebar).position === 'fixed'});
  document.body.appendChild(report);
});
</script>"""
