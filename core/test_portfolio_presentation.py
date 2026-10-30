from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import PortfolioPresentation, PortfolioProject
from core.testing import BaseTestCase


@override_settings(PRODUCT_SALES_ENABLED=False)
class PortfolioPresentationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user("presentation-owner", staff=True)
        self.customer = self.make_user("presentation-customer")

    def payload(self, **overrides):
        data = {"is_visible": "on", "eyebrow": "Selected work", "heading": "Applications I have developed",
                "introduction": "Custom applications for students and organizations.", "display_name": "Example developer",
                "professional_title": "Full-stack developer", "about": "I design and build applications around client requirements.",
                "skills": "Django, PostgreSQL, JavaScript", "location": "Philippines",
                "github_url": "https://github.com/example", "linkedin_url": "https://www.linkedin.com/in/example/"}
        data.update(overrides)
        return data

    def project(self, **overrides):
        values = {"title": "Public portal", "summary": "A portal for organizational workflows.",
                  "project_url": "https://example.org/app", "project_type": "web", "is_published": True}
        values.update(overrides)
        return PortfolioProject.objects.create(**values)

    def test_portfolio_profile_editor_requires_staff_and_csrf(self):
        url = reverse("dashboard:portfolio_presentation")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 403)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        self.assertEqual(csrf_client.post(url, self.payload()).status_code, 403)

    def test_saved_intro_profile_and_links_appear_on_landing_page_and_directory(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("dashboard:portfolio_presentation"), self.payload())
        self.assertRedirects(response, reverse("dashboard:portfolio_presentation"))
        self.client.logout()
        for path in (reverse("core:home"), reverse("core:portfolio_list")):
            response = self.client.get(path)
            for text in ("Applications I have developed", "Example developer", "PostgreSQL", "Philippines",
                         "https://github.com/example", "https://www.linkedin.com/in/example/"):
                self.assertContains(response, text)
            self.assertNotContains(response, "Portfolio setup")
        self.assertEqual(PortfolioPresentation.objects.count(), 1)

    def test_landing_visibility_does_not_unpublish_individual_projects(self):
        project = self.project()
        presentation = PortfolioPresentation.load()
        presentation.is_visible = False
        presentation.save()
        self.assertNotContains(self.client.get(reverse("core:home")), project.title)
        self.assertContains(self.client.get(reverse("core:portfolio_list")), project.title)
        self.assertContains(self.client.get(project.get_absolute_url()), project.title)

    def test_empty_portfolio_setup_is_visible_only_to_staff(self):
        self.assertNotContains(self.client.get(reverse("core:home")), "Introduce yourself and showcase your work")
        self.client.force_login(self.customer)
        self.assertNotContains(self.client.get(reverse("core:home")), "Introduce yourself and showcase your work")
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("core:home")), "Introduce yourself and showcase your work")
        self.assertContains(self.client.get(reverse("dashboard:portfolio_list")), reverse("dashboard:portfolio_presentation"))

    def test_unsafe_profile_links_do_not_change_saved_settings(self):
        self.client.force_login(self.staff)
        for link in ("javascript:alert(1)", "ftp://example.org/profile", "https://secret:pass@example.org/profile"):
            response = self.client.post(reverse("dashboard:portfolio_presentation"), self.payload(github_url=link))
            self.assertEqual(response.status_code, 200)
            self.assertIn("github_url", response.context["form"].errors)
        self.assertEqual(PortfolioPresentation.load().github_url, "")

    def test_featured_public_project_is_highlighted_once_and_drafts_stay_hidden(self):
        normal = self.project(title="Standard project")
        featured = self.project(title="Featured project", is_featured=True)
        self.project(title="Private featured work", is_featured=True, is_published=False)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.context["featured_portfolio_project"], featured)
        self.assertEqual(response.context["portfolio_grid_projects"], [normal])
        self.assertContains(response, 'class="portfolio-case portfolio-case-featured"', count=1)
        self.assertNotContains(response, "Private featured work")

    def test_case_study_details_save_and_render_with_escaped_content(self):
        self.client.force_login(self.staff)
        data = {"title": "Project case study", "project_type": "web", "stage": "completed", "is_published": "on",
                "summary": "An application built for a local organization.", "project_url": "https://example.org/case",
                "industry": "Local government", "contribution": "Full-stack development", "project_year": timezone.localdate().year,
                "challenge": "Requests were handled across separate records.", "solution": "A central portal with staff roles.",
                "outcome": '<script>alert("unsafe")</script> Staff can track requests in one place.',
                "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0", "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "12"}
        response = self.client.post(reverse("dashboard:portfolio_create"), data)
        self.assertEqual(response.status_code, 302)
        project = PortfolioProject.objects.get()
        self.client.logout()
        response = self.client.get(project.get_absolute_url())
        for text in ("The challenge", "The solution", "The outcome", "Local government", "Full-stack development"):
            self.assertContains(response, text)
        self.assertNotContains(response, '<script>alert("unsafe")</script>')
        self.assertContains(response, "&lt;script&gt;")
        self.assertEqual(project.project_domain, "example.org")

    def test_invalid_project_year_is_rejected(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("dashboard:portfolio_create"), {
            "title": "Future project", "project_type": "web", "stage": "ongoing", "summary": "Future work.",
            "project_year": timezone.localdate().year + 2, "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "12",
        })
        self.assertIn("project_year", response.context["form"].errors)
        self.assertFalse(PortfolioProject.objects.exists())
