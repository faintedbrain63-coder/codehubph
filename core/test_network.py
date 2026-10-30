from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from core.network import client_ip
from core.testing import PASSWORD, BaseTestCase


class ClientIpTests(SimpleTestCase):
    def request(self, **meta):
        return RequestFactory().get("/", REMOTE_ADDR="127.0.0.1", **meta)

    @override_settings(BEHIND_PROXY=False)
    def test_header_ignored_unless_behind_proxy(self):
        self.assertEqual(client_ip(self.request(HTTP_X_REAL_IP="203.0.113.9")), "127.0.0.1")

    @override_settings(BEHIND_PROXY=True)
    def test_real_ip_from_proxy(self):
        self.assertEqual(client_ip(self.request(HTTP_X_REAL_IP="203.0.113.9")), "203.0.113.9")
        self.assertEqual(client_ip(self.request(HTTP_X_REAL_IP="2001:db8::1")), "2001:db8::1")

    @override_settings(BEHIND_PROXY=True)
    def test_malformed_header_falls_back(self):
        self.assertEqual(client_ip(self.request(HTTP_X_REAL_IP="evil, 1.2.3.4")), "127.0.0.1")
        self.assertEqual(client_ip(self.request()), "127.0.0.1")


@override_settings(BEHIND_PROXY=True)
class ProxyAwareLimitsTests(BaseTestCase):
    def test_contact_limit_is_per_visitor_behind_proxy(self):
        def send(ip, n):
            return self.client.post(reverse("core:contact"), {
                "name": "Visitor", "email": "v@example.com", "subject": f"Q{n}",
                "message": "Do you offer installation support for this system?",
            }, REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP=ip)
        for n in range(5):
            send("203.0.113.1", n)
        self.assertEqual(send("203.0.113.1", 6).status_code, 429)
        self.assertEqual(send("198.51.100.2", 7).status_code, 302)  # another visitor is unaffected

    def test_login_lockout_is_per_visitor_behind_proxy(self):
        user = self.make_user("target")
        url = reverse("accounts:login")
        for _ in range(5):
            self.client.post(url, {"email": user.email, "password": "wrong"}, REMOTE_ADDR="127.0.0.1",
                             HTTP_X_REAL_IP="203.0.113.1")
        attacker = self.client.post(url, {"email": user.email, "password": "wrong"}, REMOTE_ADDR="127.0.0.1",
                                    HTTP_X_REAL_IP="203.0.113.1")
        self.assertEqual(attacker.status_code, 429)
        owner = self.client.post(url, {"email": user.email, "password": PASSWORD}, REMOTE_ADDR="127.0.0.1",
                                 HTTP_X_REAL_IP="198.51.100.2")
        self.assertEqual(owner.status_code, 302)  # the real owner, from another IP, can still sign in
