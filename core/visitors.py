"""Unique-visitor counting for the navbar badge and the dashboard's visitor locations.

A browser is counted once, the first time it loads an HTML page without the visitor cookie.
The cookie holds only a marker, no personal data. Obvious crawlers are skipped.
The country comes from Cloudflare's CF-IPCountry header; no IP address is stored.
"""

from django.conf import settings

from core.models import VisitorCounter, VisitorCountry

COOKIE_NAME = "chp_visitor"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2  # two years
SKIPPED_PREFIXES = ("/static/", "/media/", "/admin/", "/manage/")
BOT_MARKERS = ("bot", "crawl", "spider", "slurp", "preview", "monitor", "curl", "wget", "python-requests", "headless")


def visitor_country(request):
    """Two-letter country code from Cloudflare, or "" when unknown.

    The header is only trusted behind the proxy (BEHIND_PROXY), where Cloudflare sets it on every request.
    XX means Cloudflare could not tell; T1 is Tor.
    """
    if not settings.BEHIND_PROXY:
        return ""
    code = request.META.get("HTTP_CF_IPCOUNTRY", "").strip().upper()
    if len(code) != 2 or not code.isalpha() or code == "XX":
        return ""
    return code


def is_countable(request):
    if request.method != "GET" or COOKIE_NAME in request.COOKIES:
        return False
    if request.path.startswith(SKIPPED_PREFIXES):
        return False
    if "text/html" not in request.META.get("HTTP_ACCEPT", ""):
        return False
    agent = request.META.get("HTTP_USER_AGENT", "").lower()
    return bool(agent) and not any(marker in agent for marker in BOT_MARKERS)


class VisitorCounterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        counted = is_countable(request)
        if counted:
            VisitorCounter.increment()
            if country := visitor_country(request):
                VisitorCountry.increment(country)
        response = self.get_response(request)
        if counted:
            response.set_cookie(COOKIE_NAME, "1", max_age=COOKIE_MAX_AGE, secure=request.is_secure(), httponly=True, samesite="Lax")
        return response
