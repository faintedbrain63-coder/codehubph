from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from capstone.models import CapstoneRequest
from core.testing import BaseTestCase

PDF = b"%PDF-1.4 concept"
OFFICE_XML = b"PK\x03\x04 office"
OFFICE_LEGACY = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 office"


class ConceptFileTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.student = self.make_user("student", school="PUP")
        self.staff = self.make_user("admin1", staff=True)
        self.project = self.make_capstone_project()

    def submit(self, upload=None):
        self.client.force_login(self.student)
        data = {"school_name": "PUP", "program": "BSIT", "customization_notes": "Build a thesis archive."}
        if upload is not None:
            data["concept_file"] = upload
        return self.client.post(reverse("capstone:request_create", args=[self.project.slug]), data)

    def test_request_form_accepts_only_pdf_word_and_powerpoint(self):
        self.client.force_login(self.student)
        page = self.client.get(reverse("capstone:request_create", args=[self.project.slug]))
        self.assertContains(page, 'enctype="multipart/form-data"')
        self.assertContains(page, 'accept=".pdf,.doc,.docx,.ppt,.pptx"')

    def test_customer_can_attach_each_allowed_type(self):
        for name, content in (("concept.pdf", PDF), ("algorithm.docx", OFFICE_XML), ("slides.pptx", OFFICE_XML),
                              ("old.doc", OFFICE_LEGACY), ("old.ppt", OFFICE_LEGACY)):
            with self.subTest(name=name):
                response = self.submit(SimpleUploadedFile(name, content))
                req = CapstoneRequest.objects.latest("pk")
                self.assertRedirects(response, req.get_absolute_url())
                self.assertTrue(req.concept_file.name.startswith("capstone/concepts/"))
                self.assertTrue(req.concept_file.name.endswith("." + name.rsplit(".", 1)[1]))

    def test_request_without_a_file_still_works(self):
        self.submit()
        req = CapstoneRequest.objects.get()
        self.assertFalse(req.concept_file)
        self.client.force_login(self.staff)
        page = self.client.get(reverse("dashboard:capstone_request_detail", args=[req.reference]))
        self.assertContains(page, "The customer did not attach a file.")

    def test_other_types_and_disguised_files_are_rejected(self):
        for upload in (SimpleUploadedFile("notes.txt", b"plain text"), SimpleUploadedFile("setup.exe", b"MZ"),
                       SimpleUploadedFile("page.pdf", b"<html><script>alert(1)</script>"),
                       SimpleUploadedFile("fake.docx", PDF)):
            with self.subTest(name=upload.name):
                response = self.submit(upload)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors.get("concept_file"))
        self.assertFalse(CapstoneRequest.objects.exists())

    @override_settings(MAX_CONCEPT_FILE_MB=0)
    def test_oversized_files_are_rejected(self):
        response = self.submit(SimpleUploadedFile("concept.pdf", PDF))
        self.assertContains(response, "maximum allowed size")
        self.assertFalse(CapstoneRequest.objects.exists())

    def test_staff_view_pdf_in_browser_and_download_office_files(self):
        self.submit(SimpleUploadedFile("concept.pdf", PDF))
        pdf_request = CapstoneRequest.objects.latest("pk")
        self.submit(SimpleUploadedFile("algorithm.docx", OFFICE_XML))
        word_request = CapstoneRequest.objects.latest("pk")
        self.client.force_login(self.staff)

        page = self.client.get(reverse("dashboard:capstone_request_detail", args=[pdf_request.reference]))
        self.assertContains(page, "View PDF")
        pdf = self.client.get(reverse("dashboard:capstone_request_concept_file", args=[pdf_request.reference]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf["Content-Disposition"].startswith("inline"))
        self.assertEqual(pdf["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(pdf.streaming_content), PDF)

        page = self.client.get(reverse("dashboard:capstone_request_detail", args=[word_request.reference]))
        self.assertContains(page, "Word document")
        self.assertContains(page, "Download to open")
        word = self.client.get(reverse("dashboard:capstone_request_concept_file", args=[word_request.reference]))
        self.assertTrue(word["Content-Disposition"].startswith("attachment"))
        self.assertIn(f"{word_request.reference.lower()}-concept.docx", word["Content-Disposition"])

    def test_only_staff_can_open_concept_files(self):
        self.submit(SimpleUploadedFile("concept.pdf", PDF))
        req = CapstoneRequest.objects.get()
        url = reverse("dashboard:capstone_request_concept_file", args=[req.reference])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertIn(reverse("accounts:login"), self.client.get(url)["Location"])

    def test_missing_file_returns_not_found(self):
        self.submit()
        self.client.force_login(self.staff)
        req = CapstoneRequest.objects.get()
        url = reverse("dashboard:capstone_request_concept_file", args=[req.reference])
        self.assertEqual(self.client.get(url).status_code, 404)
