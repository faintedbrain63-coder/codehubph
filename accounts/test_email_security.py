import re
import os
import shutil
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.email_security import deliver_auth_emails, queue_auth_email, verification_path, verification_token
from accounts.models import AuthEmailJob, AuthEmailRateLimit
from accounts.test_purchase_onboarding import registration
from core.testing import BaseTestCase, PASSWORD

User = get_user_model()


@override_settings(SITE_URL="https://codehubph.tech", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountEmailSecurityTests(BaseTestCase):
    def pending(self, **overrides):
        return self.make_user("pending", is_active=False, email_verification_required=True, **overrides)

    def test_signup_queues_email_without_authenticating_or_sending_in_request(self):
        response = self.client.post(reverse("accounts:register"), registration())
        self.assertRedirects(response, reverse("accounts:verification_sent"))
        user = User.objects.get(email="maria@example.com")
        self.assertFalse(user.is_active)
        self.assertTrue(user.email_verification_required)
        self.assertIsNone(user.email_verified_at)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(AuthEmailJob.objects.get().purpose, "verify")
        self.assertEqual(len(mail.outbox), 0)
        self.client.post(reverse("accounts:login"), {"email": user.email, "password": PASSWORD})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signup_dispatches_its_job_only_after_transaction_commits(self):
        with patch("accounts.email_security.dispatch_auth_email") as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("accounts:register"), registration())
                self.assertEqual(response.status_code, 302)
                dispatch.assert_not_called()
            dispatch.assert_called_once_with(AuthEmailJob.objects.get().pk)

    @override_settings(AUTH_EMAIL_DELIVERY_MODE="worker")
    def test_worker_only_mode_does_not_schedule_in_process_delivery(self):
        with patch("accounts.email_security.dispatch_auth_email") as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse("accounts:register"), registration())
            dispatch.assert_not_called()

    def test_scoped_delivery_never_drains_another_customers_job(self):
        first = queue_auth_email(self.pending(), "verify")
        other = self.make_user("other-email", is_active=False, email_verification_required=True)
        second = queue_auth_email(other, "verify")
        deliver_auth_emails(limit=1, job_id=second.pk)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, "pending")
        self.assertEqual(second.status, "sent")
        self.assertEqual(mail.outbox[0].to, [other.email])

    def test_active_flag_alone_cannot_bypass_verification(self):
        user = self.make_user("unverified-active", email_verification_required=True)
        self.client.post(reverse("accounts:login"), {"email": user.email, "password": PASSWORD})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_rate_limit_does_not_create_unbounded_address_keys(self):
        with override_settings(AUTH_EMAIL_PER_IP=2):
            for number in range(10):
                self.client.post(reverse("accounts:password_reset"), {"email": f"unknown-{number}@example.com"})
        self.assertEqual(AuthEmailRateLimit.objects.count(), 3)

    def test_verification_email_has_trusted_origin_and_html_and_text(self):
        user = self.pending()
        queue_auth_email(user, "verify")
        self.assertEqual(deliver_auth_emails(), 1)
        self.assertEqual(AuthEmailJob.objects.get().status, "sent")
        message = mail.outbox[0]
        self.assertEqual(message.to, [user.email])
        self.assertIn("https://codehubph.tech/account/verify-email/", message.body)
        self.assertIn("1440 minutes", message.body)
        self.assertEqual(message.alternatives[0].mimetype, "text/html")

    def test_scanner_get_does_not_activate_and_post_consumes_link(self):
        user = self.pending()
        path = verification_path(user)
        response = self.client.get(path)
        self.assertContains(response, "Verify and activate account")
        self.assertEqual(response["Referrer-Policy"], "origin")
        self.assertIn("no-store", response["Cache-Control"])
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertRedirects(self.client.post(path), reverse("accounts:login"))
        user.refresh_from_db()
        verified_at = user.email_verified_at
        self.assertTrue(user.is_active)
        self.assertIsNotNone(verified_at)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.post(path), "This link is no longer valid")
        user.refresh_from_db()
        self.assertEqual(user.email_verified_at, verified_at)
        self.assertRedirects(self.client.post(reverse("accounts:login"), {"email": user.email, "password": PASSWORD}), reverse("accounts:dashboard"))

    def test_confirmation_requires_csrf(self):
        user = self.pending()
        self.assertEqual(Client(enforce_csrf_checks=True).post(verification_path(user)).status_code, 403)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_expired_tampered_and_wrong_account_links_do_not_activate(self):
        user = self.pending()
        path = verification_path(user)
        with patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + 86402):
            self.assertContains(self.client.post(path), "This link is no longer valid")
        tampered = path[:-2] + ("x" if path[-2] != "x" else "y") + "/"
        self.assertContains(self.client.post(tampered), "This link is no longer valid")
        other = self.make_user("other-pending", is_active=False, email_verification_required=True)
        wrong = reverse("accounts:verify_email", kwargs={"uidb64": urlsafe_base64_encode(force_bytes(other.pk)), "token": verification_token(user)})
        self.assertContains(self.client.post(wrong), "This link is no longer valid")
        user.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(other.is_active)

    def test_changed_email_invalidates_verification(self):
        user = self.pending()
        path = verification_path(user)
        User.objects.filter(pk=user.pk).update(email="changed@example.com")
        self.assertContains(self.client.post(path), "This link is no longer valid")

    def test_disabled_legacy_accounts_cannot_be_activated(self):
        user = self.make_user("disabled", is_active=False)
        self.assertContains(self.client.post(verification_path(user)), "This link is no longer valid")
        self.client.post(reverse("accounts:resend_verification"), {"email": user.email})
        self.assertFalse(AuthEmailJob.objects.exists())

    def test_resend_generic_response_and_shared_address_limit(self):
        user = self.pending()
        for _ in range(5):
            response = self.client.post(reverse("accounts:resend_verification"), {"email": user.email.upper()})
            self.assertRedirects(response, reverse("accounts:verification_sent"))
        self.assertEqual(AuthEmailJob.objects.count(), 3)
        unknown = self.client.post(reverse("accounts:resend_verification"), {"email": "unknown@example.com"})
        self.assertEqual(unknown["Location"], response["Location"])
        self.assertTrue(all(user.email not in bucket.key for bucket in AuthEmailRateLimit.objects.all()))

    def test_ip_limit_covers_different_email_addresses(self):
        with override_settings(AUTH_EMAIL_PER_IP=2):
            for i in range(3):
                user = self.make_user(f"pending-{i}", is_active=False, email_verification_required=True)
                self.client.post(reverse("accounts:resend_verification"), {"email": user.email})
        self.assertEqual(AuthEmailJob.objects.count(), 2)

    def test_rate_budget_recovers_after_window(self):
        user = self.pending()
        for _ in range(3):
            self.client.post(reverse("accounts:resend_verification"), {"email": user.email})
        AuthEmailRateLimit.objects.update(started_at=timezone.now() - timedelta(minutes=16))
        self.client.post(reverse("accounts:resend_verification"), {"email": user.email})
        self.assertEqual(AuthEmailJob.objects.count(), 4)

    def test_password_reset_queues_only_active_eligible_accounts_and_is_generic(self):
        user = self.make_user()
        pending = self.pending()
        inactive = self.make_user("inactive", is_active=False)
        unusable = self.make_user("unusable")
        unusable.set_unusable_password()
        unusable.save()
        for email in (user.email, pending.email, inactive.email, unusable.email, "unknown@example.com"):
            response = self.client.post(reverse("accounts:password_reset"), {"email": email})
            self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(AuthEmailJob.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        deliver_auth_emails()
        self.assertIn("60 minutes", mail.outbox[0].body)
        self.assertIn("https://codehubph.tech/account/password-reset/", mail.outbox[0].body)

    def test_reset_changes_password_invalidates_sessions_and_rejects_replay(self):
        user = self.make_user()
        old_session = Client()
        old_session.force_login(user)
        self.client.post(reverse("accounts:password_reset"), {"email": user.email})
        deliver_auth_emails()
        link = re.search(r"https://[^\s]+/password-reset/[^\s]+", mail.outbox[0].body).group()
        path = urlsplit(link).path
        response = self.client.get(path)
        self.assertEqual(response.status_code, 302)
        form_path = response["Location"]
        self.assertIn("set-password", form_path)
        self.assertNotIn(default_token_generator.make_token(user), form_path)
        new_password = "N3w-secure-pass-2026!"
        response = self.client.post(form_path, {"new_password1": new_password, "new_password2": new_password})
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(old_session.get(reverse("accounts:dashboard")).status_code, 302)
        self.assertContains(self.client.get(path), "This link is no longer valid")

    def test_expired_reset_and_disabled_account_are_rejected(self):
        user = self.make_user()
        path = reverse("accounts:password_reset_confirm", kwargs={"uidb64": urlsafe_base64_encode(force_bytes(user.pk)), "token": default_token_generator.make_token(user)})
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            self.assertContains(self.client.get(path), "This link is no longer valid")
        user.is_active = False
        user.save()
        self.assertContains(self.client.get(path), "This link is no longer valid")

    def test_password_validation_and_csrf_remain_enforced(self):
        user = self.make_user()
        path = reverse("accounts:password_reset_confirm", kwargs={"uidb64": urlsafe_base64_encode(force_bytes(user.pk)), "token": default_token_generator.make_token(user)})
        redirect = self.client.get(path)["Location"]
        self.assertEqual(self.client.post(redirect, {"new_password1": "123", "new_password2": "123"}).status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse("accounts:password_reset"), {"email": user.email}).status_code, 403)

    def test_delivery_failure_retries_without_exposing_exception_message(self):
        user = self.pending()
        job = queue_auth_email(user, "verify")
        with patch("accounts.email_security.EmailMultiAlternatives.send", side_effect=ConnectionError("private-token-password")):
            self.assertEqual(deliver_auth_emails(), 0)
        job.refresh_from_db()
        self.assertEqual(job.status, "pending")
        self.assertEqual(job.error_code, "ConnectionError")
        self.assertEqual(job.attempts, 1)
        self.assertGreater(job.available_at, timezone.now())
        AuthEmailJob.objects.filter(pk=job.pk).update(available_at=timezone.now())
        self.assertEqual(deliver_auth_emails(), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, "sent")

    def test_worker_cancels_stale_password_or_email_jobs(self):
        user = self.make_user()
        job = queue_auth_email(user, "reset")
        user.set_password("Changed-after-request-2026!")
        user.save()
        self.assertEqual(deliver_auth_emails(), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, "cancelled")
        self.assertEqual(len(mail.outbox), 0)

    def test_worker_recovers_abandoned_job_and_limits_retries(self):
        user = self.pending()
        job = queue_auth_email(user, "verify")
        AuthEmailJob.objects.filter(pk=job.pk).update(status="sending", attempted_at=timezone.now() - timedelta(minutes=6), attempts=5)
        with patch("accounts.email_security.EmailMultiAlternatives.send", side_effect=ConnectionError()):
            deliver_auth_emails()
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.attempts, 6)

    def test_invalid_canonical_origin_fails_closed(self):
        queue_auth_email(self.pending(), "verify")
        with override_settings(DEBUG=False, SITE_URL="http://untrusted.example"):
            deliver_auth_emails()
        self.assertEqual(AuthEmailJob.objects.get().error_code, "ImproperlyConfigured")
        self.assertEqual(len(mail.outbox), 0)

    def test_verified_signup_preserves_safe_next_without_automatic_login(self):
        self.client.post(reverse("accounts:register"), registration(next="/projects/request/"))
        user = User.objects.get(email="maria@example.com")
        response = self.client.post(verification_path(user))
        self.assertEqual(response["Location"], reverse("accounts:login") + "?next=%2Fprojects%2Frequest%2F")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_verified_address_cannot_be_changed_with_profile_payload(self):
        user = self.make_user(email_verification_required=True, email_verified_at=timezone.now())
        self.client.force_login(user)
        self.client.post(reverse("accounts:profile"), {"first_name": "Alice", "last_name": "", "email": "unverified@example.com", "phone_number": "", "school": ""})
        user.refresh_from_db()
        self.assertEqual(user.email, "alice@example.com")

    def test_malformed_ids_are_safe(self):
        for uid in ("invalid", urlsafe_base64_encode(b"9" * 100), urlsafe_base64_encode(b"-1")):
            for name in ("accounts:verify_email", "accounts:password_reset_confirm"):
                self.assertEqual(self.client.get(reverse(name, kwargs={"uidb64": uid, "token": "invalid"})).status_code, 200)

    def test_account_security_pages_render_and_optional_previews(self):
        user = self.pending()
        active = self.make_user("recovery")
        reset = reverse("accounts:password_reset_confirm", kwargs={"uidb64": urlsafe_base64_encode(force_bytes(active.pk)), "token": default_token_generator.make_token(active)})
        reset_form = self.client.get(reset)["Location"]
        pages = {
            "auth-register": reverse("accounts:register"), "auth-login": reverse("accounts:login"),
            "auth-verification-sent": reverse("accounts:verification_sent"),
            "auth-verify": verification_path(user), "auth-resend": reverse("accounts:resend_verification"),
            "auth-verify-invalid": reverse("accounts:verify_email", kwargs={"uidb64": "invalid", "token": "invalid"}),
            "auth-reset-form": reverse("accounts:password_reset"), "auth-reset-confirm": reset_form,
            "auth-reset-sent": reverse("accounts:password_reset_done"), "auth-reset-complete": reverse("accounts:password_reset_complete"),
        }
        preview = os.environ.get("CODEHUB_RENDER_ACCOUNTS") == "1"
        root = Path(settings.BASE_DIR) / ".qa/site"
        if preview:
            (root / "previews").mkdir(parents=True, exist_ok=True)
            shutil.copytree(Path(settings.BASE_DIR) / "static", root / "static", dirs_exist_ok=True)
        for name, path in pages.items():
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, name)
            self.assertNotContains(response, "adsbygoogle")
            if preview:
                (root / "previews" / f"{name}.html").write_bytes(response.content)
        queue_auth_email(user, "verify")
        deliver_auth_emails()
        if preview:
            (root / "previews/auth-email.html").write_text(mail.outbox[0].alternatives[0].content, encoding="utf-8")
