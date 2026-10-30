from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.urls import reverse

from accounts.backends import EmailBackend
from capstone.models import CapstoneMessage, CapstoneRequest
from core.models import ContactMessage
from core.testing import PASSWORD, BaseTestCase, zip_upload
from orders.models import Order
from payments.models import Payment

User = get_user_model()


class CustomerAdminTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user("owner", staff=True)
        self.customer = self.make_user(
            "shopper", first_name="Mina", last_name="Cruz", school="State University", phone_number="+63 917 000 1111",
        )
        self.client.force_login(self.staff)

    def form(self, **overrides):
        data = {
            "first_name": "Ana",
            "last_name": "Reyes",
            "email": "ana@example.com",
            "phone_number": "+63 917 222 3333",
            "school": "City College",
            "password1": "Customer2026!",
            "password2": "Customer2026!",
            "is_active": "on",
        }
        data.update(overrides)
        return data

    def test_customers_require_staff_and_can_be_searched(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:customer_list"))
        self.assertIn(reverse("accounts:login"), response["Location"])
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("dashboard:customer_list")).status_code, 403)
        self.client.force_login(self.staff)
        page = self.client.get(reverse("dashboard:customer_list"), {"q": "State University"})
        self.assertContains(page, "Mina Cruz")
        self.assertContains(page, "New customer")
        self.assertNotContains(page, self.staff.email)
        phone = self.client.get(reverse("dashboard:customer_list"), {"q": "917 000 1111"})
        self.assertContains(phone, self.customer.email)
        blocked = self.client.get(reverse("dashboard:customer_list"), {"status": "inactive"})
        self.assertNotContains(blocked, self.customer.email)

    def test_staff_can_create_a_customer_who_can_sign_in(self):
        response = self.client.post(reverse("dashboard:customer_create"), self.form())
        self.assertRedirects(response, reverse("dashboard:customer_list"))
        created = User.objects.get(email="ana@example.com")
        self.assertFalse(created.is_staff)
        self.assertTrue(created.is_active)
        self.assertEqual(created.school, "City College")
        self.assertTrue(created.check_password("Customer2026!"))

    def test_create_rejects_a_duplicate_email_and_a_mismatched_password(self):
        duplicate = self.client.post(reverse("dashboard:customer_create"), self.form(email=self.customer.email.upper()))
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, "already exists")
        mismatch = self.client.post(reverse("dashboard:customer_create"), self.form(password2="Other2026!"))
        self.assertEqual(mismatch.status_code, 200)
        self.assertContains(mismatch, "do not match")
        self.assertFalse(User.objects.filter(email="ana@example.com").exists())

    def test_staff_can_update_a_customer_without_changing_the_password(self):
        response = self.client.post(reverse("dashboard:customer_edit", args=[self.customer.pk]), self.form(
            first_name="Mina", last_name="Santos", email=self.customer.email, password1="", password2="", school="New School",
        ))
        self.assertRedirects(response, reverse("dashboard:customer_list"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.last_name, "Santos")
        self.assertEqual(self.customer.school, "New School")
        self.assertTrue(self.customer.check_password(PASSWORD))

    def test_staff_can_activate_a_customer_whose_verification_email_failed(self):
        pending = self.make_user("pending", is_active=False, email_verification_required=True)
        page = self.client.get(reverse("dashboard:customer_list"), {"status": "inactive"})
        self.assertContains(page, "Awaiting email")
        self.assertContains(page, "Activate")
        response = self.client.post(reverse("dashboard:customer_activate", args=[pending.pk]))
        self.assertRedirects(response, reverse("dashboard:customer_list"))
        pending.refresh_from_db()
        self.assertTrue(pending.is_active)
        self.assertIsNotNone(pending.email_verified_at)
        signed_in = EmailBackend().authenticate(
            RequestFactory().post("/account/login/"), email=pending.email, password=PASSWORD,
        )
        self.assertEqual(signed_in, pending)
        self.client.logout()
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(reverse("dashboard:customer_activate", args=[pending.pk])).status_code, 403)

    def test_staff_accounts_are_not_editable_here(self):
        self.assertEqual(self.client.get(reverse("dashboard:customer_edit", args=[self.staff.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:customer_delete", args=[self.staff.pk])).status_code, 404)

    def test_delete_removes_an_unused_account_and_deactivates_one_with_orders(self):
        unused = self.make_user("unused")
        removed = self.client.post(reverse("dashboard:customer_delete", args=[unused.pk]))
        self.assertRedirects(removed, reverse("dashboard:customer_list"))
        self.assertFalse(User.objects.filter(pk=unused.pk).exists())
        Order.objects.create(user=self.customer, total="100.00")
        kept = self.client.post(reverse("dashboard:customer_delete", args=[self.customer.pk]))
        self.assertRedirects(kept, reverse("dashboard:customer_list"))
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

    def request_for(self, customer, **extra):
        return CapstoneRequest.objects.create(
            customer=customer, project=self.make_capstone_project(), school_name="School", program="BSIT",
            customization_notes="Details", **extra,
        )

    def test_delete_removes_the_customers_requests_conversations_messages_and_delivered_files(self):
        req = self.request_for(self.customer, delivered_source=zip_upload("delivery.zip"),
                               concept_file=SimpleUploadedFile("concept.pdf", b"%PDF-1.4 concept"))
        storage, delivered, concept = req.delivered_source.storage, req.delivered_source.name, req.concept_file.name
        CapstoneMessage.objects.create(request=req, sender=self.customer, body="Question")
        CapstoneMessage.objects.create(request=req, sender=self.staff, body="Answer")
        ContactMessage.objects.create(name="Mina", email=self.customer.email.upper(), subject="Hi", message="Hello")
        other = self.make_user("other")
        other_request = self.request_for(other)
        ContactMessage.objects.create(name="Other", email=other.email, subject="Hi", message="Hello")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("dashboard:customer_delete", args=[self.customer.pk]))
        self.assertRedirects(response, reverse("dashboard:customer_list"))
        self.assertFalse(User.objects.filter(pk=self.customer.pk).exists())
        self.assertFalse(CapstoneRequest.objects.filter(pk=req.pk).exists())
        self.assertFalse(CapstoneMessage.objects.filter(request_id=req.pk).exists())
        self.assertFalse(ContactMessage.objects.filter(email__iexact=self.customer.email).exists())
        self.assertFalse(storage.exists(delivered))
        self.assertFalse(storage.exists(concept))
        self.assertTrue(CapstoneRequest.objects.filter(pk=other_request.pk).exists())
        self.assertTrue(ContactMessage.objects.filter(email=other.email).exists())

    def test_delete_keeps_everything_and_deactivates_when_a_request_has_payments(self):
        req = self.request_for(self.customer)
        CapstoneMessage.objects.create(request=req, sender=self.customer, body="Question")
        ContactMessage.objects.create(name="Mina", email=self.customer.email, subject="Hi", message="Hello")
        Payment.objects.create(capstone_request=req, customer=self.customer, amount="500.00", method="gcash", provider="manual")
        response = self.client.post(reverse("dashboard:customer_delete", args=[self.customer.pk]))
        self.assertRedirects(response, reverse("dashboard:customer_list"))
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertTrue(CapstoneMessage.objects.filter(request=req).exists())
        self.assertTrue(ContactMessage.objects.filter(email=self.customer.email).exists())
