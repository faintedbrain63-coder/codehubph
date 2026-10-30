from django.conf import settings
from django.db import migrations


LEGACY_NAME = "FaintedBrain Digital Store"


def rename_store(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    rows = SiteSettings.objects.using(schema_editor.connection.alias)
    rows.filter(site_name__iexact=LEGACY_NAME).update(site_name="CodehubPh")
    # Existing installations can still have the previous name in their environment.
    if settings.SITE_NAME.strip().casefold() == LEGACY_NAME.casefold():
        rows.get_or_create(pk=1, defaults={"site_name": "CodehubPh"})
        rows.filter(pk=1, site_name="").update(site_name="CodehubPh")


class Migration(migrations.Migration):
    dependencies = [("core", "0003_chunked_upload")]

    operations = [migrations.RunPython(rename_store, migrations.RunPython.noop)]
