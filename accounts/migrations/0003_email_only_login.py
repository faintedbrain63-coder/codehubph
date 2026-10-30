from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import migrations


def prepare_email_login(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    users = list(User.objects.using(schema_editor.connection.alias).all())
    seen = set()
    for user in users:
        email = (user.email or "").strip().lower()
        try:
            validate_email(email)
        except ValidationError as exc:
            raise RuntimeError(f"Account {user.pk} needs a valid email before removing usernames.") from exc
        if email in seen:
            raise RuntimeError("Accounts have duplicate normalized emails. Resolve them before removing usernames.")
        seen.add(email)
        user.email = email
    User.objects.using(schema_editor.connection.alias).bulk_update(users, ["email"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_unique_username_ci")]

    operations = [
        migrations.RunPython(prepare_email_login, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="user", name="unique_user_username_ci"),
        migrations.RemoveField(model_name="user", name="username"),
    ]
