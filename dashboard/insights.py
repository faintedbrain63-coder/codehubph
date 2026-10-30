"""Visitor locations and storage usage for the dashboard overview."""

import os
import shutil

from django.conf import settings
from django.core.cache import cache

from core.models import VisitorCounter, VisitorCountry

TOP_COUNTRIES = 8
STORAGE_CACHE_KEY = "dashboard.storage_usage"
STORAGE_CACHE_SECONDS = 600  # walking the upload folders is slow on large sites
STORAGE_WARNING_PERCENT = 90


def visitor_locations():
    total = VisitorCounter.current()
    countries = list(VisitorCountry.objects.values_list("code", "visitors"))
    rows = [{"code": code, "visitors": visitors} for code, visitors in countries[:TOP_COUNTRIES]]
    other = sum(visitors for _, visitors in countries[TOP_COUNTRIES:])
    if other:
        rows.append({"code": "", "label": "Other countries", "visitors": other})
    # Visitors counted before location tracking, or without a Cloudflare country.
    unknown = max(total - sum(visitors for _, visitors in countries), 0)
    if unknown:
        rows.append({"code": "", "label": "Unknown", "visitors": unknown})
    peak = max((row["visitors"] for row in rows), default=0)
    for row in rows:
        row["percent"] = round(row["visitors"] * 100 / total, 1) if total else 0
        row["width"] = round(row["visitors"] * 100 / peak, 1) if peak else 0
    return {"total": total, "countries": len(countries), "rows": rows}


def folder_size(path):
    size = 0
    try:
        entries = list(os.scandir(path))
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                size += folder_size(entry.path)
            elif entry.is_file(follow_symlinks=False):
                size += entry.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    return size


def storage_usage():
    usage = cache.get(STORAGE_CACHE_KEY)
    if usage is None:
        usage = measure_storage()
        cache.set(STORAGE_CACHE_KEY, usage, STORAGE_CACHE_SECONDS)
    return usage


def measure_storage():
    try:
        disk = shutil.disk_usage(settings.MEDIA_ROOT if os.path.isdir(settings.MEDIA_ROOT) else settings.BASE_DIR)
    except OSError:
        return None
    public = folder_size(settings.MEDIA_ROOT)
    private = folder_size(settings.PRIVATE_MEDIA_ROOT)
    # Both folders may sit on another disk; never let the "other" share go negative.
    other = max(disk.used - public - private, 0)
    segments = [
        {"key": "public", "label": "Public images", "bytes": public},
        {"key": "private", "label": "Private files", "bytes": private},
        {"key": "other", "label": "System and other data", "bytes": other},
        {"key": "free", "label": "Free space", "bytes": disk.free},
    ]
    for segment in segments:
        segment["percent"] = round(segment["bytes"] * 100 / disk.total, 1) if disk.total else 0
    used_percent = round(disk.used * 100 / disk.total, 1) if disk.total else 0
    return {
        "total": disk.total,
        "used": disk.used,
        "free": disk.free,
        "used_percent": used_percent,
        "is_low": used_percent >= STORAGE_WARNING_PERCENT,
        "segments": segments,
    }
