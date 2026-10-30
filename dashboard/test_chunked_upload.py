import os
from datetime import timedelta

from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from capstone.models import CapstoneProject, CapstoneRequest
from catalog.models import Product
from core.models import ChunkedUpload
from core.testing import BaseTestCase, zip_upload

PAYLOAD = b"PK\x05\x06" + bytes(range(256)) * 40  # 10,244 bytes


class ChunkedUploadTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user("boss", staff=True)
        self.client.force_login(self.staff)

    def start(self, target="catalog.Product.file", filename="big-app.zip", size=len(PAYLOAD)):
        return self.client.post(
            reverse("dashboard:upload_start"), {"target": target, "filename": filename, "size": size},
            content_type="application/json",
        )

    def send(self, upload_id, start, end, payload=PAYLOAD, total=None):
        return self.client.post(
            reverse("dashboard:upload_chunk", args=[upload_id]), payload[start:end + 1],
            content_type="application/octet-stream",
            headers={"Content-Range": f"bytes {start}-{end}/{total or len(payload)}"},
        )

    def upload(self, payload=PAYLOAD, **start_kwargs):
        upload_id = self.start(size=len(payload), **start_kwargs).json()["id"]
        step = 4000
        for start in range(0, len(payload), step):
            response = self.send(upload_id, start, min(start + step, len(payload)) - 1, payload)
            self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["complete"])
        return upload_id

    @staticmethod
    def product_data(**extra):
        data = {
            "name": "Chunked Product", "category": "software", "short_description": "Short summary",
            "description": "Full description", "price": "700.00", "version": "1.0", "status": "draft",
            "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0", "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "12",
        }
        data.update(extra)
        return data

    def test_chunks_assemble_into_the_saved_private_file(self):
        upload_id = self.upload()
        part_path = ChunkedUpload.objects.get(pk=upload_id).part_path
        response = self.client.post(reverse("dashboard:product_create"), self.product_data(file__upload=upload_id))
        self.assertRedirects(response, reverse("dashboard:product_list"))
        product = Product.objects.get(name="Chunked Product")
        with product.file.open("rb") as stored:
            self.assertEqual(stored.read(), PAYLOAD)
        self.assertEqual(product.file_size, len(PAYLOAD))
        self.assertTrue(product.file.name.startswith("products/files/") and product.file.name.endswith(".zip"))
        self.assertFalse(ChunkedUpload.objects.exists())
        self.assertFalse(os.path.exists(part_path))

    def test_start_runs_the_destination_field_validators(self):
        self.assertIn("not allowed", self.start(filename="virus.php").json()["error"])
        with override_settings(MAX_PRODUCT_FILE_MB=1):
            self.assertIn("maximum", self.start(size=2 * 1024 * 1024).json()["error"])
        self.assertEqual(self.start(target="accounts.User.password").status_code, 400)
        self.assertEqual(self.start(target="capstone.CapstoneProject.documentation", filename="a.exe").status_code, 400)
        self.assertEqual(self.start(size=0).status_code, 400)
        self.assertFalse(ChunkedUpload.objects.exists())

    def test_staff_only(self):
        self.client.force_login(self.make_user("customer"))
        self.assertEqual(self.start().status_code, 403)
        self.client.logout()
        self.assertEqual(self.start().status_code, 302)

    def test_out_of_order_and_retried_chunks(self):
        upload_id = self.start().json()["id"]
        self.assertEqual(self.send(upload_id, 0, 999).json()["received"], 1000)
        gap = self.send(upload_id, 2000, 2999)
        self.assertEqual(gap.status_code, 409)
        self.assertEqual(gap.json()["received"], 1000)
        # A retry of an already stored chunk is acknowledged without changing anything.
        self.assertEqual(self.send(upload_id, 0, 999).json()["received"], 1000)
        status = self.client.get(reverse("dashboard:upload_chunk", args=[upload_id])).json()
        self.assertEqual((status["received"], status["complete"]), (1000, False))

    @override_settings(UPLOAD_CHUNK_MB=1)
    def test_chunks_larger_than_the_limit_are_refused(self):
        payload = b"x" * (1024 * 1024 + 1)
        upload_id = self.start(size=len(payload)).json()["id"]
        self.assertEqual(self.send(upload_id, 0, len(payload) - 1, payload).status_code, 400)
        self.assertEqual(ChunkedUpload.objects.get(pk=upload_id).received, 0)

    def test_chunk_must_match_upload_size(self):
        upload_id = self.start().json()["id"]
        self.assertEqual(self.send(upload_id, 0, 99, total=99999).status_code, 400)

    def test_other_users_and_incomplete_tokens_are_rejected(self):
        upload_id = self.upload()
        self.client.force_login(self.make_user("boss2", staff=True))
        response = self.client.post(reverse("dashboard:product_create"), self.product_data(file__upload=upload_id))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.exists())
        self.assertEqual(self.client.get(reverse("dashboard:upload_chunk", args=[upload_id])).status_code, 404)

        self.client.force_login(self.staff)
        partial = self.start().json()["id"]
        self.send(partial, 0, 99)
        response = self.client.post(reverse("dashboard:product_create"), self.product_data(file__upload=partial))
        self.assertContains(response, "expired or is not available")
        self.assertFalse(Product.objects.exists())

    def test_token_for_another_field_is_rejected(self):
        upload_id = self.upload(target="capstone.CapstoneProject.source_code")
        response = self.client.post(reverse("dashboard:product_create"), self.product_data(file__upload=upload_id))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.exists())

    def test_invalid_form_keeps_the_upload_ready_for_resubmission(self):
        upload_id = self.upload()
        response = self.client.post(reverse("dashboard:product_create"), self.product_data(name="", file__upload=upload_id))
        self.assertContains(response, "Uploaded and ready to save")
        self.assertContains(response, f'value="{upload_id}"')
        self.assertTrue(ChunkedUpload.objects.filter(pk=upload_id).exists())
        response = self.client.post(reverse("dashboard:product_create"), self.product_data(file__upload=upload_id))
        self.assertRedirects(response, reverse("dashboard:product_list"))

    def test_direct_file_upload_still_works(self):
        response = self.client.post(reverse("dashboard:product_create"), self.product_data(file=zip_upload()))
        self.assertRedirects(response, reverse("dashboard:product_list"))

    def test_capstone_project_and_deliverables_accept_chunked_files(self):
        source = self.upload(target="capstone.CapstoneProject.source_code", filename="system.zip")
        docs = self.upload(payload=b"%PDF-1.4 " + b"d" * 5000, target="capstone.CapstoneProject.documentation",
                           filename="manual.pdf")
        response = self.client.post(reverse("dashboard:capstone_project_create"), {
            "title": "Chunked Capstone", "field": "web", "short_description": "Short", "description": "Full",
            "suggested_price": "12000.00", "status": "draft", "source_code__upload": source, "documentation__upload": docs,
        })
        self.assertRedirects(response, reverse("dashboard:capstone_project_list"))
        project = CapstoneProject.objects.get(title="Chunked Capstone")
        self.assertTrue(project.documentation.name.endswith(".pdf"))

        req = CapstoneRequest.objects.create(
            customer=self.make_user("student"), project=project, school_name="PUP", program="BSIT",
            customization_notes="Add reports",
        )
        delivered = self.upload(target="capstone.CapstoneRequest.delivered_source", filename="custom.zip")
        self.client.post(reverse("dashboard:capstone_request_deliverables", args=[req.reference]),
                         {"delivered_source__upload": delivered})
        req.refresh_from_db()
        with req.delivered_source.open("rb") as stored:
            self.assertEqual(stored.read(), PAYLOAD)

    def test_cancel_and_expiry_remove_partial_files(self):
        upload_id = self.start().json()["id"]
        part = ChunkedUpload.objects.get(pk=upload_id).part_path
        self.send(upload_id, 0, 99)
        self.assertEqual(self.client.delete(reverse("dashboard:upload_chunk", args=[upload_id])).status_code, 200)
        self.assertFalse(os.path.exists(part))

        stale_id = self.start().json()["id"]
        stale = ChunkedUpload.objects.get(pk=stale_id)
        ChunkedUpload.objects.filter(pk=stale_id).update(updated_at=timezone.now() - timedelta(hours=25))
        call_command("cleanup_uploads", stdout=open(os.devnull, "w"))
        self.assertFalse(ChunkedUpload.objects.exists())
        self.assertFalse(os.path.exists(stale.part_path))

    @override_settings(UPLOAD_MAX_ACTIVE_SESSIONS=2)
    def test_unfinished_uploads_are_capped_per_user(self):
        self.start()
        self.start()
        self.assertEqual(self.start().status_code, 429)

    def test_csrf_is_enforced_and_header_token_accepted(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        client.get(reverse("dashboard:product_create"))
        token = client.cookies["csrftoken"].value
        url = reverse("dashboard:upload_start")
        body = {"target": "catalog.Product.file", "filename": "a.zip", "size": len(PAYLOAD)}
        self.assertEqual(client.post(url, body, content_type="application/json").status_code, 403)
        upload_id = client.post(url, body, content_type="application/json", headers={"X-CSRFToken": token}).json()["id"]
        chunk = reverse("dashboard:upload_chunk", args=[upload_id])
        headers = {"Content-Range": f"bytes 0-99/{len(PAYLOAD)}"}
        self.assertEqual(client.post(chunk, PAYLOAD[:100], content_type="application/octet-stream",
                                     headers=headers).status_code, 403)
        response = client.post(chunk, PAYLOAD[:100], content_type="application/octet-stream",
                               headers={**headers, "X-CSRFToken": token})
        self.assertEqual(response.json()["received"], 100)

    def test_upload_form_renders_chunk_hooks(self):
        response = self.client.get(reverse("dashboard:product_create"))
        self.assertContains(response, 'data-chunked-upload="catalog.Product.file"')
        self.assertContains(response, 'name="file__upload"')
        self.assertContains(response, "js/chunked-upload.js")
