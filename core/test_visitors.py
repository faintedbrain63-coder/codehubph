from django.test import TestCase
from django.urls import reverse

from core.models import VisitorCounter
from core.visitors import COOKIE_NAME

BROWSER = {"HTTP_USER_AGENT": "Mozilla/5.0 (Windows NT 10.0) Chrome/130", "HTTP_ACCEPT": "text/html,*/*"}


class VisitorCounterTests(TestCase):
    def visit(self, client=None, **meta):
        return (client or self.client).get(reverse("core:home"), **{**BROWSER, **meta})

    def test_counts_each_browser_once(self):
        response = self.visit()
        self.assertIn(COOKIE_NAME, response.cookies)
        self.visit()
        self.assertEqual(VisitorCounter.current(), 1)
        self.visit(client=self.client_class())
        self.assertEqual(VisitorCounter.current(), 2)

    def test_skips_bots_and_non_html_requests(self):
        self.visit(HTTP_USER_AGENT="Googlebot/2.1")
        self.visit(HTTP_USER_AGENT="")
        self.visit(HTTP_ACCEPT="application/json")
        self.assertEqual(VisitorCounter.current(), 0)

    def test_navbar_shows_count(self):
        VisitorCounter.objects.create(pk=1, total=1233)
        self.visit()
        response = self.visit()
        self.assertContains(response, "nav-visitors")
        self.assertContains(response, "1,234")
