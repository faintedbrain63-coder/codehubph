"""Regression coverage for the project audit's cross-feature edge cases."""

import json
from decimal import Decimal
from unittest import mock

from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from capstone.models import CapstoneRequest
from core.models import SiteSettings, Testimonial
from core.notifications import send_templated_email
from core.testing import PASSWORD, BaseTestCase
from core.legal import CURRENT_VERSIONS
from orders.models import Order
from orders.services import create_order
from payments.forms import ManualPaymentForm
from payments.models import Payment, WebhookEvent
from payments.providers import get_provider
from payments.services import (
    PaymentError, approve_payment, complete_automated_payment,
    refund_payable, start_automated_payment, submit_manual_payment,
)


class OrderRegressionTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_user()
        self.product = self.make_product()
        self.client.force_login(self.customer)

    def test_buy_now_does_not_reuse_a_larger_cart_order(self):
        cart_order, _ = create_order(self.customer, [self.product, self.make_product("Second")])
        single_order, created = create_order(self.customer, [self.product])
        self.assertTrue(created)
        self.assertNotEqual(cart_order.pk, single_order.pk)
        self.assertEqual(single_order.items.count(), 1)

    def test_identical_cart_checkout_reuses_order(self):
        products = [self.product, self.make_product("Second")]
        first, _ = create_order(self.customer, products)
        second, created = create_order(self.customer, reversed(products))
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)

    def test_new_checkout_uses_current_product_price(self):
        first, _ = create_order(self.customer, [self.product])
        self.product.price = Decimal("100.00")
        self.product.save()
        second, _ = create_order(self.customer, [self.product])
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.total, Decimal("100.00"))

    def test_missing_file_does_not_consume_download(self):
        order, _ = create_order(self.customer, [self.product])
        order.mark_paid(None)
        item = order.items.get()
        with mock.patch.object(self.product.file.storage, "open", side_effect=FileNotFoundError):
            response = self.client.get(reverse("orders:download", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.download_count, 0)

    def test_head_does_not_consume_download(self):
        order, _ = create_order(self.customer, [self.product])
        order.mark_paid(None)
        item = order.items.get()
        response = self.client.head(reverse("orders:download", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.download_count, 0)

    def test_product_page_explains_expired_download(self):
        order, _ = create_order(self.customer, [self.product])
        order.mark_paid(None)
        order.items.update(access_expires_at=timezone.now() - timezone.timedelta(days=1))
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, "expired")
        self.assertNotContains(response, f'href="{reverse("orders:download", args=[order.items.get().pk])}"')

    def test_checkout_refuses_products_unpublished_after_selection(self):
        self.product.status = "draft"
        self.product.save()
        with self.assertRaises(ValueError):
            create_order(self.customer, [self.product])
        self.assertFalse(Order.objects.exists())

    @mock.patch("orders.views.create_order", side_effect=ValueError("Product is no longer available."))
    def test_buy_now_handles_a_product_unpublished_during_checkout(self, _create):
        response = self.client.post(reverse("orders:buy_now", args=[self.product.slug]))
        self.assertRedirects(response, reverse("catalog:list"))

    @mock.patch("orders.views.create_order", side_effect=ValueError("Product is no longer available."))
    def test_cart_handles_a_product_unpublished_during_checkout(self, _create):
        self.client.post(reverse("orders:cart_add", args=[self.product.slug]))
        response = self.client.post(reverse("orders:cart_checkout"))
        self.assertRedirects(response, reverse("orders:cart"))


@override_settings(PAYPAL_MODE="automated", PAYPAL_CLIENT_ID="client", PAYPAL_SECRET="secret")
class PaymentRegressionTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_user()
        self.staff = self.make_user("staff", staff=True)
        self.order, _ = create_order(self.customer, [self.make_product(price="300.00")])
        self.client.force_login(self.customer)

    def _pending(self):
        payment = start_automated_payment(self.order, self.customer, get_provider("paypal_checkout"))
        payment.provider_reference = "PAYPAL-ORDER-1"
        payment.save()
        return payment

    def _manual(self):
        return submit_manual_payment(self.order, self.customer, get_provider("paypal_manual"), "ABC123456")

    def test_json_endpoints_reject_non_objects(self):
        for name in ("payments:paypal_create", "payments:paypal_capture", "payments:paypal_webhook"):
            for value in ([], "text", 1, None):
                with self.subTest(name=name, value=value):
                    response = self.client.post(reverse(name), json.dumps(value), content_type="application/json")
                    self.assertEqual(response.status_code, 400)

    def test_create_rejects_non_string_kind(self):
        response = self.client.post(reverse("payments:paypal_create"), json.dumps({
            "method": "paypal", "kind": [], "reference": self.order.number,
        }), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_repeated_gateway_start_preserves_existing_attempt(self):
        first = self._pending()
        second = start_automated_payment(self.order, self.customer, get_provider("paypal_checkout"))
        self.assertEqual(first.pk, second.pk)
        first.refresh_from_db()
        self.assertEqual(first.status, Payment.Status.PENDING)

    @mock.patch("payments.providers.paypal_api.create_order")
    def test_create_reuses_provider_order(self, create):
        self._pending()
        response = self.client.post(reverse("payments:paypal_create"), json.dumps({
            "method": "paypal", "kind": "order", "reference": self.order.number,
        }), content_type="application/json")
        self.assertEqual(response.json(), {"id": "PAYPAL-ORDER-1"})
        create.assert_not_called()

    def test_staff_cannot_approve_unconfirmed_gateway_capture(self):
        payment = self._pending()
        payment.status = Payment.Status.AWAITING_VERIFICATION
        payment.save()
        with self.assertRaises(PaymentError):
            approve_payment(payment.pk, self.staff)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_manual_payment_cannot_be_completed_by_gateway(self):
        payment = self._manual()
        with self.assertRaises(PaymentError):
            complete_automated_payment(payment.pk, "CAP", "300.00", "PHP", {})

    def test_completion_never_resurrects_refunded_order(self):
        payment = self._pending()
        self.order.status = Order.Status.REFUNDED
        self.order.save()
        with self.assertRaises(PaymentError):
            complete_automated_payment(payment.pk, "CAP", "300.00", "PHP", {})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.REFUNDED)

    def test_invalid_gateway_amount_is_a_payment_error(self):
        for amount in ("broken", "NaN", "Infinity", "-1"):
            with self.subTest(amount=amount):
                payment = self._pending()
                with self.assertRaises(PaymentError):
                    complete_automated_payment(payment.pk, "CAP", amount, "PHP", {})

    @mock.patch("payments.providers.paypal_api.capture_order")
    def test_rejected_payment_never_calls_capture_api(self, capture):
        payment = self._pending()
        payment.status = Payment.Status.REJECTED
        payment.save()
        response = self.client.post(reverse("payments:paypal_capture"), json.dumps({
            "orderID": payment.provider_reference,
        }), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        capture.assert_not_called()

    def test_cannot_refund_an_unpaid_order(self):
        with self.assertRaises(PaymentError):
            refund_payable(self.order, self.staff)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    @mock.patch("payments.providers.paypal_api.verify_webhook_signature", return_value=True)
    def test_refund_without_capture_id_does_not_refund_manual_payment(self, _verify):
        payment = self._manual()
        approve_payment(payment.pk, self.staff)
        response = self.client.post(reverse("payments:paypal_webhook"), json.dumps({
            "id": "REFUND-1", "event_type": "PAYMENT.CAPTURE.REFUNDED", "resource": {},
        }), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    @mock.patch("payments.providers.paypal_api.verify_webhook_signature", return_value=True)
    def test_webhook_requires_event_identity(self, _verify):
        response = self.client.post(reverse("payments:paypal_webhook"), json.dumps({
            "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {},
        }), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(WebhookEvent.objects.exists())

    def test_submission_cannot_assign_a_different_customer(self):
        with self.assertRaises(PaymentError):
            submit_manual_payment(self.order, self.staff, get_provider("paypal_manual"), "ABC123456")

    @mock.patch("payments.providers.paypal_api.verify_webhook_signature", return_value=True)
    @mock.patch("payments.providers.paypal_api.get_capture", return_value={"status": "REFUNDED"})
    def test_full_gateway_refund_revokes_access_and_replays_safely(self, get_capture, _verify):
        payment = self._pending()
        complete_automated_payment(payment.pk, "CAP-1", "300.00", "PHP", {})
        event = {"id": "REFUND-1", "event_type": "PAYMENT.CAPTURE.REFUNDED", "resource": {
            "links": [{"rel": "up", "href": "https://api-m.paypal.com/v2/payments/captures/CAP-1"}],
        }}
        for _ in range(2):
            response = self.client.post(reverse("payments:paypal_webhook"), json.dumps(event), content_type="application/json")
            self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.REFUNDED)
        self.assertFalse(self.order.items.get().can_download)
        self.assertEqual(get_capture.call_count, 1)

    @mock.patch("payments.providers.paypal_api.verify_webhook_signature", return_value=True)
    @mock.patch("payments.providers.paypal_api.get_capture", return_value={"status": "PARTIALLY_REFUNDED"})
    def test_partial_gateway_refund_preserves_access(self, _get_capture, _verify):
        payment = self._pending()
        complete_automated_payment(payment.pk, "CAP-1", "300.00", "PHP", {})
        response = self.client.post(reverse("payments:paypal_webhook"), json.dumps({
            "id": "REFUND-1", "event_type": "PAYMENT.CAPTURE.REFUNDED", "resource": {
                "links": [{"rel": "up", "href": "https://api-m.paypal.com/v2/payments/captures/CAP-1"}],
            },
        }), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    @mock.patch("payments.providers.paypal_api.verify_webhook_signature", return_value=True)
    def test_unknown_payment_webhook_is_retained_for_retry(self, _verify):
        response = self.client.post(reverse("payments:paypal_webhook"), json.dumps({
            "id": "EARLY-1", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {
                "id": "CAP-1", "custom_id": "9999999", "amount": {"value": "300.00", "currency_code": "PHP"},
            },
        }), content_type="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(WebhookEvent.objects.get().processed_at)

    @mock.patch("payments.providers.paypal_api.capture_order")
    def test_changed_quote_is_refused_before_charging(self, capture):
        payment = self._pending()
        self.order.total = Decimal("400.00")
        self.order.save()
        response = self.client.post(reverse("payments:paypal_capture"), json.dumps({
            "orderID": payment.provider_reference,
        }), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        capture.assert_not_called()

    @mock.patch("payments.providers.paypal_api.capture_order")
    def test_pending_capture_cannot_be_captured_twice(self, capture):
        payment = self._pending()
        capture.return_value = {"id": payment.provider_reference, "purchase_units": [{
            "custom_id": str(payment.pk), "payments": {"captures": [{
                "id": "CAP-1", "status": "PENDING", "amount": {"value": "300.00", "currency_code": "PHP"},
            }]},
        }]}
        for _ in range(2):
            response = self.client.post(reverse("payments:paypal_capture"), json.dumps({
                "orderID": payment.provider_reference,
            }), content_type="application/json")
            self.assertEqual(response.json()["status"], "PENDING")
        self.assertEqual(capture.call_count, 1)

    @mock.patch("payments.providers.paypal_api.capture_order", return_value={"purchase_units": [None]})
    def test_malformed_gateway_response_has_controlled_error(self, _capture):
        payment = self._pending()
        response = self.client.post(reverse("payments:paypal_capture"), json.dumps({
            "orderID": payment.provider_reference,
        }), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @mock.patch("payments.providers.paypal_api._access_token", return_value="token")
    @mock.patch("payments.providers.paypal_api.requests.request")
    def test_gateway_requests_the_full_capture_representation(self, request, _token):
        from payments.providers import paypal_api

        request.return_value.status_code = 201
        request.return_value.json.return_value = {"id": "ORDER-1"}
        paypal_api.capture_order("ORDER-1", "retry-key")
        self.assertEqual(request.call_args.kwargs["headers"]["Prefer"], "return=representation")

    @mock.patch("payments.providers.paypal_api.verify_webhook_signature", return_value=True)
    def test_capture_event_can_match_provider_order_when_custom_id_is_absent(self, _verify):
        payment = self._pending()
        response = self.client.post(reverse("payments:paypal_webhook"), json.dumps({
            "id": "CAPTURE-EVENT", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {
                "id": "CAP-1", "amount": {"value": "300.00", "currency_code": "PHP"},
                "supplementary_data": {"related_ids": {"order_id": payment.provider_reference}},
            },
        }), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    @mock.patch("payments.providers.paypal_api.verify_webhook_signature", return_value=True)
    @mock.patch("payments.providers.paypal_api.get_capture")
    def test_refund_before_completion_never_unlocks_files(self, get_capture, _verify):
        payment = self._pending()
        get_capture.return_value = {"id": "CAP-1", "custom_id": str(payment.pk), "status": "REFUNDED"}
        response = self.client.post(reverse("payments:paypal_webhook"), json.dumps({
            "id": "EARLY-REFUND", "event_type": "PAYMENT.CAPTURE.REFUNDED", "resource": {
                "links": [{"rel": "up", "href": "https://api-m.paypal.com/v2/payments/captures/CAP-1"}],
            },
        }), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        with self.assertLogs("payments", level="ERROR"):
            response = self.client.post(reverse("payments:paypal_webhook"), json.dumps({
                "id": "LATE-COMPLETION", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {
                    "id": "CAP-1", "custom_id": str(payment.pk), "amount": {"value": "300.00", "currency_code": "PHP"},
                },
            }), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REFUNDED)
        self.assertFalse(self.order.items.get().can_download)


class WorkflowAndUIRegressionTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_user()
        self.staff = self.make_user("staff", staff=True)

    def test_pending_capstone_payment_freezes_quote_and_cancellation(self):
        req = CapstoneRequest.objects.create(
            customer=self.customer, project=self.make_capstone_project(), school_name="School", program="BSIT",
            customization_notes="Custom reports", agreed_price=Decimal("300.00"), status="accepted",
        )
        payment = submit_manual_payment(req, self.customer, get_provider("paypal_manual"), "ABC123456")
        self.client.force_login(self.staff)
        response = self.client.post(reverse("dashboard:capstone_request_quote", args=[req.reference]), {
            "agreed_price": "900.00", "quote_notes": "Changed",
        })
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.agreed_price, Decimal("300.00"))
        self.assertEqual(req.status, "accepted")
        self.client.force_login(self.customer)
        self.client.post(reverse("capstone:request_cancel", args=[req.reference]))
        req.refresh_from_db()
        self.assertEqual(req.status, "accepted")
        approve_payment(payment.pk, self.staff)
        req.refresh_from_db()
        self.assertEqual(req.status, "paid")

    def test_gcash_requires_a_13_digit_reference(self):
        form = ManualPaymentForm({"gcash-provider_reference": "ABCDEF1234567", "gcash-confirm": "on"},
                                 provider=get_provider("gcash_manual"))
        self.assertFalse(form.is_valid())
        self.assertIn("provider_reference", form.errors)

    def test_verified_review_requires_a_purchase(self):
        review = Testimonial.objects.create(user=self.customer, name="Customer", message="Helpful product.")
        self.assertFalse(review.is_verified_customer)

    def test_pagination_includes_the_current_middle_page(self):
        page = Paginator(range(1000), 10).page(50)
        request = RequestFactory().get("/products/?page=50&q=app")
        html = render_to_string("partials/_pagination.html", {"page_obj": page, "request": request})
        self.assertIn('aria-current="page"', html)
        self.assertIn('>50</span>', html)
        self.assertIn('page=51', html)

    @override_settings(PAYPAL_ME_URL="")
    def test_unavailable_method_is_not_selected(self):
        site = SiteSettings.load()
        site.paypal_me_url = ""
        site.gcash_number = "09171234567"
        site.save()
        order, _ = create_order(self.customer, [self.make_product()])
        self.client.force_login(self.customer)
        response = self.client.get(order.get_payment_url() + "?method=card")
        self.assertEqual(response.context["selected"], "gcash")

    def test_empty_contact_post_shows_errors(self):
        response = self.client.post(reverse("core:contact"), {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.context["contact_form"].errors)

    def test_long_display_name_can_leave_review(self):
        self.customer.first_name = "A" * 100
        self.customer.last_name = "B" * 100
        self.customer.save()
        order, _ = create_order(self.customer, [self.make_product()])
        order.mark_paid(None)
        self.client.force_login(self.customer)
        response = self.client.post(reverse("accounts:testimonial"), {
            "rating": "5", "message": "This product helped our group finish the project.", "role": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertLessEqual(len(Testimonial.objects.get().name), 100)

    @mock.patch("core.notifications.render_to_string", side_effect=RuntimeError("Template error"))
    def test_email_render_failure_does_not_break_main_workflow(self, _render):
        with self.assertLogs("core.notifications", level="ERROR"):
            send_templated_email("Order", "order_received", {}, ["person@example.com"])

    def test_capstone_refund_requires_staff_and_revokes_access(self):
        req = CapstoneRequest.objects.create(
            customer=self.customer, project=self.make_capstone_project(), school_name="School", program="BSIT",
            customization_notes="Custom reports", agreed_price=Decimal("300.00"), status="accepted",
        )
        payment = submit_manual_payment(req, self.customer, get_provider("paypal_manual"), "ABC123456")
        approve_payment(payment.pk, self.staff)
        url = reverse("dashboard:capstone_request_refund", args=[req.reference])
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url, {"notes": "Refunded"}).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(url, {"notes": "Refunded via PayPal"}).status_code, 302)
        req.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(req.status, CapstoneRequest.Status.CANCELLED)
        self.assertFalse(req.files_unlocked)
        self.assertEqual(payment.status, Payment.Status.REFUNDED)

    def test_all_public_customer_and_staff_page_templates_render(self):
        product = self.make_product()
        order, _ = create_order(self.customer, [product])
        project = self.make_capstone_project()
        req = CapstoneRequest.objects.create(
            customer=self.customer, project=project, school_name="School", program="BSIT",
            customization_notes="Custom reports",
        )
        for name in ("core:home", "core:terms", "core:privacy", "catalog:list", "capstone:list", "orders:cart",
                     "accounts:login", "accounts:register", "accounts:password_reset"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.client.force_login(self.customer)
        customer_urls = [product.get_absolute_url(), project.get_absolute_url(), order.get_absolute_url(),
                         order.get_payment_url(), req.get_absolute_url(),
                         reverse("capstone:request_create", args=[project.slug])]
        customer_urls += [reverse(name) for name in ("accounts:dashboard", "accounts:profile", "accounts:password_change",
                         "accounts:testimonial", "orders:list", "capstone:my_requests")]
        for url in customer_urls:
            with self.subTest(page=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.staff)
        staff_urls = [reverse(name) for name in ("dashboard:home", "dashboard:product_list", "dashboard:product_create",
                      "dashboard:capstone_project_list", "dashboard:capstone_project_create", "dashboard:capstone_request_list",
                      "dashboard:order_list", "dashboard:payment_list", "dashboard:customer_list", "dashboard:message_list",
                      "dashboard:testimonial_list", "dashboard:testimonial_create", "dashboard:settings")]
        staff_urls += [reverse("dashboard:product_edit", args=[product.pk]),
                       reverse("dashboard:capstone_project_edit", args=[project.pk]),
                       reverse("dashboard:capstone_request_detail", args=[req.reference]),
                       reverse("dashboard:order_detail", args=[order.number])]
        for url in staff_urls:
            with self.subTest(page=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_django_admin_cannot_bypass_order_payment_workflow(self):
        order, _ = create_order(self.customer, [self.make_product()])
        superuser = self.make_user("superuser", staff=True, is_superuser=True)
        self.client.force_login(superuser)
        url = reverse("admin:orders_order_change", args=[order.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"status": "paid"}).status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_email_can_sign_in_without_a_username(self):
        user = self.make_user("email-login", email="unique@example.com")
        response = self.client.post(reverse("accounts:login"), {"email": user.email, "password": PASSWORD})
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_login_lockout_is_shared_by_email_case_variants(self):
        for identifier in ("alice@example.com", "ALICE@example.com", "alice@EXAMPLE.COM", "ALICE@EXAMPLE.COM", "Alice@Example.com"):
            self.client.post(reverse("accounts:login"), {"email": identifier, "password": "wrong"})
        response = self.client.post(reverse("accounts:login"), {"email": "alice@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 429)

    def test_featured_products_sort_first_but_price_sort_is_respected(self):
        featured = self.make_product("Featured", price="900.00", is_featured=True)
        other = self.make_product("Other", price="100.00")
        response = self.client.get(reverse("catalog:list"))
        self.assertEqual(list(response.context["products"]), [featured, other])
        response = self.client.get(reverse("catalog:list") + "?sort=price_asc")
        self.assertEqual(list(response.context["products"]), [other, featured])

    def test_malformed_cart_values_do_not_crash_or_duplicate_purchases(self):
        product = self.make_product()
        session = self.client.session
        session["cart"] = [product.pk, str(product.pk), "²", "9" * 100, 0, -1, None]
        session.save()
        response = self.client.get(reverse("orders:cart"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["products"]), [product])
        self.assertEqual(self.client.session["cart"], [product.pk])

    def test_registration_preserves_the_requested_destination(self):
        url = reverse("accounts:register") + "?next=%2Fcart%2F"
        self.assertContains(self.client.get(url), 'name="next" value="/cart/"')
        response = self.client.post(reverse("accounts:register"), {
            "first_name": "New", "last_name": "Customer",
            "email": "new@example.com", "password1": PASSWORD, "password2": PASSWORD, "next": "/cart/",
            "accept_privacy": "on", "accept_license": "on",
            "privacy_version": CURRENT_VERSIONS["privacy"], "license_version": CURRENT_VERSIONS["license"],
        })
        self.assertRedirects(response, reverse("orders:cart"))
