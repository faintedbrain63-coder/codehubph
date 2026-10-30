"""Upload validation and safe filename generation."""

import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from django.utils.deconstruct import deconstructible


def _extension(name):
    return os.path.splitext(name)[1].lower().lstrip(".")


@deconstructible
class AllowedExtensionValidator:
    """Checks the file extension against a list stored in settings (by name)."""

    def __init__(self, setting_name):
        self.setting_name = setting_name

    def __call__(self, value):
        allowed = [e.lower().strip(".") for e in getattr(settings, self.setting_name)]
        ext = _extension(value.name)
        if ext not in allowed:
            raise ValidationError(
                "Files of type “.%(ext)s” are not allowed. Allowed types: %(allowed)s.",
                params={"ext": ext or "?", "allowed": ", ".join(allowed)},
                code="invalid_extension",
            )

    def __eq__(self, other):
        return isinstance(other, AllowedExtensionValidator) and self.setting_name == other.setting_name


@deconstructible
class MaxFileSizeValidator:
    """Checks the file size against a megabyte limit stored in settings (by name)."""

    def __init__(self, setting_name):
        self.setting_name = setting_name

    def __call__(self, value):
        limit = getattr(settings, self.setting_name) * 1024 * 1024
        if value.size > limit:
            raise ValidationError(
                "This file is %(size)s. The maximum allowed size is %(limit)s.",
                params={"size": filesizeformat(value.size), "limit": filesizeformat(limit)},
                code="file_too_large",
            )

    def __eq__(self, other):
        return isinstance(other, MaxFileSizeValidator) and self.setting_name == other.setting_name


validate_product_file_ext = AllowedExtensionValidator("ALLOWED_PRODUCT_FILE_EXTENSIONS")
validate_document_ext = AllowedExtensionValidator("ALLOWED_DOCUMENT_EXTENSIONS")
validate_image_ext = AllowedExtensionValidator("ALLOWED_IMAGE_EXTENSIONS")
validate_product_file_size = MaxFileSizeValidator("MAX_PRODUCT_FILE_MB")
validate_image_size = MaxFileSizeValidator("MAX_IMAGE_MB")

validate_concept_file_ext = AllowedExtensionValidator("ALLOWED_CONCEPT_FILE_EXTENSIONS")
validate_concept_file_size = MaxFileSizeValidator("MAX_CONCEPT_FILE_MB")

# Leading bytes of each allowed concept-file format: PDF, Office Open XML (zip) and legacy Office (OLE2).
CONCEPT_FILE_SIGNATURES = {
    "pdf": (b"%PDF-",),
    "docx": (b"PK\x03\x04",),
    "pptx": (b"PK\x03\x04",),
    "doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "ppt": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
}


def validate_concept_file_content(value):
    """Reject files whose contents do not match their PDF, Word or PowerPoint extension."""
    signatures = CONCEPT_FILE_SIGNATURES.get(_extension(value.name))
    if signatures is None:
        return  # The extension validator reports unsupported types.
    position = value.tell() if hasattr(value, "tell") else 0
    value.seek(0)
    head = value.read(8)
    value.seek(position)
    if not head.startswith(signatures):
        raise ValidationError(
            "This file does not look like a valid PDF, Word or PowerPoint document.", code="invalid_content",
        )


IMAGE_VALIDATORS = [validate_image_ext, validate_image_size]
PRODUCT_FILE_VALIDATORS = [validate_product_file_ext, validate_product_file_size]
DOCUMENT_VALIDATORS = [validate_document_ext, validate_product_file_size]
CONCEPT_FILE_VALIDATORS = [validate_concept_file_ext, validate_concept_file_size, validate_concept_file_content]


@deconstructible
class UniqueUploadPath:
    """upload_to callable: stores files as <folder>/<yyyy>/<mm>/<uuid>.<ext>.

    The original filename is never used on disk, which removes path tricks and
    collisions. Human-friendly names are restored in Content-Disposition on download.
    """

    def __init__(self, folder):
        self.folder = folder

    def __call__(self, instance, filename):
        from django.utils import timezone

        ext = _extension(filename)
        now = timezone.now()
        name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
        return f"{self.folder}/{now:%Y}/{now:%m}/{name}"

    def __eq__(self, other):
        return isinstance(other, UniqueUploadPath) and self.folder == other.folder
