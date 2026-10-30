from django.urls import reverse

from catalog.models import Product
from core.testing import BaseTestCase


class ProductVisibilityTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.published = self.make_product("Published POS")
        self.draft = self.make_product("Secret Draft", status=Product.Status.DRAFT)

    def test_published_product_listed_and_viewable(self):
        response = self.client.get(reverse("catalog:list"))
        self.assertContains(response, "Published POS")
        self.assertEqual(self.client.get(self.published.get_absolute_url()).status_code, 200)

    def test_draft_product_hidden_everywhere(self):
        self.assertNotContains(self.client.get(reverse("catalog:list")), "Secret Draft")
        self.assertNotContains(self.client.get(reverse("core:home")), "Secret Draft")
        self.assertEqual(self.client.get(self.draft.get_absolute_url()).status_code, 404)

    def test_publishing_makes_product_appear_in_catalog(self):
        self.draft.status = Product.Status.PUBLISHED
        self.draft.save()
        self.assertIsNotNone(self.draft.published_at)
        self.assertContains(self.client.get(reverse("catalog:list")), "Secret Draft")

    def test_catalog_has_category_tabs(self):
        response = self.client.get(reverse("catalog:list"), {"category": "mobile_app"})
        for label in ("Software", "Mobile Apps"):
            self.assertContains(response, label)
        self.assertNotContains(response, "Web Apps")
        self.assertContains(response, 'href="/products/?category=mobile_app" aria-current="page"', html=False)

    def test_old_web_app_links_go_to_capstone_web_projects(self):
        response = self.client.get(reverse("catalog:list"), {"category": "web_app"})
        self.assertRedirects(response, reverse("capstone:list") + "?field=web", status_code=301)

    def test_capstone_projects_are_not_in_catalog(self):
        project = self.make_capstone_project("Capstone Only System")
        response = self.client.get(reverse("catalog:list") + "?q=Capstone")
        self.assertNotContains(response, "Capstone Only System")
        self.assertEqual(self.client.get(f"/products/{project.slug}/").status_code, 404)

    def test_search_category_and_sort(self):
        self.make_product("Mobile Thing", category=Product.Category.MOBILE_APP, price="100.00")
        response = self.client.get(reverse("catalog:list"), {"category": "mobile_app"})
        self.assertContains(response, "Mobile Thing")
        self.assertNotContains(response, "Published POS")
        response = self.client.get(reverse("catalog:list"), {"sort": "price_asc"})
        names = [p.name for p in response.context["products"]]
        self.assertEqual(names[0], "Mobile Thing")
        response = self.client.get(reverse("catalog:list"), {"q": "POS"})
        self.assertEqual([p.name for p in response.context["products"]], ["Published POS"])

    def test_slug_generated_and_unique(self):
        other = self.make_product("Published POS")
        self.assertNotEqual(other.slug, self.published.slug)
