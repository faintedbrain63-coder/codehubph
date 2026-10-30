import json
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.urls import reverse

from core.models import SiteSettings
from core.testing import BaseTestCase, png_upload
from orders.models import Order
from orders.services import create_order
from payments.models import Payment, WebhookEvent
from payments.providers import get_provider
from payments.services import PaymentError, approve_payment, complete_automated_payment, start_automated_payment


class ManualPaymentFlowTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        site = SiteSettings.load()
        site.gcash_number = "09170000000"
        site.gcash_account_name = "Store"
        site.save()
        self.customer = self.make_user("payer")
        self.staff = self.make_user("boss", staff=True)
        self.product = self.make_product("Billing System", price="2500.00")
        self.order, _ = create_order(self.customer, [self.product])
        self.client.force_login(self.customer)

    def _submit(self, method="gcash", reference="1234567890123", proof=True):
        data = {f"{method}-provider_reference": reference, f"{method}-confirm": "on"}
        if proof:
            data[f"{method}-proof_image"] = png_upload()
        url = reverse("payments:submit_manual", args=["order", self.order.number, method])
        return self.client.post(url, data)

    def test_checkout_shows_all_methods(self):
        response = self.client.get(self.order.get_payment_url())
        self.assertContains(response, "PayPal")
        self.assertContains(response, "GCash")
        self.assertContains(response, "Debit / Credit Card")
        self.assertContains(response, "https://paypal.me/faintedbrain63/2500.00PHP")
        self.assertContains(response, self.order.number)
        # Card fields need gateway keys; without them the card tab explains it is unavailable.
        self.assertContains(response, "isn’t available yet")

    def test_checkout_never_renders_raw_card_inputs(self):
        html = self.client.get(self.order.get_payment_url()).content.decode()
        for forbidden in ('name="card_number"', 'name="cvv"', 'name="cvc"', 'name="expiry"'):
            self.assertNotIn(forbidden, html)

    def test_gcash_qr_alone_enables_gcash_and_is_shown_first(self):
        site = SiteSettings.objects.get(pk=1)
        site.gcash_number = ""
        site.gcash_account_name = "CH******N R."
        site.gcash_qr = png_upload("gcash.png")
        site.save()
        self.assertTrue(get_provider("gcash_manual").is_configured())
        response = self.client.get(self.order.get_payment_url())
        self.assertContains(response, site.gcash_qr.url)
        self.assertContains(response, 'download="gcash-qr"')
        self.assertContains(response, "Upload QR")
        self.assertContains(response, "Check that the recipient shows <strong>CH******N R.</strong>", html=False)
        self.assertNotContains(response, "Or send money to this number")
        self.assertNotContains(response, "Copy number")

    def test_gcash_number_is_offered_next_to_the_qr(self):
        site = SiteSettings.objects.get(pk=1)
        site.gcash_qr = png_upload("gcash.png")
        site.save()
        response = self.client.get(self.order.get_payment_url())
        self.assertContains(response, site.gcash_qr.url)
        self.assertContains(response, "Or send money to this number")
        self.assertContains(response, "09170000000")

    def test_gcash_is_hidden_without_a_number_or_qr(self):
        SiteSettings.objects.filter(pk=1).update(gcash_number="", gcash_qr="")
        self.assertFalse(get_provider("gcash_manual").is_configured())

    def test_gcash_requires_receipt_screenshot(self):
        response = self._submit(proof=False)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_manual_submission_sets_awaiting_verification(self):
        response = self._submit()
        self.assertRedirects(response, self.order.get_absolute_url())
        payment = Payment.objects.get()
        self.order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.AWAITING_VERIFICATION)
        self.assertEqual(payment.amount, Decimal("2500.00"))
        self.assertEqual(self.order.status, Order.Status.AWAITING_VERIFICATION)
        self.assertTrue(payment.proof_image.name.startswith("payments/proofs/"))

    def test_second_submission_is_blocked_while_awaiting(self):
        self._submit()
        self._submit(reference="9999999999999")
        self.assertEqual(Payment.objects.count(), 1)

    def test_paypal_manual_screenshot_optional(self):
        response = self._submit(method="paypal", reference="8AB12345CD678901E", proof=False)
        self.assertRedirects(response, self.order.get_absolute_url())
        self.assertEqual(Payment.objects.get().method, "paypal")

    def test_staff_approval_marks_order_paid_and_unlocks_download(self):
        self._submit()
        payment = Payment.objects.get()
        mail.outbox.clear()
        self.client.force_login(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("dashboard:payment_approve", args=[payment.pk]))
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.COMPLETED)
        self.assertEqual(payment.verified_by, self.staff)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertTrue(self.order.items.get().can_download)
        self.assertTrue(any("confirmed" in m.subject for m in mail.outbox))

    def test_double_approval_is_idempotent(self):
        self._submit()
        payment = Payment.objects.get()
        _, changed_first = approve_payment(payment.pk, self.staff)
        self.order.refresh_from_db()
        paid_at = self.order.paid_at
        _, changed_second = approve_payment(payment.pk, self.staff)
        self.order.refresh_from_db()
        self.assertTrue(changed_first)
        self.assertFalse(changed_second)
        self.assertEqual(self.order.paid_at, paid_at)

    def test_customer_cannot_approve_own_payment(self):
        self._submit()
        payment = Payment.objects.get()
        response = self.client.post(reverse("dashboard:payment_approve", args=[payment.pk]))
        self.assertEqual(response.status_code, 403)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.AWAITING_VERIFICATION)

    def test_rejection_requires_reason_and_allows_retry(self):
        self._submit()
        payment = Payment.objects.get()
        self.client.force_login(self.staff)
        self.client.post(reverse("dashboard:payment_reject", args=[payment.pk]), {"reason": ""})
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.AWAITING_VERIFICATION)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("dashboard:payment_reject", args=[payment.pk]), {"reason": "Reference not found"})
        payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REJECTED)
        self.assertEqual(self.order.status, Order.Status.REJECTED)
        self.assertTrue(any("Reference not found" in m.body for m in mail.outbox))

        # Customer sees the reason and can submit again (even re-using the corrected reference).
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(self.order.get_payment_url()), "Reference not found")
        self._submit()
        self.assertEqual(Payment.objects.filter(status=Payment.Status.AWAITING_VERIFICATION).count(), 1)

    def test_same_reference_cannot_be_reused_for_another_order(self):
        self._submit(reference="5555555555555")
        other_product = self.make_product("Other", price="10.00")
        other_order, _ = create_order(self.customer, [other_product])
        url = reverse("payments:submit_manual", args=["order", other_order.number, "gcash"])
        self.client.post(url, {"gcash-provider_reference": "5555555555555", "gcash-confirm": "on",
                               "gcash-proof_image": png_upload()})
        self.assertFalse(Payment.objects.filter(order=other_order).exists())

    def test_refund_revokes_access(self):
        self._submit()
        approve_payment(Payment.objects.get().pk, self.staff)
        self.client.force_login(self.staff)
        self.client.post(reverse("dashboard:order_refund", args=[self.order.number]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.REFUNDED)
        self.assertFalse(self.order.items.get().can_download)

    def test_other_users_cannot_open_checkout(self):
        self.client.force_login(self.make_user("intruder"))
        self.assertEqual(self.client.get(self.order.get_payment_url()).status_code, 404)

    def test_staff_can_view_proof_but_customers_cannot(self):
        self._submit()
        payment = Payment.objects.get()
        url = reverse("dashboard:payment_proof", args=[payment.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.staff)
        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "image/png")


@override_settings(PAYPAL_CLIENT_ID="client", PAYPAL_SECRET="secret", PAYPAL_MODE="automated", PAYPAL_WEBHOOK_ID="WH-1")
class AutomatedPayPalTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_user("auto")
        self.order, _ = create_order(self.customer, [self.make_product("Auto App", price="300.00")])
        self.client.force_login(self.customer)

    def _capture_response(self, payment, amount="300.00", custom_id=None, status="COMPLETED"):
        return {
            "id": "PAYPAL-ORDER-1",
            "status": "COMPLETED",
            "purchase_units": [{
                "custom_id": str(custom_id or payment.pk),
                "payments": {"captures": [{
                    "id": "CAPTURE-1", "status": status, "custom_id": str(custom_id or payment.pk),
                    "amount": {"currency_code": "PHP", "value": amount},
                }]},
            }],
        }

    @mock.patch("payments.providers.paypal_api.create_order", return_value={"id": "PAYPAL-ORDER-1"})
    def test_create_uses_server_side_amount(self, create):
        response = self.client.post(
            reverse("payments:paypal_create"),
            data=json.dumps({"kind": "order", "reference": self.order.number, "method": "paypal", "amount": "1.00"}),
            content_type="application/json",
        )
        self.assertEqual(response.json(), {"id": "PAYPAL-ORDER-1"})
        self.assertEqual(create.call_args.kwargs["amount"], Decimal("300.00"))
        payment = Payment.objects.get()
        self.assertEqual(payment.provider_reference, "PAYPAL-ORDER-1")
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def _create_card(self, **extra):
        body = {"kind": "order", "reference": self.order.number, "method": "card", **extra}
        return self.client.post(reverse("payments:paypal_create"), data=json.dumps(body), content_type="application/json")

    @mock.patch("payments.providers.paypal_api.create_card_button_order")
    @mock.patch("payments.providers.paypal_api.create_card_order", return_value={"id": "CARD-ORDER-1"})
    def test_card_fields_order_requests_3d_secure_card_source(self, card_order, button_order):
        self.assertEqual(self._create_card().json(), {"id": "CARD-ORDER-1"})
        card_order.assert_called_once()
        button_order.assert_not_called()
        self.assertEqual(Payment.objects.get().provider, "card_paypal")

    @mock.patch("payments.providers.paypal_api.create_card_order")
    @mock.patch("payments.providers.paypal_api.create_card_button_order", return_value={"id": "CARD-BTN-1"})
    def test_card_button_fallback_uses_server_amount_and_card_method(self, button_order, card_order):
        response = self._create_card(cardButton=True, amount="1.00")
        self.assertEqual(response.json(), {"id": "CARD-BTN-1"})
        card_order.assert_not_called()
        self.assertEqual(button_order.call_args.kwargs["amount"], Decimal("300.00"))
        payment = Payment.objects.get()
        self.assertEqual((payment.method, payment.provider, payment.provider_reference), ("card", "card_paypal", "CARD-BTN-1"))

    def test_card_button_order_has_no_shipping_and_no_card_source(self):
        with mock.patch("payments.providers.paypal_api._request", return_value={"id": "X"}) as request:
            from payments.providers import paypal_api
            paypal_api.create_card_button_order(amount=Decimal("300.00"), currency="PHP", custom_id="1",
                                                invoice_id="FB-1-1", description="Order", request_id="r")
        payload = request.call_args.kwargs["json"]
        self.assertNotIn("payment_source", payload)
        self.assertEqual(payload["application_context"]["shipping_preference"], "NO_SHIPPING")
        self.assertEqual(payload["purchase_units"][0]["amount"], {"currency_code": "PHP", "value": "300.00"})

    def test_checkout_loads_card_fields_and_fallback_container(self):
        response = self.client.get(self.order.get_payment_url() + "?method=card")
        self.assertContains(response, "components=buttons,card-fields")
        self.assertContains(response, 'id="card-button"')
        self.assertContains(response, 'id="card-form"')

    @mock.patch("payments.providers.paypal_api.capture_order")
    def test_capture_marks_order_paid(self, capture):
        payment = start_automated_payment(self.order, self.customer, get_provider("paypal_checkout"))
        Payment.objects.filter(pk=payment.pk).update(provider_reference="PAYPAL-ORDER-1")
        capture.return_value = self._capture_response(payment)
        response = self.client.post(
            reverse("payments:paypal_capture"), data=json.dumps({"orderID": "PAYPAL-ORDER-1"}),
            content_type="application/json",
        )
        self.assertEqual(response.json()["status"], "COMPLETED")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        # Retrying the capture (double click) does not call PayPal again.
        self.client.post(reverse("payments:paypal_capture"), data=json.dumps({"orderID": "PAYPAL-ORDER-1"}),
                         content_type="application/json")
        self.assertEqual(capture.call_count, 1)

    @mock.patch("payments.providers.paypal_api.capture_order")
    def test_capture_with_wrong_payment_id_is_refused(self, capture):
        payment = start_automated_payment(self.order, self.customer, get_provider("paypal_checkout"))
        Payment.objects.filter(pk=payment.pk).update(provider_reference="PAYPAL-ORDER-1")
        capture.return_value = self._capture_response(payment, custom_id=999999)
        response = self.client.post(reverse("payments:paypal_capture"), data=json.dumps({"orderID": "PAYPAL-ORDER-1"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_amount_mismatch_is_refused(self):
        payment = start_automated_payment(self.order, self.customer, get_provider("paypal_checkout"))
        with self.assertRaises(PaymentError):
            complete_automated_payment(payment.pk, "CAP", "1.00", "PHP", {})
        payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(self.order.status, Order.Status.PENDING)

    @mock.patch("payments.providers.paypal_api.verify_webhook_signature", return_value=False)
    def test_webhook_with_bad_signature_is_rejected(self, _verify):
        response = self.client.post(reverse("payments:paypal_webhook"), data=json.dumps({"id": "WH-EVT"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(WebhookEvent.objects.exists())

    @mock.patch("payments.providers.paypal_api.verify_webhook_signature", return_value=True)
    def test_webhook_completes_payment_once(self, _verify):
        payment = start_automated_payment(self.order, self.customer, get_provider("paypal_checkout"))
        event = {
            "id": "WH-EVT-1",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {"id": "CAP-9", "custom_id": str(payment.pk), "amount": {"value": "300.00", "currency_code": "PHP"}},
        }
        for _ in range(2):  # replay
            response = self.client.post(reverse("payments:paypal_webhook"), data=json.dumps(event),
                                        content_type="application/json")
            self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(WebhookEvent.objects.count(), 1)
