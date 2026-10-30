"""Versioned legal documents. Retain published bodies and identifiers.

For revisions, add an archived template/entry and update CURRENT_VERSIONS.
Changing the identified operator or privacy contact also requires a new version.
"""

from datetime import date

from django.urls import reverse

CURRENT_VERSIONS = {"privacy": "2026-10-24", "license": "2026-10-24"}
DOCUMENTS = {
    "privacy": {
        "2026-10-24": {
            "title": "Privacy Policy",
            "effective_date": date(2026, 10, 24),
            "template": "core/legal/privacy_2026_10_24.html",
        },
        "2026-10-23": {
            "title": "Privacy Policy",
            "effective_date": date(2026, 10, 23),
            "template": "core/legal/privacy_2026_10_23.html",
        },
    },
    "license": {
        "2026-10-24": {
            "title": "Custom Development, Software License Agreement and Terms of Service",
            "effective_date": date(2026, 10, 24),
            "template": "core/legal/license_2026_10_24.html",
        },
        "2026-10-23": {
            "title": "Software License Agreement and Terms of Service",
            "effective_date": date(2026, 10, 23),
            "template": "core/legal/license_2026_10_23.html",
        },
    },
}


def get_document(kind, version=None):
    version = CURRENT_VERSIONS[kind] if version is None else version
    return {**DOCUMENTS[kind][version], "kind": kind, "version": version,
            "url": reverse("core:legal_document", args=[kind, version])}
