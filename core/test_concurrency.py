"""Exercise row locks using independent PostgreSQL connections, without TestCase's outer transaction."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

from django.core.cache import cache
from django.db import connections
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from core.testing import TEST_MEDIA, BaseTestCase
from orders.models import Order
from orders.services import create_order
from payments.models import Payment
from payments.providers import get_provider
from payments.services import PaymentError, approve_payment, refund_payable, submit_manual_payment


@override_settings(PRIVATE_MEDIA_ROOT=f"{TEST_MEDIA}/concurrency", DOWNLOAD_LIMIT=1, PRODUCT_SALES_ENABLED=True)
class ConcurrentWorkflowTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.customer = BaseTestCase.make_user("concurrent")
        self.staff = BaseTestCase.make_user("concurrent-staff", staff=True)
        self.product = BaseTestCase.make_product("Concurrent App")

    @staticmethod
    def _together(*jobs):
        barrier = Barrier(len(jobs))

        def run(job):
            try:
                barrier.wait(timeout=10)
                return job()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            return [future.result(timeout=20) for future in futures]

    @mock.patch("orders.services.notify_order_received")
    def test_simultaneous_checkouts_create_one_order(self, _notify):
        def checkout():
            order, _created = create_order(self.customer, [self.product])
            return order.pk

        ids = self._together(checkout, checkout)
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Order.objects.count(), 1)

    @mock.patch("orders.services.notify_order_received")
    def test_simultaneous_downloads_cannot_exceed_limit(self, _notify):
        order, _created = create_order(self.customer, [self.product])
        order.mark_paid(None)
        item = order.items.get()

        def download():
            client = Client()
            client.force_login(self.customer)
            response = client.get(reverse("orders:download", args=[item.pk]))
            if response.streaming:
                b"".join(response.streaming_content)
            return response.status_code

        statuses = self._together(download, download)
        self.assertEqual(sorted(statuses), [200, 302])
        item.refresh_from_db()
        self.assertEqual(item.download_count, 1)

    @mock.patch("orders.services.notify_order_received")
    @mock.patch("payments.services._after_paid")
    @mock.patch("payments.services.notify_payment_submitted")
    def test_approval_and_refund_do_not_deadlock_or_diverge(self, _submitted, _paid, _order):
        order, _created = create_order(self.customer, [self.product])
        payment = submit_manual_payment(order, self.customer, get_provider("paypal_manual"), "CONCURRENT123")

        def approve():
            approve_payment(payment.pk, self.staff)

        def refund():
            try:
                refund_payable(order, self.staff, "Returned through provider")
            except PaymentError:
                pass  # Refund raced before approval and correctly refused an unpaid order.

        self._together(approve, refund)
        order.refresh_from_db()
        payment.refresh_from_db()
        expected = Payment.Status.REFUNDED if order.status == Order.Status.REFUNDED else Payment.Status.COMPLETED
        self.assertEqual(payment.status, expected)
        self.assertIn(order.status, (Order.Status.PAID, Order.Status.REFUNDED))
