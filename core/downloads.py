"""Streams private files to users who already passed a permission check."""

import mimetypes
import os

from django.http import FileResponse, Http404
from django.utils.text import slugify


def serve_private_file(field_file, download_name_base):
    """Return a FileResponse for a private FileField with a safe, readable filename."""
    if not field_file:
        raise Http404("File not available.")
    try:
        handle = field_file.storage.open(field_file.name, "rb")
    except FileNotFoundError as exc:
        raise Http404("File not found on the server.") from exc

    ext = os.path.splitext(field_file.name)[1].lower()
    filename = f"{slugify(download_name_base) or 'download'}{ext}"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = FileResponse(handle, as_attachment=True, filename=filename, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def serve_private_image_inline(field_file):
    """Inline display of a private image (e.g. payment proof) for staff."""
    if not field_file:
        raise Http404("File not available.")
    try:
        handle = field_file.storage.open(field_file.name, "rb")
    except FileNotFoundError as exc:
        raise Http404("File not found on the server.") from exc
    content_type = mimetypes.guess_type(field_file.name)[0] or "application/octet-stream"
    if not content_type.startswith("image/"):
        content_type = "application/octet-stream"
    response = FileResponse(handle, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
