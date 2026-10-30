from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def skip_for_existing_users(apps, schema_editor):
    # Accounts that have already signed in (and staff) are not first-time users.
    User = apps.get_model("accounts", "User")
    User.objects.filter(Q(last_login__isnull=False) | Q(is_staff=True)).update(onboarding_completed_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_registration_legal_acceptance")]

    operations = [
        migrations.AddField(
            model_name="user", name="onboarding_completed_at",
            field=models.DateTimeField(blank=True, null=True, editable=False),
        ),
        migrations.RunPython(skip_for_existing_users, migrations.RunPython.noop),
    ]
