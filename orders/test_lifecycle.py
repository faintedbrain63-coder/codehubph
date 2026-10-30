from django.urls import reverse

from core.models import SiteSettings
from core.testing import BaseTestCase, png_upload
from orders.models import Order
from orders.services import create_order
from payments.models import Payment
from payments.services import PaymentError, start_automated_payment, submit_manual_payment
from payments.providers import get_provider


class OrderCancellationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_user("buyer")
        self.other = self.make_user("other")
        self.first = self.make_product("First App", price="700.00")
        self.second = self.make_product("Second App", price="300.00")
        self.order, _ = create_order(self.customer, [self.first, self.second])
        self.client.force_login(self.customer)

    def _cancel(self, order=None, **data):
        return self.client.post(reverse("orders:cancel", args=[(order or self.order).number]), data)

    def test_customer_can_cancel_unpaid_order(self):
        response = self._cancel()
        self.assertRedirects(response, self.order.get_absolute_url())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertIsNotNone(self.order.cancelled_at)
        self.assertFalse(self.order.can_be_paid)

    def test_cancel_requires_post_and_ownership(self):
        self.assertEqual(self.client.get(reverse("orders:cancel", args=[self.order.number])).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self._cancel().status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_paid_order_cannot_be_cancelled(self):
        self.order.mark_paid(payment=None)
        self._cancel()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_order_under_review_cannot_be_cancelled(self):
        site = SiteSettings.load()
        site.gcash_number, site.gcash_account_name = "09170000000", "Store"
        site.save()
        submit_manual_payment(self.order, self.customer, get_provider("gcash_manual"), "1234567890123", png_upload())
        self._cancel()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.AWAITING_VERIFICATION)

    def test_cancel_retires_pending_gateway_attempts(self):
        with self.settings(PAYPAL_CLIENT_ID="id", PAYPAL_SECRET="secret", PAYPAL_MODE="automated"):
            payment = start_automated_payment(self.order, self.customer, get_provider("paypal_checkout"))
        self._cancel()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)

    def test_cancelled_order_is_not_reused_for_new_checkout(self):
        self._cancel()
        new_order, created = create_order(self.customer, [self.first, self.second])
        self.assertTrue(created)
        self.assertNotEqual(new_order.pk, self.order.pk)

    def test_restore_moves_remaining_items_to_cart(self):
        response = self._cancel(restore_cart="1")
        self.assertRedirects(response, reverse("orders:cart"))
        self.assertEqual(sorted(self.client.session["cart"]), sorted([self.first.pk, self.second.pk]))


class AlreadyOwnedProductTests(BaseTestCase):
    """A stale pending order must not charge a customer again for something they bought elsewhere."""

    def setUp(self):
        super().setUp()
        site = SiteSettings.load()
        site.gcash_number, site.gcash_account_name = "09170000000", "Store"
        site.save()
        self.customer = self.make_user("buyer")
        self.first = self.make_product("First App", price="700.00")
        self.second = self.make_product("Second App", price="300.00")
        self.stale, _ = create_order(self.customer, [self.first, self.second])
        bought, _ = create_order(self.customer, [self.first])
        bought.mark_paid(payment=None)
        self.client.force_login(self.customer)

    def test_checkout_explains_conflict_instead_of_taking_payment(self):
        response = self.client.get(self.stale.get_payment_url())
        self.assertContains(response, "You already own First App")
        self.assertContains(response, reverse("orders:cancel", args=[self.stale.number]))
        self.assertNotContains(response, "paypal.me")

    def test_services_refuse_manual_and_gateway_payment(self):
        with self.assertRaisesMessage(PaymentError, "already own"):
            submit_manual_payment(self.stale, self.customer, get_provider("gcash_manual"), "1234567890123", png_upload())
        with self.settings(PAYPAL_CLIENT_ID="id", PAYPAL_SECRET="secret", PAYPAL_MODE="automated"):
            with self.assertRaisesMessage(PaymentError, "already own"):
                start_automated_payment(self.stale, self.customer, get_provider("paypal_checkout"))
        self.assertFalse(Payment.objects.exists())

    def test_cancel_and_restore_keeps_only_unowned_items(self):
        response = self.client.post(reverse("orders:cancel", args=[self.stale.number]), {"restore_cart": "1"})
        self.assertRedirects(response, reverse("orders:cart"))
        self.assertEqual(self.client.session["cart"], [self.second.pk])

    def test_order_without_conflict_is_unaffected(self):
        fresh, _ = create_order(self.customer, [self.second])
        self.assertIsNone(fresh.payment_block_reason)
        self.assertContains(self.client.get(fresh.get_payment_url()), "paypal.me")
