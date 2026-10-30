from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_email_only_login")]

    operations = [
        migrations.AddField(
            model_name="user", name="legal_accepted_at",
            field=models.DateTimeField(blank=True, null=True, editable=False),
        ),
        migrations.AddField(
            model_name="user", name="privacy_policy_version",
            field=models.CharField(blank=True, max_length=32, editable=False),
        ),
        migrations.AddField(
            model_name="user", name="license_agreement_version",
            field=models.CharField(blank=True, max_length=32, editable=False),
        ),
    ]
