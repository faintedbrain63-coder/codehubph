"""JSON endpoints for chunked staff uploads (see core/chunked_uploads.py and static/js/chunked-upload.js).

POST   /manage/uploads/               {"target", "filename", "size"} -> start an upload
GET    /manage/uploads/<id>/          -> progress, used to resume after a dropped connection
POST   /manage/uploads/<id>/          raw bytes + "Content-Range: bytes start-end/total" -> append a chunk
DELETE /manage/uploads/<id>/          -> abandon the upload
"""

import json
import os
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from core.chunked_uploads import chunk_bytes, expire_stale_uploads, validate_upload
from core.models import ChunkedUpload
from dashboard.decorators import staff_required

CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
READ_BLOCK = 64 * 1024


def _state(upload, status=200):
    return JsonResponse(
        {"id": str(upload.pk), "size": upload.size, "received": upload.received,
         "complete": upload.is_complete, "chunk_size": chunk_bytes()},
        status=status,
    )


def _error(message, status=400, **extra):
    return JsonResponse({"error": message, **extra}, status=status)


@staff_required
@require_POST
def upload_start(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return _error("Invalid request.")
    if not isinstance(data, dict):
        return _error("Invalid request.")
    target, filename, size = data.get("target"), data.get("filename"), data.get("size")
    if not isinstance(target, str) or not isinstance(filename, str) or not isinstance(size, int) or isinstance(size, bool):
        return _error("Supply the target field, file name and size.")
    filename = os.path.basename(filename.replace("\\", "/")).strip()[:200]
    if not filename or size <= 0:
        return _error("Choose a non-empty file.")
    try:
        validate_upload(target, filename, size)
    except ValidationError as exc:
        return _error(" ".join(exc.messages))

    expire_stale_uploads()
    active = ChunkedUpload.objects.filter(user=request.user, completed_at__isnull=True).count()
    if active >= settings.UPLOAD_MAX_ACTIVE_SESSIONS:
        return _error("Too many unfinished uploads. Finish or cancel one, then try again.", status=429)

    upload = ChunkedUpload.objects.create(user=request.user, target=target, filename=filename, size=size)
    os.makedirs(os.path.dirname(upload.part_path), exist_ok=True)
    with open(upload.part_path, "wb"):
        pass
    return _state(upload, status=201)


@staff_required
@require_http_methods(["GET", "POST", "DELETE"])
def upload_chunk(request, upload_id):
    if request.method == "GET":
        return _state(get_object_or_404(ChunkedUpload, pk=upload_id, user=request.user))
    if request.method == "DELETE":
        get_object_or_404(ChunkedUpload, pk=upload_id, user=request.user).discard()
        return JsonResponse({"deleted": True})

    match = CONTENT_RANGE.match(request.headers.get("Content-Range", ""))
    if not match:
        return _error("Missing or invalid Content-Range header.")
    start, end, total = (int(g) for g in match.groups())
    length = end - start + 1
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = -1
    if length <= 0 or length > chunk_bytes() or declared != length:
        return _error(f"Each chunk must be 1 byte to {chunk_bytes()} bytes and match Content-Length.")

    # The row lock serialises chunks for one upload (e.g. a retry racing the original request).
    with transaction.atomic():
        upload = get_object_or_404(ChunkedUpload.objects.select_for_update(), pk=upload_id, user=request.user)
        if total != upload.size or end >= upload.size:
            return _error("The chunk does not fit this upload.")
        if end < upload.received:
            return _state(upload)  # already stored: a retried chunk is acknowledged without rewriting
        if start != upload.received:
            return _error("Unexpected chunk offset.", status=409, received=upload.received)
        if upload.is_complete or not os.path.exists(upload.part_path):
            return _error("This upload is no longer available. Start again.", status=410)

        written = 0
        with open(upload.part_path, "r+b") as part:
            part.seek(start)
            part.truncate()
            while written < length:
                block = request.read(min(READ_BLOCK, length - written))
                if not block:
                    break
                part.write(block)
                written += len(block)
            if written != length:
                part.truncate(start)  # drop the partial chunk so the client can resend it
        if written != length:
            return _error("The chunk was incomplete. Retrying.", status=400, received=upload.received)

        upload.received = end + 1
        if upload.received == upload.size:
            upload.completed_at = timezone.now()
        upload.save(update_fields=["received", "completed_at", "updated_at"])
    return _state(upload)
