from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial")]

    operations = [
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                fields=("capture_id",), condition=~models.Q(capture_id=""), name="unique_gateway_capture",
            ),
        ),
    ]
