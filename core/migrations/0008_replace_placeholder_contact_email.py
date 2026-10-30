from django.db import migrations, models


def replace_placeholder_contact_email(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.using(schema_editor.connection.alias).filter(
        contact_email="support@example.com",
    ).update(contact_email="ragus.christian1989@gmail.com")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_portfolio_presentation_and_case_studies"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="contact_email",
            field=models.EmailField(default="ragus.christian1989@gmail.com", max_length=254),
        ),
        migrations.RunPython(replace_placeholder_contact_email, migrations.RunPython.noop),
    ]
