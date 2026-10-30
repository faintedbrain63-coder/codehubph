import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from capstone.models import CapstoneRequest
from core.models import PortfolioPresentation, PortfolioProject, PortfolioScreenshot, Testimonial
from core.testing import BaseTestCase, png_upload


@override_settings(PRODUCT_SALES_ENABLED=False)
class PortfolioTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user("portfolio-owner", staff=True, is_superuser=True)
        self.customer = self.make_user("portfolio-client")
        self.other = self.make_user("other-client")
        self.client.force_login(self.staff)

    def payload(self, **overrides):
        data = {"title": "Community services portal", "project_type": "web", "stage": "completed",
                "summary": "A portal for service requests and records.", "description": "An example project description.",
                "project_url": "https://example.org/portal", "customer": self.customer.pk,
                "is_published": "on", "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "12"}
        data.update(overrides)
        return data

    def project(self, **overrides):
        data = {"title": "Community services portal", "project_type": "web", "stage": "completed",
                "summary": "An example customer project.", "project_url": "https://example.org/portal",
                "customer": self.customer, "is_published": True}
        data.update(overrides)
        return PortfolioProject.objects.create(**data)

    def review_data(self, **overrides):
        data = {"name": "Client initials", "rating": "5", "message": "The project meets our needs and the support was helpful.",
                "role": "Project coordinator", "publication_permission": "on"}
        data.update(overrides)
        return data

    def test_portfolio_crud_requires_staff_and_csrf(self):
        project = self.project()
        paths = [reverse("dashboard:portfolio_list"), reverse("dashboard:portfolio_create"),
                 reverse("dashboard:portfolio_edit", args=[project.pk])]
        self.client.logout()
        for url in paths:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.customer)
        for url in paths:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse("dashboard:portfolio_delete", args=[project.pk])).status_code, 403)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        self.assertEqual(csrf_client.post(reverse("dashboard:portfolio_create"), self.payload()).status_code, 403)

    def test_screenshots_open_in_a_lightbox(self):
        project = self.project(slug="battlespace1")
        PortfolioScreenshot.objects.create(project=project, image=png_upload("one.png"), caption="Command view", sort_order=0)
        PortfolioScreenshot.objects.create(project=project, image=png_upload("two.png"), caption="Map view", sort_order=1)
        self.client.logout()
        response = self.client.get(project.get_absolute_url())
        self.assertContains(response, 'id="portfolio-lightbox"')
        self.assertContains(response, 'data-lightbox-open="0"')
        self.assertContains(response, 'data-lightbox-open="1"')
        self.assertContains(response, "Command view")
        self.assertContains(response, "Map view")
        self.assertContains(response, "js/portfolio-lightbox.js")
        self.assertNotContains(response, "target=\"_blank\" rel=\"noopener\"><img")

    def test_web_project_create_read_update_and_publication(self):
        response = self.client.post(reverse("dashboard:portfolio_create"), self.payload())
        self.assertRedirects(response, reverse("dashboard:portfolio_list"))
        project = PortfolioProject.objects.get()
        self.assertContains(self.client.get(reverse("dashboard:portfolio_list")), project.title)
        self.assertContains(self.client.get(project.get_absolute_url()), "https://example.org/portal")
        response = self.client.post(reverse("dashboard:portfolio_edit", args=[project.pk]), self.payload(
            title="Updated portal", stage="ongoing", project_url="https://example.org/new", save_action="continue"))
        self.assertRedirects(response, reverse("dashboard:portfolio_edit", args=[project.pk]))
        project.refresh_from_db()
        self.assertEqual(project.title, "Updated portal")
        self.assertEqual(project.stage, "ongoing")
        self.client.logout()
        self.assertContains(self.client.get(reverse("core:home")), "Updated portal")
        self.assertContains(self.client.get(reverse("core:portfolio_list")), "https://example.org/new")

    def test_web_links_are_required_for_publication_and_reject_unsafe_schemes(self):
        for url in ("", "javascript:alert(1)", "ftp://example.org/app", "https://secret:password@example.org/app"):
            response = self.client.post(reverse("dashboard:portfolio_create"), self.payload(project_url=url))
            self.assertEqual(response.status_code, 200)
            self.assertIn("project_url", response.context["form"].errors)
        self.assertFalse(PortfolioProject.objects.exists())
        self.assertEqual(self.client.post(reverse("dashboard:portfolio_create"), self.payload(
            project_url="", is_published="")).status_code, 302)

    def test_mobile_and_software_require_screenshots_only_when_published(self):
        for project_type in ("mobile", "software"):
            response = self.client.post(reverse("dashboard:portfolio_create"), self.payload(
                project_type=project_type, project_url=""))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["formset"].non_form_errors())
            data = self.payload(title=f"Custom {project_type}", project_type=project_type, project_url="",
                                **{"images-TOTAL_FORMS": "1", "images-0-image": png_upload(), "images-0-sort_order": "0"})
            self.assertEqual(self.client.post(reverse("dashboard:portfolio_create"), data).status_code, 302)
        self.assertEqual(PortfolioScreenshot.objects.count(), 2)

    def test_invalid_images_and_too_many_screenshots_do_not_save_partial_projects(self):
        invalid = SimpleUploadedFile("bad.png", b"This is not a real image", content_type="image/png")
        response = self.client.post(reverse("dashboard:portfolio_create"), self.payload(
            **{"images-TOTAL_FORMS": "1", "images-0-image": invalid, "images-0-sort_order": "0"}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["formset"].errors)
        response = self.client.post(reverse("dashboard:portfolio_create"), self.payload(**{"images-TOTAL_FORMS": "13"}))
        self.assertTrue(response.context["formset"].non_form_errors())
        self.assertFalse(PortfolioProject.objects.exists())

    def test_drafts_and_their_images_are_private_to_staff_and_linked_customer(self):
        project = self.project(is_published=False)
        screenshot = PortfolioScreenshot.objects.create(project=project, image=png_upload())
        for user, status in ((None, 404), (self.other, 404), (self.customer, 200), (self.staff, 200)):
            self.client.logout()
            if user:
                self.client.force_login(user)
            self.assertEqual(self.client.get(project.get_absolute_url()).status_code, status)
            response = self.client.get(screenshot.get_absolute_url())
            self.assertEqual(response.status_code, status)
            if status == 200:
                self.assertEqual(response["Cache-Control"], "private, no-store")
                b"".join(response.streaming_content)
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("core:home")), project.title)
        self.assertNotContains(self.client.get(reverse("core:portfolio_list")), project.title)

    def test_existing_private_screenshots_render_in_both_admin_editors(self):
        project = self.project(project_type="mobile", project_url="")
        screenshot = PortfolioScreenshot.objects.create(project=project, image=png_upload())
        for url in (reverse("dashboard:portfolio_edit", args=[project.pk]),
                    reverse("admin:core_portfolioproject_change", args=[project.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
        self.assertContains(self.client.get(reverse("dashboard:portfolio_edit", args=[project.pk])), screenshot.get_absolute_url())

    def test_request_link_selects_customer_and_rejects_mismatched_account(self):
        req = CapstoneRequest.objects.create(customer=self.customer, request_title="Custom brief",
            client_type="business", project_type="web", school_name="Example business", customization_notes="Records portal")
        response = self.client.post(reverse("dashboard:portfolio_create"), self.payload(request=req.pk, customer=self.other.pk))
        self.assertIn("customer", response.context["form"].errors)
        self.assertEqual(self.client.post(reverse("dashboard:portfolio_create"), self.payload(
            request=req.pk, customer="")).status_code, 302)
        self.assertEqual(PortfolioProject.objects.get().customer_id, self.customer.pk)

    def test_filters_and_public_landings_hide_customer_email_and_show_project_stage(self):
        self.project(title="Public web project")
        self.project(title="Private project name", is_published=False)
        self.project(title="Mobile field app", project_type="mobile", stage="ongoing", project_url="")
        self.client.logout()
        response = self.client.get(reverse("core:portfolio_list") + "?project_type=mobile&stage=ongoing")
        self.assertContains(response, "Mobile field app")
        self.assertNotContains(response, "Public web project")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Past and ongoing projects")
        self.assertContains(response, "Ongoing")
        self.assertNotContains(response, self.customer.email)
        self.assertNotContains(response, "Private project name")

    def test_only_assigned_customer_can_write_review_and_permission_is_required(self):
        project = self.project()
        url = reverse("accounts:project_testimonial", args=[project.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.review_data()).status_code, 404)
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse("accounts:project_reviews")), project.title)
        response = self.client.post(url, self.review_data(publication_permission=""))
        self.assertIn("publication_permission", response.context["form"].errors)
        self.assertFalse(Testimonial.objects.exists())

    def test_project_review_is_pending_then_approved_and_edits_return_to_pending(self):
        project = self.project()
        self.client.force_login(self.customer)
        url = reverse("accounts:project_testimonial", args=[project.pk])
        start = timezone.now()
        self.assertRedirects(self.client.post(url, self.review_data(status="approved", user=self.other.pk)), url)
        review = Testimonial.objects.get()
        self.assertEqual(review.user_id, self.customer.pk)
        self.assertEqual(review.status, "pending")
        self.assertGreaterEqual(review.publication_consented_at, start)
        self.assertNotContains(self.client.get(reverse("core:home")), review.message)
        self.client.force_login(self.staff)
        self.client.post(reverse("dashboard:testimonial_action", args=[review.pk]), {"action": "approve"})
        self.client.logout()
        self.assertContains(self.client.get(reverse("core:home")), review.message)
        self.assertContains(self.client.get(project.get_absolute_url()), review.name)
        self.client.force_login(self.customer)
        self.client.post(url, self.review_data(message="Updated review after using the project for several weeks."))
        review.refresh_from_db()
        self.assertEqual(Testimonial.objects.count(), 1)
        self.assertEqual(review.status, "pending")
        self.assertIsNone(review.approved_at)

    def test_one_customer_can_review_each_project_and_keep_a_general_review(self):
        self.client.force_login(self.customer)
        for title in ("First project", "Second project"):
            project = self.project(title=title)
            self.client.post(reverse("accounts:project_testimonial", args=[project.pk]), self.review_data())
        Testimonial.objects.create(user=self.customer, name="Client", message="An older general service review.")
        self.assertEqual(Testimonial.objects.filter(user=self.customer).count(), 3)

    def test_private_project_reviews_remain_hidden_even_if_approved(self):
        project = self.project(is_published=False)
        review = Testimonial.objects.create(portfolio_project=project, user=self.customer, name="Private client",
            message="Confidential project feedback must stay hidden.", status="approved")
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("core:home")), review.message)
        PortfolioProject.objects.filter(pk=project.pk).update(is_published=True)
        self.assertContains(self.client.get(reverse("core:home")), review.message)

    def test_moderation_preserves_customer_authored_project_review(self):
        project = self.project()
        review = Testimonial.objects.create(portfolio_project=project, user=self.customer, name="Original name",
            message="The original comment written by the customer.", rating=3)
        response = self.client.post(reverse("dashboard:testimonial_edit", args=[review.pk]), {
            "name": "Forged name", "message": "Different text", "rating": "5", "role": "", "status": "approved",
            "portfolio_project": project.pk,
        })
        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.assertEqual(review.name, "Original name")
        self.assertEqual(review.rating, 3)
        self.assertEqual(review.message, "The original comment written by the customer.")
        self.assertEqual(review.status, "approved")

    def test_delete_project_removes_its_reviews_and_images_but_preserves_request(self):
        req = CapstoneRequest.objects.create(customer=self.customer, request_title="Retained project request",
            school_name="Organization", customization_notes="Example brief")
        project = self.project(request=req)
        shot = PortfolioScreenshot.objects.create(project=project, image=png_upload())
        storage, name = shot.image.storage, shot.image.name
        Testimonial.objects.create(portfolio_project=project, user=self.customer, name="Client", message="A real project review.")
        self.assertEqual(self.client.get(reverse("dashboard:portfolio_delete", args=[project.pk])).status_code, 405)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("dashboard:portfolio_delete", args=[project.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PortfolioProject.objects.exists())
        self.assertFalse(PortfolioScreenshot.objects.exists())
        self.assertFalse(Testimonial.objects.exists())
        self.assertTrue(CapstoneRequest.objects.filter(pk=req.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_removing_a_screenshot_deletes_its_file(self):
        project = self.project()
        kept = PortfolioScreenshot.objects.create(project=project, image=png_upload("kept.png"), sort_order=0)
        removed = PortfolioScreenshot.objects.create(project=project, image=png_upload("removed.png"), sort_order=1)
        kept_name, removed_name = kept.image.name, removed.image.name
        storage = removed.image.storage
        self.assertTrue(storage.exists(kept_name))
        self.assertTrue(storage.exists(removed_name))
        edit_page = self.client.get(reverse("dashboard:portfolio_edit", args=[project.pk]))
        self.assertContains(edit_page, "Delete this picture")
        self.assertContains(edit_page, "removed from the server")
        data = self.payload(**{
            "images-TOTAL_FORMS": "3", "images-INITIAL_FORMS": "2",
            "images-0-id": str(kept.pk), "images-0-caption": "", "images-0-sort_order": "0",
            "images-1-id": str(removed.pk), "images-1-caption": "", "images-1-sort_order": "1",
            "images-1-DELETE": "on",
            "images-2-caption": "", "images-2-sort_order": "0",
        })
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("dashboard:portfolio_edit", args=[project.pk]), data)
        self.assertRedirects(response, reverse("dashboard:portfolio_list"))
        self.assertTrue(PortfolioScreenshot.objects.filter(pk=kept.pk).exists())
        self.assertFalse(PortfolioScreenshot.objects.filter(pk=removed.pk).exists())
        self.assertTrue(storage.exists(kept_name))
        self.assertFalse(storage.exists(removed_name))

    def test_replacing_a_screenshot_deletes_the_previous_file(self):
        project = self.project()
        shot = PortfolioScreenshot.objects.create(project=project, image=png_upload("original.png"))
        storage, previous = shot.image.storage, shot.image.name
        data = self.payload(**{
            "images-TOTAL_FORMS": "1", "images-INITIAL_FORMS": "1",
            "images-0-id": str(shot.pk), "images-0-caption": "Updated", "images-0-sort_order": "0",
            "images-0-image": png_upload("replacement.png"),
        })
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("dashboard:portfolio_edit", args=[project.pk]), data)
        self.assertRedirects(response, reverse("dashboard:portfolio_list"))
        shot.refresh_from_db()
        self.assertNotEqual(shot.image.name, previous)
        self.assertTrue(storage.exists(shot.image.name))
        self.assertFalse(storage.exists(previous))

    def test_portfolio_content_and_review_text_are_escaped(self):
        project = self.project(title='<script>alert("project")</script>')
        Testimonial.objects.create(portfolio_project=project, user=self.customer, name="Client",
            message='<script>alert("review")</script> Feedback for this project.', status="approved")
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, '<script>alert("project")</script>')
        self.assertNotContains(response, '<script>alert("review")</script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_portfolio_pages_render_and_optional_visual_previews(self):
        import io
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (960, 600), "#f1f4f9")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 210, 600), fill="#19253c")
        draw.rectangle((245, 35, 920, 100), fill="#ffffff")
        for index in range(3):
            draw.rounded_rectangle((245 + index * 225, 135, 445 + index * 225, 250), radius=12, fill="#dcdafb")
        for index in range(5):
            draw.rectangle((245, 300 + index * 45, 920, 325 + index * 45), fill="#ffffff")
        file = io.BytesIO()
        image.save(file, "PNG")
        presentation = PortfolioPresentation.load()
        presentation.display_name = "Example developer"
        presentation.professional_title = "Full-stack developer"
        presentation.about = "I build web applications, mobile apps and software around the workflows of students and organizations. My work spans planning, implementation and delivery."
        presentation.skills = "Web development, Mobile applications, Database design, System integration"
        presentation.location = "Philippines"
        presentation.save()
        web = self.project(title="Community service portal", stage="ongoing", is_featured=True, industry="Local government",
            contribution="Full-stack development", project_year=2026, tech_stack="Django, PostgreSQL, Bootstrap",
            description="A shared workspace for service requests, records and staff coordination.",
            challenge="Staff needed a consistent way to receive and follow up community service requests.",
            solution="A role-based portal with request tracking, document records and reporting.",
            outcome="Service requests and staff status updates are brought together in one interface.")
        mobile = self.project(title="Field reporting mobile app", project_type="mobile", project_url="",
            industry="Field operations", tech_stack="Flutter, REST API")
        software = self.project(title="Inventory desktop system", project_type="software", project_url="",
            industry="Business operations", tech_stack="Python, SQLite")
        for project in (web, mobile, software):
            screenshot_bytes = file.getvalue()
            if project == mobile:
                screen = Image.new("RGB", (540, 1080), "#f3f5fa")
                pen = ImageDraw.Draw(screen)
                pen.rectangle((0, 0, 540, 185), fill="#253550")
                pen.rounded_rectangle((32, 220, 508, 370), radius=16, fill="#dfdcfa")
                for row in range(4):
                    pen.rounded_rectangle((32, 410 + row * 128, 508, 510 + row * 128), radius=12, fill="#ffffff")
                buffer = io.BytesIO()
                screen.save(buffer, "PNG")
                screenshot_bytes = buffer.getvalue()
            PortfolioScreenshot.objects.create(project=project, image=SimpleUploadedFile("example.png", screenshot_bytes, content_type="image/png"))
        Testimonial.objects.create(portfolio_project=web, user=self.customer, name="Example client",
            message="The project gives our team a clear way to manage service requests.", status="approved",
            publication_consented_at=timezone.now())
        root = Path(settings.BASE_DIR) / ".qa/site"
        export = os.environ.get("CODEHUB_RENDER_PORTFOLIO") == "1"
        if export:
            (root / "previews/portfolio-images").mkdir(parents=True, exist_ok=True)
            shutil.copytree(Path(settings.BASE_DIR) / "static", root / "static", dirs_exist_ok=True)
            for shot in PortfolioScreenshot.objects.all():
                with shot.image.open("rb") as data:
                    (root / "previews/portfolio-images" / f"{shot.pk}.png").write_bytes(data.read())
        previews = ((None, {"public-storefront": reverse("core:home"), "portfolio-list": reverse("core:portfolio_list"),
                          "portfolio-detail": web.get_absolute_url(), "public-register": reverse("accounts:register"),
                          "public-privacy": reverse("core:privacy"), "public-license": reverse("core:license")}),
                    (self.staff, {"portfolio-admin": reverse("dashboard:portfolio_list"),
                                  "portfolio-presentation": reverse("dashboard:portfolio_presentation"),
                                  "portfolio-form": reverse("dashboard:portfolio_edit", args=[web.pk])}),
                    (self.customer, {"project-review-list": reverse("accounts:project_reviews"),
                                     "project-review-form": reverse("accounts:project_testimonial", args=[web.pk])}))
        for user, paths in previews:
            self.client.logout()
            if user:
                type(user).objects.filter(pk=user.pk).update(onboarding_completed_at=timezone.now())
                self.client.force_login(user)
            for filename, url in paths.items():
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                if export:
                    html = response.content.decode()
                    for shot in PortfolioScreenshot.objects.all():
                        html = html.replace(shot.get_absolute_url(), f"/previews/portfolio-images/{shot.pk}.png")
                    preview_script = '<script>addEventListener("load",function(){if(location.hash==="#privacy")new bootstrap.Modal(document.getElementById("legal-privacy")).show();if(location.hash==="#license")new bootstrap.Modal(document.getElementById("legal-license")).show();});</script>'
                    (root / "previews" / f"{filename}.html").write_text(html.replace("</body>", preview_script + "</body>"), encoding="utf-8")
