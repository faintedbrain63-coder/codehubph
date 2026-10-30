"""Read-only PayPal deployment validation. Never creates orders or captures money."""

from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from payments.providers import paypal_api

REQUIRED_EVENTS = {
    "PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.DENIED",
    "PAYMENT.CAPTURE.DECLINED", "PAYMENT.CAPTURE.REFUNDED",
}


def configuration_issues(production=False, require_webhook=True):
    issues = []
    if settings.PAYPAL_MODE != "automated":
        issues.append("Set PAYPAL_MODE=automated to use API checkout.")
    if settings.PAYPAL_ENV not in {"sandbox", "live"}:
        issues.append("PAYPAL_ENV must be sandbox or live.")
    if production and settings.PAYPAL_ENV != "live":
        issues.append("Production requires PAYPAL_ENV=live and credentials from the Live PayPal app.")
    required = ["PAYPAL_CLIENT_ID", "PAYPAL_SECRET"]
    if require_webhook:
        required.append("PAYPAL_WEBHOOK_ID")
    for name in required:
        if not getattr(settings, name, "").strip():
            issues.append(f"Set {name} in the server environment or .env.")
    if production:
        if settings.DEBUG:
            issues.append("Set DEBUG=False on the production server.")
        origin = settings.SITE_URL.rstrip("/")
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password or parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            issues.append("Set SITE_URL to your public HTTPS origin (no path, query or credentials).")
        else:
            if parsed.hostname not in settings.ALLOWED_HOSTS:
                issues.append("Add the public SITE_URL hostname explicitly to ALLOWED_HOSTS.")
            if origin not in settings.CSRF_TRUSTED_ORIGINS:
                issues.append("Add the public HTTPS SITE_URL to CSRF_TRUSTED_ORIGINS.")
        if not getattr(settings, "SESSION_COOKIE_SECURE", False):
            issues.append("Enable SESSION_COOKIE_SECURE in production.")
        if not getattr(settings, "CSRF_COOKIE_SECURE", False):
            issues.append("Enable CSRF_COOKIE_SECURE in production.")
    return issues


class Command(BaseCommand):
    help = "Check PayPal settings; optionally authenticate and inspect the registered webhook. No payments are created."

    def add_arguments(self, parser):
        parser.add_argument("--production", action="store_true", help="Require live mode and secure public hosting settings.")
        parser.add_argument("--connect", action="store_true", help="Authenticate and read the configured webhook from PayPal.")
        parser.add_argument("--authenticate-only", action="store_true", help="Check API credentials without requiring or inspecting a webhook.")

    def handle(self, *args, **options):
        if options["connect"] and options["authenticate_only"]:
            raise CommandError("Choose either --connect or --authenticate-only.")
        issues = configuration_issues(options["production"], require_webhook=not options["authenticate_only"])
        if issues:
            for issue in issues:
                self.stderr.write("- " + issue)
            raise CommandError("PayPal configuration is incomplete. Values and secrets were not printed.")
        self.stdout.write("PayPal configuration checks passed.")
        if not options["connect"] and not options["authenticate_only"]:
            self.stdout.write("Use --connect to verify credentials and webhook registration without creating a payment.")
            return
        try:
            # The secret stays server-side; the token is never included in output.
            paypal_api._access_token()
            if options["authenticate_only"]:
                self.stdout.write(self.style.SUCCESS(f"PayPal OAuth authentication verified for {settings.PAYPAL_ENV}. No order was created and no payment was charged."))
                return
            webhook = paypal_api._request("GET", "/v1/notifications/webhooks/" + settings.PAYPAL_WEBHOOK_ID)
        except (paypal_api.PayPalError, requests.RequestException) as exc:
            status = getattr(exc, "status_code", None)
            suffix = f" (HTTP {status})" if status else ""
            raise CommandError(f"PayPal authentication or webhook lookup failed: {type(exc).__name__}{suffix}. No credentials were printed.") from None
        expected_url = settings.SITE_URL.rstrip("/") + "/payments/webhooks/paypal/"
        if webhook.get("url") != expected_url:
            raise CommandError("The configured PayPal webhook URL does not match SITE_URL + /payments/webhooks/paypal/.")
        events = webhook.get("event_types")
        registered = {event.get("name") for event in events if isinstance(event, dict)} if isinstance(events, list) else set()
        missing = REQUIRED_EVENTS - registered
        if missing and "*" not in registered:
            raise CommandError("Missing webhook subscriptions: " + ", ".join(sorted(missing)))
        self.stdout.write(self.style.SUCCESS("PayPal authentication and webhook registration verified. No order was created and no payment was charged."))
