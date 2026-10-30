from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import Client, override_settings
from django.urls import reverse

from core.models import SiteSettings
from core.testing import PASSWORD, BaseTestCase


NEW_PASSWORD = "Cedar-river-2026!"


class AccountSettingsTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_user("customer")
        self.staff = self.make_user("owner", staff=True, school="Existing university")
        self.other = self.make_user("other")

    def profile_data(self, user, **overrides):
        data = {"action": "profile", "first_name": "Updated", "last_name": "Name",
                "email": user.email, "phone_number": "+63 917 123 4567", "school": "PUP"}
        data.update(overrides)
        return data

    def password_data(self, **overrides):
        data = {"action": "password", "old_password": PASSWORD,
                "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        data.update(overrides)
        return data

    def roles(self):
        return ((self.customer, "accounts:settings"), (self.staff, "dashboard:settings"))

    def test_settings_require_login(self):
        for _, name in self.roles():
            for method in (self.client.get, self.client.post):
                response = method(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("accounts:login"), response["Location"])

    def test_customer_sees_account_forms_and_settings_navigation(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("accounts:settings"))
        self.assertContains(response, "Account settings")
        self.assertContains(response, 'name="action" value="profile"')
        self.assertContains(response, 'name="action" value="password"')
        self.assertContains(response, 'href="/account/settings/"')
        self.assertNotContains(response, 'name="site_name"')
        self.assertNotContains(response, 'id="manageSidebar"')

    def test_staff_settings_stay_in_workspace(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:settings"))
        self.assertContains(response, 'id="manageSidebar"')
        self.assertContains(response, 'name="site_name"')
        self.assertContains(response, 'name="old_password"')
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'href="/manage/settings/#profile"')
        self.assertNotContains(response, 'aria-label="Main navigation"')

    def test_staff_account_settings_and_old_links_open_workspace(self):
        self.client.force_login(self.staff)
        for source, suffix in (("accounts:settings", ""), ("accounts:profile", "#profile"),
                               ("accounts:password_change", "#security")):
            self.assertRedirects(self.client.get(reverse(source)), reverse("dashboard:settings") + suffix)

    def test_profiles_save_independently_and_cannot_change_permissions_or_other_users(self):
        for user, name in self.roles():
            with self.subTest(role=name):
                self.client.force_login(user)
                response = self.client.post(reverse(name), self.profile_data(
                    user, email=f" UPDATED-{user.pk}@EXAMPLE.COM ",
                    is_staff="on", is_superuser="on", id=self.other.pk,
                    site_name="Unauthorized store change", password="injected-password"))
                self.assertRedirects(response, reverse(name))
                user.refresh_from_db()
                self.assertEqual(user.first_name, "Updated")
                self.assertEqual(user.email, f"updated-{user.pk}@example.com")
                self.assertTrue(user.check_password(PASSWORD))
                self.assertFalse(user.is_superuser)
                self.assertEqual(user.is_staff, name == "dashboard:settings")
                self.assertEqual(user.school, "Existing university" if user.is_staff else "PUP")
                self.assertNotEqual(SiteSettings.load().name, "Unauthorized store change")
                self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.other.refresh_from_db()
        self.assertEqual(self.other.first_name, "Other")

    def test_duplicate_email_and_invalid_phone_leave_profile_unchanged(self):
        for user, name in self.roles():
            for changes, field in (({"email": self.other.email.upper()}, "email"),
                                   ({"phone_number": "not a phone"}, "phone_number")):
                with self.subTest(role=name, field=field):
                    self.client.force_login(user)
                    response = self.client.post(reverse(name), self.profile_data(user, **changes))
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(field, response.context["profile_form"].errors)
                    self.assertFalse(response.context["password_form"].is_bound)
                    user.refresh_from_db()
                    self.assertEqual(user.first_name, "Owner" if user.is_staff else "Customer")

    def test_password_change_keeps_current_session_invalidates_other_session_and_replaces_login(self):
        for user, name in self.roles():
            with self.subTest(role=name):
                self.client.force_login(user)
                other_device = Client()
                other_device.force_login(user)
                response = self.client.post(reverse(name), self.password_data())
                self.assertRedirects(response, reverse(name))
                user.refresh_from_db()
                self.assertTrue(user.check_password(NEW_PASSWORD))
                self.assertFalse(user.check_password(PASSWORD))
                self.assertNotEqual(user.password, NEW_PASSWORD)
                self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
                self.assertEqual(other_device.get(reverse(name)).status_code, 302)
                self.client.logout()
                response = self.client.post(reverse("accounts:login"), {
                    "email": user.email, "password": NEW_PASSWORD,
                })
                self.assertEqual(response.status_code, 302)
                self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_password_validation_rejects_wrong_current_mismatch_weak_and_missing_passwords(self):
        invalid = ({"old_password": "wrong"}, {"new_password2": "Different-password!"},
                   {"new_password1": "12345678", "new_password2": "12345678"}, {"old_password": ""})
        for user, name in self.roles():
            for changes in invalid:
                with self.subTest(role=name, changes=changes):
                    self.client.force_login(user)
                    response = self.client.post(reverse(name), self.password_data(**changes))
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.context["password_form"].errors)
                    self.assertFalse(response.context["profile_form"].is_bound)
                    self.assertNotContains(response, 'value="wrong"')
                    user.refresh_from_db()
                    self.assertTrue(user.check_password(PASSWORD))

    def test_customer_cannot_edit_store_or_staff_account(self):
        self.client.force_login(self.customer)
        original = SiteSettings.load().name
        self.assertEqual(self.client.post(reverse("dashboard:settings"), {
            "action": "store", "site_name": "Hijacked",
        }).status_code, 403)
        self.assertEqual(self.client.post(reverse("accounts:settings"), {
            "action": "store", "site_name": "Hijacked",
        }).status_code, 400)
        self.assertEqual(SiteSettings.load().name, original)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.first_name, "Owner")

    def test_settings_require_csrf_and_reject_unknown_actions(self):
        for user, name in self.roles():
            self.client.force_login(user)
            csrf_client = Client(enforce_csrf_checks=True)
            csrf_client.force_login(user)
            self.assertEqual(csrf_client.post(reverse(name), self.profile_data(user)).status_code, 403)
            self.assertEqual(csrf_client.post(reverse(name), self.password_data()).status_code, 403)
            self.assertEqual(self.client.post(reverse(name), {"action": "unknown"}).status_code, 400)

    def test_store_name_change_is_visible_to_customers_and_does_not_change_account(self):
        self.client.force_login(self.staff)
        site = SiteSettings.load()
        site.site_name = "Faintedbrain Digital Store"
        site.save()
        response = self.client.post(reverse("dashboard:settings"), {
            "action": "store", "site_name": "CodehubPh", "tagline": site.tagline,
            "contact_email": site.contact_email, "contact_phone": "", "paypal_me_url": "",
            "gcash_account_name": "", "gcash_number": "", "payment_instructions": site.payment_instructions,
        })
        self.assertRedirects(response, reverse("dashboard:settings"))
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.first_name, "Owner")
        self.assertTrue(self.staff.check_password(PASSWORD))
        self.client.logout()
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "CodehubPh")
        self.assertNotContains(response, "Faintedbrain Digital Store")

    def test_advanced_admin_branding_uses_saved_store_name(self):
        site = SiteSettings.load()
        site.site_name = "Saved store name"
        site.save()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Saved store name — Django admin")
        self.assertContains(response, "| Saved store name</title>")
        self.assertContains(response, 'href="/manage/settings/"')


