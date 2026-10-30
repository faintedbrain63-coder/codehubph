"""Verify that removing the old identifier preserves accounts and their relationships."""

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from core.testing import PASSWORD
from orders.models import Order


class EmailOnlyMigrationTests(TransactionTestCase):
    def test_existing_account_and_orders_survive_username_removal(self):
        before = [("accounts", "0002_unique_username_ci")]
        after = MigrationExecutor(connection).loader.graph.leaf_nodes("accounts")
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(after))
        OldUser = executor.loader.project_state(before).apps.get_model("accounts", "User")
        encoded_password = make_password(PASSWORD)
        old = OldUser.objects.create(
            username="legacy-handle", email=" Legacy@Example.COM ", password=encoded_password,
            first_name="Legacy", is_staff=True, is_superuser=True,
        )
        order = Order.objects.create(user_id=old.pk, total="100.00")

        MigrationExecutor(connection).migrate(after)

        user = get_user_model().objects.get(pk=old.pk)
        self.assertEqual(user.email, "legacy@example.com")
        self.assertEqual(user.password, encoded_password)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertIsNone(user.legal_accepted_at)
        self.assertEqual(user.privacy_policy_version, "")
        self.assertEqual(user.license_agreement_version, "")
        self.assertEqual(Order.objects.get(pk=order.pk).user_id, user.pk)
        with connection.cursor() as cursor:
            columns = {column.name for column in connection.introspection.get_table_description(cursor, user._meta.db_table)}
        self.assertNotIn("username", columns)
