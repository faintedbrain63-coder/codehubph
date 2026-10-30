from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="is_featured",
            field=models.BooleanField(
                "featured", default=False,
                help_text="Featured products show first in the catalog's newest sort.",
            ),
        ),
    ]