class StoreNameMigrationTests(BaseTestCase):
    def run_rename(self):
        migration = import_module("core.migrations.0004_codehubph_store_name")
        migration.rename_store(apps, SimpleNamespace(connection=connection))

    def test_renames_previous_brand_case_insensitively(self):
        site = SiteSettings.load()
        site.site_name = "Faintedbrain Digital Store"
        site.save()
        self.run_rename()
        self.assertEqual(SiteSettings.load().name, "CodehubPh")

    @override_settings(SITE_NAME="FaintedBrain Digital Store")
    def test_previous_environment_name_becomes_editable_store_name(self):
        self.run_rename()
        self.assertEqual(SiteSettings.load().site_name, "CodehubPh")
        SiteSettings.objects.filter(pk=1).update(site_name="")
        self.run_rename()
        self.assertEqual(SiteSettings.load().site_name, "CodehubPh")

    @override_settings(SITE_NAME="FaintedBrain Digital Store")
    def test_preserves_custom_store_name_and_other_settings(self):
        site = SiteSettings.load()
        site.site_name = "Custom Store"
        site.contact_email = "custom@example.com"
        site.save()
        self.run_rename()
        site.refresh_from_db()
        self.assertEqual(site.name, "Custom Store")
        self.assertEqual(site.contact_email, "custom@example.com")

    @override_settings(SITE_NAME="Custom environment store")
    def test_preserves_custom_environment_name(self):
        self.run_rename()
        self.assertEqual(SiteSettings.load().name, "Custom environment store")
