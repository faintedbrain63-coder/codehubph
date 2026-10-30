"""Unique-visitor counting for the navbar badge.

A browser is counted once, the first time it loads an HTML page without the visitor cookie.
The cookie holds only a marker, no personal data. Obvious crawlers are skipped.
"""

from core.models import VisitorCounter

COOKIE_NAME = "chp_visitor"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2  # two years
SKIPPED_PREFIXES = ("/static/", "/media/", "/admin/", "/manage/")
BOT_MARKERS = ("bot", "crawl", "spider", "slurp", "preview", "monitor", "curl", "wget", "python-requests", "headless")


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
        response = self.get_response(request)
        if counted:
            response.set_cookie(COOKIE_NAME, "1", max_age=COOKIE_MAX_AGE, secure=request.is_secure(), httponly=True, samesite="Lax")
        return response
