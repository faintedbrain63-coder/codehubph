from django.urls import reverse

from core.testing import PASSWORD, BaseTestCase


class AdminWorkspaceRoutingTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user("admin", staff=True)
        self.customer = self.make_user("shopper")

    def test_staff_login_opens_console_with_sidebar(self):
        response = self.client.post(reverse("accounts:login"), {
            "email": "ADMIN@EXAMPLE.COM", "password": PASSWORD,
        }, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse("dashboard:home"), 302)])
        self.assertContains(response, 'id="manageSidebar"')
        self.assertContains(response, "All digital products")
        self.assertContains(response, "Open admin menu")

    def test_customer_login_keeps_customer_dashboard(self):
        response = self.client.post(reverse("accounts:login"), {
            "email": self.customer.email, "password": PASSWORD,
        }, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse("accounts:dashboard"), 302)])
        self.assertTemplateUsed(response, "accounts/dashboard.html")
        self.assertNotContains(response, 'id="manageSidebar"')

    def test_staff_account_bookmark_redirects_to_console(self):
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse("accounts:dashboard")), reverse("dashboard:home"))

    def test_already_authenticated_staff_login_redirects_to_console(self):
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse("accounts:login")), reverse("dashboard:home"))

    def test_staff_customer_dashboard_next_cannot_hide_console(self):
        response = self.client.post(reverse("accounts:login"), {
            "email": self.staff.email, "password": PASSWORD, "next": reverse("accounts:dashboard"),
        }, follow=True)
        self.assertEqual(response.redirect_chain, [
            (reverse("accounts:dashboard"), 302), (reverse("dashboard:home"), 302),
        ])
        self.assertContains(response, 'id="manageSidebar"')

    def test_staff_can_follow_a_safe_explicit_next(self):
        target = reverse("dashboard:product_list") + "?status=draft"
        response = self.client.post(reverse("accounts:login"), {
            "email": self.staff.email, "password": PASSWORD, "next": target,
        })
        self.assertRedirects(response, target)

    def test_external_next_cannot_override_staff_destination(self):
        response = self.client.post(reverse("accounts:login"), {
            "email": self.staff.email, "password": PASSWORD, "next": "https://evil.example/phishing/",
        })
        self.assertRedirects(response, reverse("dashboard:home"))

    def test_staff_can_still_view_personal_purchases(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("accounts:purchases"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/dashboard.html")
        self.assertContains(response, reverse("accounts:purchases"))
        self.assertContains(response, "Admin console")
        self.assertContains(response, "My projects")

    def test_admin_email_alone_never_grants_admin_permissions(self):
        self.staff.is_staff = False
        self.staff.save(update_fields=["is_staff"])
        response = self.client.post(reverse("accounts:login"), {
            "email": "admin@example.com", "password": PASSWORD,
        })
        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 403)

    def test_personal_purchases_require_login(self):
        response = self.client.get(reverse("accounts:purchases"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])
