from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.urls import reverse

from core.models import ContactMessage, SiteSettings
from core.testing import PASSWORD, BaseTestCase


class SeedDemoSafetyTests(BaseTestCase):
    @override_settings(DEBUG=True)
    def test_existing_accounts_keep_their_passwords(self):
        customer = self.make_user("realcustomer")
        call_command("seed_demo", stdout=StringIO())
        customer.refresh_from_db()
        self.assertTrue(customer.check_password(PASSWORD))
        self.assertTrue(get_user_model().objects.get(email="demo@example.com").check_password("Admin2026!"))

    @override_settings(DEBUG=True)
    def test_reset_all_passwords_is_explicit_opt_in(self):
        customer = self.make_user("realcustomer")
        call_command("seed_demo", "--reset-all-passwords", stdout=StringIO())
        customer.refresh_from_db()
        self.assertTrue(customer.check_password("Admin2026!"))

    @override_settings(DEBUG=False)
    def test_refuses_to_run_in_production(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(get_user_model().objects.filter(email="admin@example.com").exists())


class ContactRateLimitTests(BaseTestCase):
    def _send(self, n):
        return self.client.post(reverse("core:contact"), {
            "name": "Visitor", "email": "visitor@example.com", "subject": f"Question {n}",
            "message": "Do you offer installation support for the inventory system?",
        })

    def test_repeated_messages_are_throttled(self):
        for n in range(5):
            self.assertEqual(self._send(n).status_code, 302)
        response = self._send(6)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(ContactMessage.objects.count(), 5)
        self.assertEqual(len(mail.outbox), 5)


class LandingClaimsTests(BaseTestCase):
    """The landing page must only advertise payment methods and stats that actually exist."""

    def test_unconfigured_methods_are_not_advertised(self):
        # Only PayPal.me is configured by default in tests: no GCash number, no card gateway keys.
        html = self.client.get(reverse("core:home")).content.decode()
        self.assertNotIn("GCash verified", html)
        self.assertNotIn("Card data secured", html)
        self.assertNotIn("Ways to pay", html)
        self.assertNotIn("debit/credit cards", html)
        self.assertIn("After you accept a quote and payment is confirmed", html)

    def test_configured_gcash_is_advertised(self):
        site = SiteSettings.load()
        site.gcash_number, site.gcash_account_name = "09170000000", "Store"
        site.save()
        self.make_product("Listed App")
        html = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("GCash", html)
        self.assertNotIn("GCash verified", html)

    def test_stats_are_pluralised_and_hidden_when_empty(self):
        self.assertNotContains(self.client.get(reverse("core:home")), "lp-stats")
        self.make_product("Only App")
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Ready-made product")
        self.assertContains(response, "Start a project")
        self.assertNotContains(response, "Average customer rating")

    def test_manual_only_store_does_not_promise_instant_access(self):
        product = self.make_product("Manual App")
        for url in (product.get_absolute_url(), reverse("orders:cart"), reverse("accounts:login")):
            response = self.client.get(url)
            self.assertNotContains(response, "Instant access")
        self.assertContains(self.client.get(product.get_absolute_url()), "as soon as we verify your payment")


class CatalogSearchTests(BaseTestCase):
    def test_search_matches_full_description_and_features(self):
        product = self.make_product("Clinic Suite", features="SMS reminders")
        product.description = "Handles patient queues and PhilHealth claims."
        product.save()
        response = self.client.get(reverse("catalog:list"), {"q": "philhealth"})
        self.assertContains(response, "Clinic Suite")
        response = self.client.get(reverse("catalog:list"), {"q": "sms reminders"})
        self.assertContains(response, "Clinic Suite")

    def test_category_tabs_keep_sort_and_form_keeps_category(self):
        response = self.client.get(reverse("catalog:list"), {"category": "mobile_app", "sort": "price_asc"})
        self.assertContains(response, "?category=software&amp;sort=price_asc")
        self.assertContains(response, '<input type="hidden" name="category" value="mobile_app">', html=False)
