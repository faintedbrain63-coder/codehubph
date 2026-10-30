from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from capstone.models import CapstoneRequest
from core.models import SiteSettings
from core.testing import BaseTestCase, png_upload
from payments.models import Payment


class CapstoneWorkflowTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        site = SiteSettings.load()
        site.gcash_number = "09170000000"
        site.save()
        self.student = self.make_user("student", school="PUP")
        self.staff = self.make_user("admin1", staff=True)
        self.project = self.make_capstone_project(with_docs=True)

    def _submit_request(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("capstone:request_create", args=[self.project.slug]),
            {
                "school_name": "PUP",
                "program": "BS Information Technology",
                "group_members": "Juan\nMaria",
                "customization_notes": "Add SMS notifications.",
                "preferred_deadline": (timezone.localdate() + timedelta(days=30)).isoformat(),
            },
        )
        req = CapstoneRequest.objects.get(customer=self.student)
        self.assertRedirects(response, req.get_absolute_url())
        return req

    def _quote(self, req, price="18000.00"):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("dashboard:capstone_request_quote", args=[req.reference]),
            {"agreed_price": price, "quote_notes": "Includes SMS module."},
        )
        req.refresh_from_db()
        return req

    def test_public_pages_list_capstone_projects(self):
        response = self.client.get(reverse("capstone:list"))
        self.assertContains(response, self.project.title)
        self.assertContains(response, "Starting at")
        self.assertEqual(self.client.get(self.project.get_absolute_url()).status_code, 200)

    def test_request_requires_an_account(self):
        url = reverse("capstone:request_create", args=[self.project.slug])
        response = self.client.get(url)
        self.assertIn(reverse("accounts:register"), response["Location"])
        self.assertIn(f"next={url}", response["Location"])

    def test_full_workflow_from_request_to_completion(self):
        req = self._submit_request()
        self.assertEqual(req.status, CapstoneRequest.Status.SUBMITTED)
        self.assertTrue(req.reference.startswith("CAP-"))

        req = self._quote(req)
        self.assertEqual(req.status, CapstoneRequest.Status.QUOTED)
        self.assertEqual(req.agreed_price, Decimal("18000.00"))

        self.client.force_login(self.student)
        self.client.post(reverse("capstone:request_accept", args=[req.reference]))
        req.refresh_from_db()
        self.assertEqual(req.status, CapstoneRequest.Status.ACCEPTED)

        # Files are locked before payment.
        response = self.client.get(reverse("capstone:request_download", args=[req.reference, "source"]))
        self.assertRedirects(response, req.get_absolute_url())

        # Pay through the same checkout used by product orders.
        self.assertEqual(self.client.get(req.get_payment_url()).status_code, 200)
        self.client.post(
            reverse("payments:submit_manual", args=["capstone", req.reference, "gcash"]),
            {"gcash-provider_reference": "7777777777777", "gcash-confirm": "on", "gcash-proof_image": png_upload()},
        )
        payment = Payment.objects.get(capstone_request=req)
        self.assertEqual(payment.amount, Decimal("18000.00"))
        req.refresh_from_db()
        self.assertEqual(req.status, CapstoneRequest.Status.ACCEPTED)

        self.client.force_login(self.staff)
        self.client.post(reverse("dashboard:payment_approve", args=[payment.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, CapstoneRequest.Status.PAID)

        for action, expected in (("in_progress", "in_progress"), ("delivered", "delivered")):
            self.client.post(reverse("dashboard:capstone_request_status", args=[req.reference]), {"action": action})
            req.refresh_from_db()
            self.assertEqual(req.status, expected)

        self.client.force_login(self.student)
        for kind in ("source", "documentation"):
            response = self.client.get(reverse("capstone:request_download", args=[req.reference, kind]))
            self.assertEqual(response.status_code, 200, kind)
            self.assertIn("attachment", response["Content-Disposition"])
            b"".join(response.streaming_content)

        self.client.post(reverse("capstone:request_complete", args=[req.reference]))
        req.refresh_from_db()
        self.assertEqual(req.status, CapstoneRequest.Status.COMPLETED)
        self.assertIsNotNone(req.completed_at)

    def test_invalid_transitions_are_blocked(self):
        req = self._submit_request()
        with self.assertRaises(ValueError):
            req.transition_to(CapstoneRequest.Status.PAID)
        # Customer cannot accept before a quote exists.
        self.client.post(reverse("capstone:request_accept", args=[req.reference]))
        req.refresh_from_db()
        self.assertEqual(req.status, CapstoneRequest.Status.SUBMITTED)
        # Cannot pay before accepting a quote.
        response = self.client.get(req.get_payment_url())
        self.assertTemplateUsed(response, "payments/checkout_closed.html")

    def test_quote_requires_price(self):
        req = self._submit_request()
        self.client.force_login(self.staff)
        self.client.post(reverse("dashboard:capstone_request_quote", args=[req.reference]), {"agreed_price": ""})
        req.refresh_from_db()
        self.assertEqual(req.status, CapstoneRequest.Status.SUBMITTED)

    def test_other_customers_cannot_see_request(self):
        req = self._submit_request()
        self.client.force_login(self.make_user("nosy"))
        self.assertEqual(self.client.get(req.get_absolute_url()).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("capstone:request_download", args=[req.reference, "source"])).status_code, 404
        )

    def test_customers_cannot_use_admin_actions(self):
        req = self._submit_request()
        response = self.client.post(
            reverse("dashboard:capstone_request_quote", args=[req.reference]), {"agreed_price": "1.00"}
        )
        self.assertEqual(response.status_code, 403)

    def test_cancel_only_before_payment(self):
        req = self._submit_request()
        self.client.post(reverse("capstone:request_cancel", args=[req.reference]))
        req.refresh_from_db()
        self.assertEqual(req.status, CapstoneRequest.Status.CANCELLED)

        req2 = CapstoneRequest.objects.create(
            customer=self.student, project=self.project, school_name="PUP", program="BSIT",
            customization_notes="x", agreed_price=Decimal("100.00"), status=CapstoneRequest.Status.PAID,
        )
        self.client.post(reverse("capstone:request_cancel", args=[req2.reference]))
        req2.refresh_from_db()
        self.assertEqual(req2.status, CapstoneRequest.Status.PAID)

    def test_capstone_cannot_be_bought_as_product(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse("orders:buy_now", args=[self.project.slug])).status_code, 404)
        self.assertEqual(self.client.post(reverse("orders:cart_add", args=[self.project.slug])).status_code, 404)

    def test_messages_thread(self):
        req = self._submit_request()
        self.client.post(reverse("capstone:request_message", args=[req.reference]), {"body": "Can you add a chart?"})
        self.client.force_login(self.staff)
        self.client.post(reverse("dashboard:capstone_request_message", args=[req.reference]), {"body": "Yes, included."})
        self.assertEqual(req.messages.count(), 2)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(req.get_absolute_url()), "Yes, included.")
