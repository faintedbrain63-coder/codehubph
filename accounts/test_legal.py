from html.parser import HTMLParser
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from accounts.forms import RegisterForm
from core.legal import CURRENT_VERSIONS, DOCUMENTS, get_document
from core.testing import PASSWORD, BaseTestCase

User = get_user_model()


class InputParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            attributes = dict(attrs)
            self.fields[attributes.get("name")] = attributes


class RegistrationAgreementTests(BaseTestCase):
    def payload(self, **overrides):
        data = {
            "first_name": "Maria", "last_name": "Santos", "email": "maria@example.com",
            "phone_number": "", "school": "", "password1": PASSWORD, "password2": PASSWORD,
            "accept_privacy": "on", "accept_license": "on",
            "privacy_version": CURRENT_VERSIONS["privacy"], "license_version": CURRENT_VERSIONS["license"],
        }
        data.update(overrides)
        return data

    def test_both_checkboxes_are_required_and_initially_unchecked(self):
        response = self.client.get(reverse("accounts:register"))
        parser = InputParser()
        parser.feed(response.content.decode())
        for field in ("accept_privacy", "accept_license"):
            self.assertEqual(parser.fields[field]["type"], "checkbox")
            self.assertIn("required", parser.fields[field])
            self.assertNotIn("checked", parser.fields[field])
        for kind in ("privacy", "license"):
            self.assertContains(response, get_document(kind)["url"])
            self.assertContains(response, f'data-bs-target="#legal-{kind}"')
            self.assertContains(response, get_document(kind)["title"])
            self.assertEqual(parser.fields[f"{kind}_version"]["value"], CURRENT_VERSIONS[kind])
        self.assertNotContains(response, "opens in a new tab")

    def test_registration_is_rejected_without_either_agreement(self):
        data = self.payload()
        del data["accept_privacy"]
        del data["accept_license"]
        response = self.client.post(reverse("accounts:register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("accept_privacy", response.context["form"].errors)
        self.assertIn("accept_license", response.context["form"].errors)
        self.assertFalse(User.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_either_missing_or_false_checkbox_prevents_signup(self):
        for field in ("accept_privacy", "accept_license"):
            for value in (None, "false", ""):
                with self.subTest(field=field, value=value):
                    data = self.payload()
                    if value is None:
                        del data[field]
                    else:
                        data[field] = value
                    response = self.client.post(reverse("accounts:register"), data)
                    self.assertIn(field, response.context["form"].errors)
                    self.assertFalse(User.objects.exists())

    def test_success_stores_server_time_and_versions_before_verification(self):
        start = timezone.now()
        response = self.client.post(reverse("accounts:register"), self.payload(
            legal_accepted_at="1999-01-01T00:00:00Z", privacy_policy_version="forged", license_agreement_version="forged",
        ))
        self.assertRedirects(response, reverse("accounts:verification_sent"))
        user = User.objects.get()
        self.assertGreaterEqual(user.legal_accepted_at, start)
        self.assertLessEqual(user.legal_accepted_at, timezone.now())
        self.assertEqual(user.privacy_policy_version, CURRENT_VERSIONS["privacy"])
        self.assertEqual(user.license_agreement_version, CURRENT_VERSIONS["license"])
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(user.is_active)

    def test_missing_or_tampered_policy_versions_are_rejected(self):
        for field in ("privacy_version", "license_version"):
            for value in (None, "1999-01-01", "future"):
                with self.subTest(field=field, value=value):
                    data = self.payload()
                    if value is None:
                        del data[field]
                    else:
                        data[field] = value
                    response = self.client.post(reverse("accounts:register"), data)
                    self.assertContains(response, "Reload the page")
                    self.assertFalse(User.objects.exists())

    def test_changed_policy_requires_a_fresh_review(self):
        data = self.payload()
        replacement = {**DOCUMENTS["license"][CURRENT_VERSIONS["license"]]}
        with mock.patch.dict(DOCUMENTS["license"], {"2026-11-01": replacement}), mock.patch.dict(
            CURRENT_VERSIONS, {"license": "2026-11-01"}
        ):
            response = self.client.post(reverse("accounts:register"), data)
            self.assertContains(response, "Reload the page")
            self.assertFalse(User.objects.exists())

    def test_failed_signup_does_not_create_an_acceptance_record(self):
        response = self.client.post(reverse("accounts:register"), self.payload(password2="mismatch"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_existing_and_staff_created_accounts_are_not_marked_as_accepting(self):
        user = self.make_user()
        self.assertIsNone(user.legal_accepted_at)
        self.assertEqual(user.privacy_policy_version, "")
        self.assertEqual(user.license_agreement_version, "")
        self.client.force_login(user)
        self.client.post(reverse("accounts:profile"), {
            "email": user.email, "first_name": "Alice", "last_name": "", "phone_number": "", "school": "",
            "legal_accepted_at": "2026-10-23T00:00:00Z", "privacy_policy_version": "forged",
        })
        user.refresh_from_db()
        self.assertIsNone(user.legal_accepted_at)
        self.assertEqual(user.privacy_policy_version, "")

    def test_form_save_without_commit_prepares_acceptance_without_creating_user(self):
        form = RegisterForm(self.payload())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save(commit=False)
        self.assertIsNotNone(user.legal_accepted_at)
        self.assertEqual(user.privacy_policy_version, CURRENT_VERSIONS["privacy"])
        self.assertFalse(User.objects.exists())


class LegalDocumentTests(BaseTestCase):
    def test_custom_service_policies_replace_current_registration_documents(self):
        response = self.client.get(reverse("accounts:register"))
        body = " ".join(strip_tags(response.content.decode()).split()).lower()
        for text in ("2026-10-24", "full-stack development", "Google AdSense", "copyright is retained",
                     "Client indemnity", "Portfolio projects and public testimonials", "publication permission"):
            self.assertIn(text.lower(), body)
        for kind in ("privacy", "license"):
            self.assertContains(response, get_document(kind)["url"])

    def test_previous_policy_bodies_and_existing_acceptances_are_preserved(self):
        user = self.make_user("existing-legal-customer", privacy_policy_version="2026-10-23",
                              license_agreement_version="2026-10-23", legal_accepted_at=timezone.now())
        accepted_at = user.legal_accepted_at
        self.assertContains(self.client.get(reverse("core:legal_document", args=["license", "2026-10-23"])),
                            "Our additional store promise")
        self.assertNotContains(self.client.get(reverse("core:license")), "Our additional store promise")
        self.assertContains(self.client.get(reverse("core:legal_document", args=["privacy", "2026-10-23"])),
                            "buy digital products")
        user.refresh_from_db()
        self.assertEqual(user.privacy_policy_version, "2026-10-23")
        self.assertEqual(user.license_agreement_version, "2026-10-23")
        self.assertEqual(user.legal_accepted_at, accepted_at)

    def test_public_and_versioned_documents_are_available_without_login(self):
        for kind, title in (("privacy", "Privacy Policy"), ("license", "Software License Agreement")):
            for url in (reverse(f"core:{kind}"), get_document(kind)["url"]):
                response = self.client.get(url)
                self.assertContains(response, title)
                self.assertContains(response, CURRENT_VERSIONS[kind])
        self.assertContains(self.client.get(reverse("core:terms")), "Software License Agreement")

    def test_unpublished_or_unknown_document_versions_are_not_served(self):
        for kind, version in (("privacy", "1999-01-01"), ("unknown", "2026-10-23")):
            self.assertEqual(self.client.get(reverse("core:legal_document", args=[kind, version])).status_code, 404)

    @override_settings(LEGAL_OWNER_NAME="Example Owner", LEGAL_CONTACT_ADDRESS="Example City, Philippines",
                       PRIVACY_CONTACT_EMAIL="privacy@example.org")
    def test_operator_and_privacy_contact_are_configurable(self):
        response = self.client.get(reverse("core:privacy"))
        self.assertContains(response, "Example Owner")
        self.assertContains(response, "Example City, Philippines")
        self.assertContains(response, "privacy@example.org")

    def test_published_versions_remain_accessible_after_a_revision(self):
        old = CURRENT_VERSIONS["license"]
        replacement = {**DOCUMENTS["license"][old]}
        with mock.patch.dict(DOCUMENTS["license"], {"2026-11-01": replacement}), mock.patch.dict(
            CURRENT_VERSIONS, {"license": "2026-11-01"}
        ):
            response = self.client.get(reverse("core:legal_document", args=["license", old]))
            self.assertContains(response, f"Version {old}")
            self.assertContains(self.client.get(reverse("core:license")), "Version 2026-11-01")
