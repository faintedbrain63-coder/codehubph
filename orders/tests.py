from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from core.testing import BaseTestCase
from orders.models import Order


class PurchaseAccessTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.buyer = self.make_user("buyer")
        self.other = self.make_user("other")
        self.product = self.make_product("Paid App", price="1499.00")

    def _buy(self, user=None):
        self.client.force_login(user or self.buyer)
        response = self.client.post(reverse("orders:buy_now", args=[self.product.slug]))
        order = Order.objects.filter(user=user or self.buyer).latest("created_at")
        self.assertRedirects(response, order.get_payment_url())
        return order

    def _mark_paid(self, order):
        order.mark_paid(payment=None)
        order.refresh_from_db()
        return order.items.get()

    def test_buy_now_creates_pending_order_with_database_price(self):
        order = self._buy()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.total, Decimal("1499.00"))
        self.assertEqual(order.items.get().product_name, "Paid App")

    def test_buy_now_reuses_unpaid_order(self):
        first = self._buy()
        second = self._buy()
        self.assertEqual(first.pk, second.pk)

    def test_buy_now_requires_an_account_and_post(self):
        response = self.client.post(reverse("orders:buy_now", args=[self.product.slug]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:register"), response["Location"])
        self.assertFalse(Order.objects.exists())
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(reverse("orders:buy_now", args=[self.product.slug])).status_code, 405)

    def test_cannot_buy_draft_product(self):
        draft = self.make_product("Draft", status=Product.Status.DRAFT)
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(reverse("orders:buy_now", args=[draft.slug])).status_code, 404)

    def test_cannot_download_unpaid_file(self):
        order = self._buy()
        item = order.items.get()
        response = self.client.get(reverse("orders:download", args=[item.pk]))
        self.assertRedirects(response, order.get_absolute_url())
        self.assertNotIn("Content-Disposition", response)

    def test_cannot_download_someone_elses_file(self):
        order = self._buy()
        item = self._mark_paid(order)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("orders:download", args=[item.pk])).status_code, 404)

    def test_anonymous_download_redirects_to_login(self):
        item = self._mark_paid(self._buy())
        self.client.logout()
        response = self.client.get(reverse("orders:download", args=[item.pk]))
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_paid_owner_can_download_and_limit_is_enforced(self):
        item = self._mark_paid(self._buy())
        self.assertEqual(item.download_limit, 3)
        for _ in range(3):
            response = self.client.get(reverse("orders:download", args=[item.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment", response["Content-Disposition"])
            self.assertIn("paid-app", response["Content-Disposition"])
            b"".join(response.streaming_content)
        item.refresh_from_db()
        self.assertEqual(item.download_count, 3)
        response = self.client.get(reverse("orders:download", args=[item.pk]))
        self.assertEqual(response.status_code, 302)

    def test_expired_access_is_blocked(self):
        item = self._mark_paid(self._buy())
        item.access_expires_at = timezone.now() - timezone.timedelta(days=1)
        item.save()
        self.assertEqual(self.client.get(reverse("orders:download", args=[item.pk])).status_code, 302)

    def test_private_file_has_no_public_url(self):
        self.assertFalse(getattr(self.product.file, "url", False))
        self.assertNotContains(self.client.get(self.product.get_absolute_url()), self.product.file.name)

    def test_cart_checkout_creates_single_order(self):
        second = self.make_product("Second App", price="500.00")
        self.client.force_login(self.buyer)
        self.client.post(reverse("orders:cart_add", args=[self.product.slug]))
        self.client.post(reverse("orders:cart_add", args=[second.slug]))
        response = self.client.post(reverse("orders:cart_checkout"))
        order = Order.objects.get(user=self.buyer)
        self.assertRedirects(response, order.get_payment_url())
        self.assertEqual(order.total, Decimal("1999.00"))
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(self.client.session["cart"], [])

    def test_invoice_only_for_owner(self):
        order = self._buy()
        self.assertEqual(self.client.get(reverse("orders:invoice", args=[order.number])).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("orders:invoice", args=[order.number])).status_code, 404)
