import io

from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.core import mail
from django.core.management import call_command
from django.test import RequestFactory
from django.urls import reverse

from core.testing import PASSWORD, BaseTestCase
from core.legal import CURRENT_VERSIONS

User = get_user_model()


class RegistrationTests(BaseTestCase):
    def _payload(self, **overrides):
        data = {
            "first_name": "Maria",
            "last_name": "Santos",
            "email": "Maria@Example.com",
            "phone_number": "",
            "school": "UP Diliman",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "accept_privacy": "on",
            "accept_license": "on",
            "privacy_version": CURRENT_VERSIONS["privacy"],
            "license_version": CURRENT_VERSIONS["license"],
        }
        data.update(overrides)
        return data

    def test_register_creates_pending_customer_then_verifies_and_signs_in(self):
        response = self.client.post(reverse("accounts:register"), self._payload())
        self.assertRedirects(response, reverse("accounts:verification_sent"))
        user = User.objects.get(email="maria@example.com")
        self.assertEqual(user.email, "maria@example.com")  # normalised
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_active)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(self.complete_registration(), reverse("accounts:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_email_is_required(self):
        response = self.client.post(reverse("accounts:register"), self._payload(email=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_email_must_be_unique_case_insensitive(self):
        self.make_user("existing", email="maria@example.com")
        response = self.client.post(reverse("accounts:register"), self._payload(email="MARIA@example.com"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_register_ignores_external_next(self):
        response = self.client.post(reverse("accounts:register") + "?next=https://evil.example/", self._payload())
        self.assertRedirects(response, reverse("accounts:verification_sent"))
        self.assertNotIn("verified_signup_next", self.client.session)
        self.assertRedirects(self.complete_registration(), reverse("accounts:dashboard"))


class LoginTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user("bob")

    def test_legacy_username_login_is_rejected(self):
        response = self.client.post(reverse("accounts:login"), {"username": "bob", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        request = RequestFactory().post(reverse("accounts:login"))
        self.assertIsNone(authenticate(request, username="bob", password=PASSWORD))

    def test_login_with_email(self):
        response = self.client.post(reverse("accounts:login"), {"email": "BOB@example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_wrong_password_is_rejected(self):
        response = self.client.post(reverse("accounts:login"), {"email": "bob@example.com", "password": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_repeated_failures_lock_the_account(self):
        for _ in range(5):
            self.client.post(reverse("accounts:login"), {"email": "bob@example.com", "password": "wrong"})
        response = self.client.post(reverse("accounts:login"), {"email": "bob@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_password_reset_sends_email(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "bob@example.com"})
        from accounts.email_security import deliver_auth_emails
        deliver_auth_emails()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/account/password-reset/", mail.outbox[0].body)
        self.assertIn("Sign-in email: bob@example.com", mail.outbox[0].body)
        self.assertNotIn("username", mail.outbox[0].body.lower())

    def test_login_and_registration_only_render_email_identifier(self):
        for name in ("accounts:login", "accounts:register"):
            response = self.client.get(reverse(name))
            self.assertContains(response, 'name="email"')
            self.assertNotContains(response, 'name="username"')
            self.assertNotContains(response, "Email or username")

    def test_inactive_account_cannot_sign_in(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(reverse("accounts:login"), {"email": self.user.email, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_django_admin_signs_in_with_email(self):
        admin = User.objects.create_superuser(email="ADMIN@Example.com", password=PASSWORD)
        response = self.client.post(reverse("admin:login"), {
            # Django's built-in form retains this internal field name; it accepts email only.
            "username": admin.email, "password": PASSWORD, "next": reverse("admin:index"),
        })
        self.assertRedirects(response, reverse("admin:index"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), admin.pk)

    def test_django_admin_lockout_applies_to_email(self):
        admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        for email in ("admin@example.com", "ADMIN@example.com", "Admin@Example.com", "admin@EXAMPLE.com", "ADMIN@EXAMPLE.COM"):
            self.client.post(reverse("admin:login"), {"username": email, "password": "wrong"})
        response = self.client.post(reverse("admin:login"), {"username": admin.email, "password": PASSWORD})
        self.assertEqual(response.status_code, 429)


class CustomerAreaTests(BaseTestCase):
    def test_customer_pages_require_login(self):
        for name in ("accounts:dashboard", "accounts:profile", "accounts:password_change", "orders:list"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("accounts:login"), response["Location"])

    def test_profile_update(self):
        user = self.make_user("carla")
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:profile"),
            {"first_name": "Carla", "last_name": "Reyes", "email": "carla@example.com",
             "phone_number": "+63 917 123 4567", "school": "PUP"},
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        user.refresh_from_db()
        self.assertEqual(user.school, "PUP")

    def test_changed_email_becomes_the_login_identifier(self):
        user = self.make_user("change-email")
        self.client.force_login(user)
        self.client.post(reverse("accounts:profile"), {
            "email": " NEW-EMAIL@example.com ", "first_name": "Email", "last_name": "Customer",
            "phone_number": "", "school": "",
        })
        user.refresh_from_db()
        self.assertEqual(user.email, "new-email@example.com")
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"email": user.email, "password": PASSWORD})
        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.client.logout()
        self.client.post(reverse("accounts:login"), {"email": "change-email@example.com", "password": PASSWORD})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_user_forms_do_not_include_username(self):
        user = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        self.client.force_login(user)
        for url in (reverse("admin:accounts_user_add"), reverse("admin:accounts_user_change", args=[user.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'name="email"')
            self.assertNotContains(response, 'name="username"')

    def test_admin_can_create_an_email_only_account(self):
        admin = User.objects.create_superuser("admin@example.com", PASSWORD)
        self.client.force_login(admin)
        response = self.client.post(reverse("admin:accounts_user_add"), {
            "email": "NEW-CUSTOMER@example.com", "usable_password": "true",
            "password1": PASSWORD, "password2": PASSWORD, "first_name": "New", "last_name": "Customer",
            "phone_number": "", "school": "", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(email="new-customer@example.com").check_password(PASSWORD))


class EmailUserManagerTests(BaseTestCase):
    def test_user_model_has_no_username_field(self):
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(User.REQUIRED_FIELDS, [])
        with self.assertRaises(FieldDoesNotExist):
            User._meta.get_field("username")

    def test_manager_creates_users_using_only_email_and_password(self):
        user = User.objects.create_user(" USER@Example.COM ", PASSWORD)
        self.assertEqual(user.email, "user@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff)
        self.assertEqual(User.objects.get_by_natural_key("USER@EXAMPLE.COM"), user)
        self.assertEqual(user.get_username(), user.email)

    def test_email_is_required_by_manager(self):
        for email in ("", "  ", None):
            with self.subTest(email=email), self.assertRaises(ValueError):
                User.objects.create_user(email, PASSWORD)

    def test_superuser_requires_staff_and_superuser_flags(self):
        for flags in ({"is_staff": False}, {"is_superuser": False}):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                User.objects.create_superuser("admin@example.com", PASSWORD, **flags)

    def test_createsuperuser_command_requires_only_email(self):
        call_command("createsuperuser", email="owner@example.com", interactive=False, stdout=io.StringIO())
        user = User.objects.get(email="owner@example.com")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
