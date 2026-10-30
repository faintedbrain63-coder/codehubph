"""Signed-out buyers register (or sign in) and continue checkout; first-time customers see the buying tutorial."""

import time
from importlib import import_module
from urllib.parse import quote

from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse

from capstone.models import CapstoneProject
from catalog.models import Product
from core.legal import CURRENT_VERSIONS
from core.testing import PASSWORD, BaseTestCase
from orders.models import Order
from orders.views import PURCHASE_INTENT_KEY

User = get_user_model()


def registration(**overrides):
    data = {
        "first_name": "Maria", "last_name": "Santos", "email": "maria@example.com", "phone_number": "", "school": "",
        "password1": PASSWORD, "password2": PASSWORD, "accept_privacy": "on", "accept_license": "on",
        "privacy_version": CURRENT_VERSIONS["privacy"], "license_version": CURRENT_VERSIONS["license"],
    }
    data.update(overrides)
    return data


class SignedOutPurchaseTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product("Clinic Desktop", price="1499.00")

    def test_buy_now_sends_visitor_to_registration_then_straight_to_checkout(self):
        response = self.client.post(reverse("orders:buy_now", args=[self.product.slug]))
        expected = reverse("accounts:register") + "?next=" + quote(self.product.get_absolute_url(), safe="")
        self.assertRedirects(response, expected, fetch_redirect_response=False)
        page = self.client.get(response["Location"])
        self.assertContains(page, "Register to continue where you left off")
        self.assertContains(page, "Create a free account to buy")

        response = self.client.post(expected, registration(next=self.product.get_absolute_url()))
        order = Order.objects.get(user__email="maria@example.com")
        self.assertRedirects(response, order.get_payment_url(), fetch_redirect_response=False)
        self.assertEqual([item.product for item in order.items.all()], [self.product])
        self.assertNotIn(PURCHASE_INTENT_KEY, self.client.session)

    def test_cart_checkout_resumes_after_signing_in_to_an_existing_account(self):
        user = self.make_user("returning")
        self.client.post(reverse("orders:cart_add", args=[self.product.slug]))
        response = self.client.post(reverse("orders:cart_checkout"))
        self.assertIn(reverse("accounts:register"), response["Location"])
        self.assertFalse(Order.objects.exists())

        response = self.client.post(reverse("accounts:login"), {"email": user.email, "password": PASSWORD})
        order = Order.objects.get(user=user)
        self.assertRedirects(response, order.get_payment_url(), fetch_redirect_response=False)
        self.assertEqual(self.client.session.get("cart"), [])

    def test_abandoned_intent_expires_and_never_creates_a_later_order(self):
        self.client.post(reverse("orders:buy_now", args=[self.product.slug]))
        session = self.client.session
        intent = session[PURCHASE_INTENT_KEY]
        intent["at"] = int(time.time()) - 2 * 60 * 60
        session[PURCHASE_INTENT_KEY] = intent
        session.save()
        response = self.client.post(reverse("accounts:register"), registration())
        self.assertRedirects(response, reverse("accounts:dashboard"), fetch_redirect_response=False)
        self.assertFalse(Order.objects.exists())

    def test_intent_for_an_unpublished_product_falls_back_to_next(self):
        self.client.post(reverse("orders:buy_now", args=[self.product.slug]))
        Product.objects.filter(pk=self.product.pk).update(status=Product.Status.DRAFT)
        response = self.client.post(reverse("accounts:register"), registration(next="/products/"))
        self.assertRedirects(response, "/products/", fetch_redirect_response=False)
        self.assertFalse(Order.objects.exists())

    def test_signed_in_buyer_goes_straight_to_checkout(self):
        user = self.make_user("buyer")
        self.client.force_login(user)
        response = self.client.post(reverse("orders:buy_now", args=[self.product.slug]))
        self.assertRedirects(response, Order.objects.get(user=user).get_payment_url(), fetch_redirect_response=False)

    def test_product_page_offers_buy_and_cart_to_visitors(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, f'action="{reverse("orders:buy_now", args=[self.product.slug])}"')
        self.assertContains(response, f'action="{reverse("orders:cart_add", args=[self.product.slug])}"')
        self.assertContains(response, "create a free account first")

    def test_capstone_request_registers_then_returns_to_the_form(self):
        project = self.make_capstone_project()
        url = reverse("capstone:request_create", args=[project.slug])
        self.assertIn(reverse("accounts:register"), self.client.get(url)["Location"])
        response = self.client.post(reverse("accounts:register"), registration(next=url))
        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.assertEqual(self.client.get(url).status_code, 200)


class OnboardingTests(BaseTestCase):
    def test_new_customer_sees_tutorial_until_it_is_finished(self):
        self.client.post(reverse("accounts:register"), registration())
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, 'id="onboarding"')
        self.assertContains(response, "data-onboarding-autostart")
        self.assertContains(response, "js/onboarding.js")

        done = self.client.post(reverse("accounts:onboarding_done"), HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(done.status_code, 204)
        self.assertIsNotNone(User.objects.get(email="maria@example.com").onboarding_completed_at)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, 'id="onboarding"')  # still available from "How buying works"
        self.assertContains(response, 'data-bs-target="#onboarding"')
        self.assertNotContains(response, "data-onboarding-autostart")

    def test_finishing_without_javascript_returns_to_a_safe_page(self):
        self.client.force_login(self.make_user("nojs"))
        response = self.client.post(reverse("accounts:onboarding_done"), {"next": "/products/"})
        self.assertRedirects(response, "/products/", fetch_redirect_response=False)
        response = self.client.post(reverse("accounts:onboarding_done"), {"next": "https://evil.example/"})
        self.assertRedirects(response, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_finishing_requires_post_and_sign_in(self):
        self.assertEqual(self.client.post(reverse("accounts:onboarding_done")).status_code, 302)
        self.client.force_login(self.make_user("getter"))
        self.assertEqual(self.client.get(reverse("accounts:onboarding_done")).status_code, 405)

    def test_tutorial_is_not_shown_to_visitors_or_staff(self):
        self.assertNotContains(self.client.get(reverse("core:home")), 'id="onboarding"')
        self.client.force_login(self.make_user("owner", staff=True))
        self.assertNotContains(self.client.get(reverse("catalog:list")), 'id="onboarding"')

    def test_tutorial_explains_custom_projects_quotes_and_delivery(self):
        self.client.force_login(self.make_user("learner"))
        response = self.client.get(reverse("catalog:list"))
        for text in ("How projects work", "web apps, mobile apps and software", "Review your quote",
                     "Start a project", "Project requests", "Get your files"):
            self.assertContains(response, text)


class WebAppMigrationTests(BaseTestCase):
    def test_existing_web_app_becomes_a_draft_capstone_offering(self):
        product = self.make_product("Legacy Web Portal", price="2500.00", tech_stack="Django")
        Product.objects.filter(pk=product.pk).update(category="web_app")
        import_module("catalog.migrations.0003_move_web_apps_to_capstone").move_web_apps(apps, None)

        product.refresh_from_db()
        self.assertEqual((product.category, product.status), (Product.Category.SOFTWARE, Product.Status.DRAFT))
        project = CapstoneProject.objects.get(title="Legacy Web Portal")
        self.assertEqual((project.field, project.status), (CapstoneProject.Field.WEB, CapstoneProject.Status.DRAFT))
        self.assertEqual(project.suggested_price, product.price)
        self.assertEqual(project.source_code.name, product.file.name)
        self.assertEqual(project.tech_stack, "Django")
