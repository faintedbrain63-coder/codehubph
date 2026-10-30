from django.urls import reverse

from catalog.models import Product
from core.models import Testimonial
from core.testing import BaseTestCase
from orders.services import create_order


class LandingPageTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product("Landing Hidden POS", category=Product.Category.MOBILE_APP)

    def test_landing_page_does_not_list_products(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Landing Hidden POS")
        self.assertContains(response, reverse("capstone:request_new") + "?project_type=mobile")
        self.assertNotContains(response, 'href="/products/')
        self.assertContains(response, "Custom development")

    def test_landing_page_loads_motion_assets(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "css/landing.css")
        self.assertContains(response, "js/landing.js")
        self.assertContains(response, 'data-reveal')
        self.assertContains(response, 'data-particles')
        self.assertContains(response, 'data-rotate')

    def test_only_approved_testimonials_are_shown(self):
        Testimonial.objects.create(name="Approved Ana", message="Great service and quick replies.", status="approved")
        Testimonial.objects.create(name="Pending Pia", message="Waiting for review comment.", status="pending")
        Testimonial.objects.create(name="Hidden Hugo", message="Hidden comment from a customer.", status="hidden")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Approved Ana")
        self.assertContains(response, "What our customers say")
        self.assertNotContains(response, "Pending Pia")
        self.assertNotContains(response, "Hidden Hugo")

    def test_section_hidden_when_no_testimonials(self):
        self.assertNotContains(self.client.get(reverse("core:home")), "What our customers say")

    def test_comment_text_is_escaped(self):
        Testimonial.objects.create(name="Eve", message="<script>alert(1)</script> nice", status="approved")
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")


class CustomerTestimonialTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_user("reviewer", school="PUP")
        self.client.force_login(self.customer)
        self.url = reverse("accounts:testimonial")
        self.data = {"rating": "5", "message": "The POS works great in our store and support was fast.", "role": "Owner"}

    def _make_paying_customer(self):
        order, _ = create_order(self.customer, [self.make_product("Reviewed App")])
        order.mark_paid(payment=None)

    def test_requires_login(self):
        self.client.logout()
        self.assertIn(reverse("accounts:login"), self.client.get(self.url)["Location"])

    def test_customer_without_purchase_cannot_submit(self):
        self.assertContains(self.client.get(self.url), "Reviews open after your first confirmed payment")
        self.client.post(self.url, self.data)
        self.assertFalse(Testimonial.objects.exists())

    def test_paying_customer_submits_pending_comment(self):
        self._make_paying_customer()
        response = self.client.post(self.url, self.data)
        self.assertRedirects(response, self.url)
        item = Testimonial.objects.get()
        self.assertEqual(item.user, self.customer)
        self.assertEqual(item.name, self.customer.display_name)
        self.assertEqual(item.status, Testimonial.Status.PENDING)
        self.assertNotContains(self.client.get(reverse("core:home")), self.data["message"])

    def test_short_comment_rejected(self):
        self._make_paying_customer()
        response = self.client.post(self.url, {**self.data, "message": "ok"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Testimonial.objects.exists())

    def test_editing_approved_comment_sends_it_back_for_review(self):
        self._make_paying_customer()
        self.client.post(self.url, self.data)
        Testimonial.objects.update(status=Testimonial.Status.APPROVED)
        self.client.post(self.url, {**self.data, "message": "Updated: still happy after three months of use."})
        item = Testimonial.objects.get()
        self.assertEqual(item.status, Testimonial.Status.PENDING)
        self.assertIsNone(item.approved_at)
        self.assertEqual(Testimonial.objects.count(), 1)

    def test_staff_approval_publishes_comment(self):
        self._make_paying_customer()
        self.client.post(self.url, self.data)
        item = Testimonial.objects.get()

        action_url = reverse("dashboard:testimonial_action", args=[item.pk])
        self.assertEqual(self.client.post(action_url, {"action": "approve"}).status_code, 403)

        self.client.force_login(self.make_user("moderator", staff=True))
        self.client.post(action_url, {"action": "approve"})
        item.refresh_from_db()
        self.assertEqual(item.status, Testimonial.Status.APPROVED)
        self.assertIsNotNone(item.approved_at)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, self.data["message"])
        self.assertContains(response, "Verified customer")

        self.client.post(action_url, {"action": "hide"})
        self.assertNotContains(self.client.get(reverse("core:home")), self.data["message"])

    def test_staff_can_add_comment_and_manage_list(self):
        self.client.force_login(self.make_user("moderator", staff=True))
        response = self.client.post(
            reverse("dashboard:testimonial_create"),
            {"name": "Liza Gomez", "role": "Café owner", "rating": "4",
             "message": "Received by email: the invoice app saves me hours.", "status": "approved"},
        )
        self.assertRedirects(response, reverse("dashboard:testimonial_list"))
        self.assertContains(self.client.get(reverse("dashboard:testimonial_list")), "Liza Gomez")
        self.assertContains(self.client.get(reverse("core:home")), "Liza Gomez")
