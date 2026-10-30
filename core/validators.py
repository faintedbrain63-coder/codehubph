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

IMAGE_VALIDATORS = [validate_image_ext, validate_image_size]
PRODUCT_FILE_VALIDATORS = [validate_product_file_ext, validate_product_file_size]
DOCUMENT_VALIDATORS = [validate_document_ext, validate_product_file_size]


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
