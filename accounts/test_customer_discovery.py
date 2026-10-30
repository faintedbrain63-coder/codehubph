from django.urls import reverse
from django.utils import timezone

from capstone.models import CapstoneRequest
from core.testing import BaseTestCase
from orders.models import Order
from orders.services import create_order


class CustomerDiscoveryTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_user("library-customer")
        self.other = self.make_user("other-customer")
        self.client.force_login(self.customer)

    def paid_order(self, name, user=None):
        product = self.make_product(name)
        order, _ = create_order(user or self.customer, [product])
        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.save()
        return order

    def test_purchase_library_is_paginated_and_searchable(self):
        for index in range(13):
            self.paid_order(f"Library Tool {index}")
        self.paid_order("Someone Else Product", self.other)
        url = reverse("accounts:dashboard")
        response = self.client.get(url)
        self.assertEqual(response.context["stats"]["purchases"], 13)
        self.assertEqual(len(response.context["purchases"]), 12)
        self.assertContains(response, "Next page")
        self.assertNotContains(response, "Someone Else Product")
        self.assertEqual(len(self.client.get(url, {"page": 2}).context["purchases"]), 1)
        response = self.client.get(url, {"q": "Library Tool 12"})
        self.assertEqual(len(response.context["purchases"]), 1)
        self.assertEqual(response.context["stats"]["purchases"], 13)
        self.assertContains(response, "1 purchase matching")

    def test_purchase_search_only_returns_own_paid_products(self):
        self.paid_order("Confirmed Product")
        self.paid_order("Hidden Ownership", self.other)
        pending, _ = create_order(self.customer, [self.make_product("Unpaid Product")])
        response = self.client.get(reverse("accounts:dashboard"), {"q": "Product"})
        self.assertEqual([i.product_name for i in response.context["purchases"]], ["Confirmed Product"])
        response = self.client.get(reverse("accounts:dashboard"), {"q": pending.number})
        self.assertEqual(len(response.context["purchases"]), 0)
        self.assertContains(response, "No matching purchases")

    def test_order_history_search_is_distinct_and_owner_scoped(self):
        first, second = self.make_product("Shared Name A"), self.make_product("Shared Name B")
        order, _ = create_order(self.customer, [first, second])
        create_order(self.other, [first])
        response = self.client.get(reverse("orders:list"), {"q": "Shared Name"})
        self.assertEqual(list(response.context["orders"]), [order])
        self.assertContains(response, "history-query")

    def test_history_search_and_status_combine_with_clear_empty_state(self):
        self.paid_order("History Product")
        url = reverse("orders:list")
        response = self.client.get(url, {"q": "History", "status": "pending"})
        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        self.assertContains(response, "No matching orders")
        response = self.client.get(url, {"q": "History", "status": "invalid"})
        self.assertEqual(response.context["status"], "")
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_capstone_catalog_search_combines_topic_technology_and_field(self):
        match = self.make_capstone_project("Library Research", field="web", tech_stack="Django")
        self.make_capstone_project("Robotics", field="iot", tech_stack="Arduino")
        hidden = self.make_capstone_project("Hidden Django", field="web", tech_stack="Django")
        hidden.status = "draft"
        hidden.save()
        response = self.client.get(reverse("capstone:list"), {"q": "dJaNgO", "field": "web"})
        self.assertEqual(list(response.context["projects"]), [match])
        self.assertNotContains(response, hidden.title)
        self.assertContains(response, "1 project found")
        response = self.client.get(reverse("capstone:list"), {"q": "missing"})
        self.assertContains(response, "No matching projects")

    def test_request_history_search_is_owner_scoped(self):
        project = self.make_capstone_project("Research Tracker")
        own = CapstoneRequest.objects.create(customer=self.customer, project=project, school_name="School",
            program="BSIT", customization_notes="Details")
        CapstoneRequest.objects.create(customer=self.other, project=project, school_name="Other school",
            program="BSIT", customization_notes="Other details")
        url = reverse("capstone:my_requests")
        response = self.client.get(url, {"q": "Research", "status": "submitted"})
        self.assertEqual(list(response.context["requests"]), [own])
        response = self.client.get(url, {"q": own.reference, "status": "completed"})
        self.assertContains(response, "No matching requests")

    def test_customer_library_query_count_does_not_grow_with_purchase_count(self):
        self.paid_order("Initial library item")
        # Both renders execute the same bounded queries even as the library grows.
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.client.get(reverse("accounts:dashboard"))  # warm site-settings cache
        with CaptureQueriesContext(connection) as baseline:
            self.client.get(reverse("accounts:dashboard"))
        for index in range(14):
            self.paid_order(f"Additional {index}")
        with CaptureQueriesContext(connection) as expanded:
            response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(len(expanded), len(baseline))
        self.assertEqual(len(response.context["purchases"]), 12)
