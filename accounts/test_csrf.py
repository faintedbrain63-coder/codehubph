import re
from contextlib import contextmanager
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from core.models import SiteSettings


@contextmanager
def no_database_transaction(*args, **kwargs):
    yield


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"], CSRF_TRUSTED_ORIGINS=[])
class AccountFormCsrfTests(SimpleTestCase):
    """Exercise real CSRF middleware without database access or real credentials."""

    def setUp(self):
        self.site = patch.object(SiteSettings, "load", return_value=SiteSettings())
        self.site.start()
        self.addCleanup(self.site.stop)
        self.client = Client(enforce_csrf_checks=True)

    def form_token(self, name):
        response = self.client.get(reverse(name), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="referrer" content="origin">')
        self.assertNotContains(response, '<meta name="referrer" content="no-referrer">')
        return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.content.decode()).group(1)

    def test_same_origin_login_post_reaches_form_validation(self):
        token = self.form_token("accounts:login")
        response = self.client.post(reverse("accounts:login"), {"csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    def test_https_form_post_with_origin_only_referrer_passes(self):
        token = self.form_token("accounts:login")
        response = self.client.post(reverse("accounts:login"), {"csrfmiddlewaretoken": token}, secure=True, HTTP_REFERER="https://testserver/")
        self.assertEqual(response.status_code, 200)

    def test_null_origin_still_rejected_even_with_valid_token(self):
        token = self.form_token("accounts:login")
        response = self.client.post(reverse("accounts:login"), {"csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="null")
        self.assertEqual(response.status_code, 403)

    def test_foreign_origin_and_missing_token_still_rejected(self):
        token = self.form_token("accounts:login")
        response = self.client.post(reverse("accounts:login"), {"csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://untrusted.example")
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("accounts:login"), {}, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(response.status_code, 403)

    def test_resend_and_reset_forms_preserve_csrf_origin(self):
        for name in ("accounts:resend_verification", "accounts:password_reset"):
            token = self.form_token(name)
            response = self.client.post(reverse(name), {"csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://testserver")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)

    def test_token_pages_use_origin_only_policy_and_remain_uncacheable(self):
        # Invalid IDs never query users; omit only the transaction boundary here.
        with patch("django.db.transaction.Atomic", new=no_database_transaction):
            for name in ("accounts:verify_email", "accounts:password_reset_confirm"):
                response = self.client.get(reverse(name, kwargs={"uidb64": "invalid", "token": "invalid"}), secure=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Referrer-Policy"], "origin")
                self.assertContains(response, '<meta name="referrer" content="origin">')
                self.assertIn("no-store", response["Cache-Control"])
