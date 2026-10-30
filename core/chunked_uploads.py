"""Chunked (resumable) uploads for large private files.

Behind Cloudflare a single request body is capped at 100 MB, so staff forms upload big files in
UPLOAD_CHUNK_MB pieces to /manage/uploads/ first (static/js/chunked-upload.js). The form then posts
only a hidden token, `<field>__upload`, and ChunkedUploadFormMixin swaps the finished upload in as
if it had been posted normally. Field validators still run, and storage moves the file into place.
Without JavaScript the plain file input keeps working, subject to the proxy's request limit.
"""

import os
import uuid
from datetime import timedelta
from types import SimpleNamespace

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from core.models import ChunkedUpload
from core.widgets import PrivateFileInput

# Only these model fields accept chunked uploads.
TARGETS = frozenset({
    "catalog.Product.file",
    "capstone.CapstoneProject.source_code",
    "capstone.CapstoneProject.documentation",
    "capstone.CapstoneRequest.delivered_source",
    "capstone.CapstoneRequest.delivered_documentation",
})

TOKEN_SUFFIX = "__upload"


def chunk_bytes():
    return settings.UPLOAD_CHUNK_MB * 1024 * 1024


def validate_upload(target, filename, size):
    """Run the destination field's validators (extension, size) before any bytes are accepted."""
    if target not in TARGETS:
        raise ValidationError("Uploads are not allowed for this field.")
    model_label, field_name = target.rsplit(".", 1)
    field = apps.get_model(model_label)._meta.get_field(field_name)
    candidate = SimpleNamespace(name=filename, size=size)
    for validator in field.validators:
        validator(candidate)


def expire_stale_uploads():
    """Remove uploads untouched for UPLOAD_SESSION_HOURS (abandoned, or never attached to a form)."""
    cutoff = timezone.now() - timedelta(hours=settings.UPLOAD_SESSION_HOURS)
    stale = list(ChunkedUpload.objects.filter(updated_at__lt=cutoff))
    for upload in stale:
        upload.discard()
    return len(stale)


class ChunkedUploadedFile(UploadedFile):
    """A completed upload presented to Django forms as an uploaded file.

    `temporary_file_path()` lets FileSystemStorage move the file instead of copying it,
    and the file is only opened if something actually reads it.
    """

    def __init__(self, path, name, size):
        self._path = path
        self._file = None
        super().__init__(None, name, "application/octet-stream", size, None)

    @property
    def file(self):
        if self._file is None:
            self._file = open(self._path, "rb")
        return self._file

    @file.setter
    def file(self, value):
        self._file = value

    def temporary_file_path(self):
        return self._path

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None


class ChunkedFileInput(PrivateFileInput):
    """Private file input that also carries the token of a file already uploaded in chunks."""

    template_name = "widgets/chunked_file_input.html"
    upload = None  # set per form instance by ChunkedUploadFormMixin

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["token_name"] = name + TOKEN_SUFFIX
        context["widget"]["upload"] = self.upload
        if self.upload:
            # The file is already on the server; don't make the browser demand it again.
            context["widget"]["attrs"].pop("required", None)
        return context


class ChunkedUploadFormMixin:
    """Lets the fields named in `chunked_fields` receive a completed ChunkedUpload by token.

    Pass `user=request.user`; tokens are only honoured for the user who uploaded them.
    """

    chunked_fields = ()

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._chunked_uploads = {}
        self._chunked_errors = {}
        model_label = self._meta.model._meta.label
        for name in self.chunked_fields:
            target = f"{model_label}.{name}"
            widget = self.fields[name].widget
            widget.attrs["data-chunked-upload"] = target
            widget.upload = None
            token = self.data.get(name + TOKEN_SUFFIX, "") if self.is_bound else ""
            if not token or self.files.get(name):
                continue  # a directly posted file takes precedence
            upload = self._resolve(token, user, target)
            if upload is None:
                self._chunked_errors[name] = "The uploaded file has expired or is not available. Select it again."
                continue
            widget.upload = upload
            self._chunked_uploads[name] = upload
            self.files = self.files.copy()
            self.files[name] = ChunkedUploadedFile(upload.part_path, upload.filename, upload.size)

    @staticmethod
    def _resolve(token, user, target):
        try:
            pk = uuid.UUID(str(token))
        except ValueError:
            return None
        if user is None or not user.is_authenticated:
            return None
        upload = ChunkedUpload.objects.filter(
            pk=pk, user=user, target=target, completed_at__isnull=False
        ).first()
        if upload is None or not os.path.exists(upload.part_path):
            return None
        return upload

    def clean(self):
        cleaned = super().clean()
        for name, message in self._chunked_errors.items():
            self.add_error(name, message)
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit)
        if commit:
            self.release_chunked_uploads()
        return instance

    def release_chunked_uploads(self):
        """Close and remove uploads now stored on the instance (any leftover copy is deleted)."""
        for name, upload in self._chunked_uploads.items():
            uploaded = self.files.get(name)
            if isinstance(uploaded, ChunkedUploadedFile):
                uploaded.close()
            upload.discard()
        self._chunked_uploads = {}

