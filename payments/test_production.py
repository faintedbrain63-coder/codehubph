from io import StringIO
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from payments.management.commands.check_paypal import REQUIRED_EVENTS, configuration_issues
from payments.providers import paypal_api


@override_settings(
    PAYPAL_MODE="automated", PAYPAL_ENV="live", PAYPAL_CLIENT_ID="test-client-id", PAYPAL_SECRET="private-test-secret",
    PAYPAL_WEBHOOK_ID="WH-TEST", SITE_URL="https://shop.example.com", DEBUG=False,
    ALLOWED_HOSTS=["shop.example.com"], CSRF_TRUSTED_ORIGINS=["https://shop.example.com"],
    SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
)
class PayPalProductionChecksTests(SimpleTestCase):
    def test_valid_production_settings_pass_without_network_access(self):
        self.assertEqual(configuration_issues(True), [])
        with patch("payments.providers.paypal_api._access_token") as authenticate:
            call_command("check_paypal", production=True, stdout=StringIO())
        authenticate.assert_not_called()

    @patch("payments.providers.paypal_api._access_token", return_value="private-token")
    def test_authentication_can_be_checked_before_webhook_setup(self, token):
        with override_settings(PAYPAL_WEBHOOK_ID=""), patch("payments.providers.paypal_api._request") as request:
            call_command("check_paypal", authenticate_only=True, stdout=StringIO())
        token.assert_called_once()
        request.assert_not_called()

    def test_missing_credentials_and_insecure_hosting_are_reported_without_secrets(self):
        with override_settings(PAYPAL_CLIENT_ID="", PAYPAL_SECRET="", PAYPAL_WEBHOOK_ID="", DEBUG=True, SITE_URL="http://localhost:8000", PAYPAL_MODE="manual", PAYPAL_ENV="sandbox"):
            issues = configuration_issues(True)
        self.assertTrue(any("PAYPAL_CLIENT_ID" in issue for issue in issues))
        self.assertTrue(any("PAYPAL_SECRET" in issue for issue in issues))
        self.assertTrue(any("PAYPAL_WEBHOOK_ID" in issue for issue in issues))
        self.assertTrue(any("HTTPS" in issue for issue in issues))
        self.assertTrue(any("DEBUG" in issue for issue in issues))

    def test_domain_and_csrf_must_be_explicitly_configured(self):
        with override_settings(ALLOWED_HOSTS=["*"], CSRF_TRUSTED_ORIGINS=[]):
            issues = configuration_issues(True)
        self.assertTrue(any("ALLOWED_HOSTS" in issue for issue in issues))
        self.assertTrue(any("CSRF_TRUSTED_ORIGINS" in issue for issue in issues))

    def test_invalid_environment_fails_closed(self):
        with override_settings(PAYPAL_ENV="lve"):
            self.assertFalse(paypal_api.is_configured())
            with self.assertRaises(paypal_api.PayPalError):
                paypal_api.base_url()
        self.assertEqual(paypal_api.base_url(), "https://api-m.paypal.com")
        with override_settings(PAYPAL_ENV="sandbox"):
            self.assertEqual(paypal_api.base_url(), "https://api-m.sandbox.paypal.com")

    @patch("payments.providers.paypal_api._request")
    @patch("payments.providers.paypal_api._access_token", return_value="private-token")
    def test_live_connection_only_reads_webhook(self, token, request):
        request.return_value = {"url": "https://shop.example.com/payments/webhooks/paypal/", "event_types": [{"name": event} for event in REQUIRED_EVENTS]}
        output = StringIO()
        call_command("check_paypal", production=True, connect=True, stdout=output)
        request.assert_called_once_with("GET", "/v1/notifications/webhooks/WH-TEST")
        self.assertNotIn("private-token", output.getvalue())
        self.assertNotIn("private-test-secret", output.getvalue())

    @patch("payments.providers.paypal_api._request")
    @patch("payments.providers.paypal_api._access_token", return_value="private-token")
    def test_wrong_webhook_and_missing_event_subscriptions_fail(self, token, request):
        request.return_value = {"url": "https://wrong.example/payments/webhooks/paypal/"}
        with self.assertRaisesMessage(CommandError, "does not match"):
            call_command("check_paypal", production=True, connect=True, stdout=StringIO())
        request.return_value = {"url": "https://shop.example.com/payments/webhooks/paypal/", "event_types": [{"name": "PAYMENT.CAPTURE.COMPLETED"}]}
        with self.assertRaisesMessage(CommandError, "Missing webhook"):
            call_command("check_paypal", production=True, connect=True, stdout=StringIO())

    @patch("payments.providers.paypal_api._access_token", side_effect=requests.ConnectionError("private-test-secret"))
    def test_network_error_does_not_disclose_exception_or_secret(self, token):
        with self.assertRaises(CommandError) as error:
            call_command("check_paypal", production=True, connect=True, stdout=StringIO())
        self.assertNotIn("private-test-secret", str(error.exception))
