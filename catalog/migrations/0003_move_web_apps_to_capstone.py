from django.db import migrations, models


def move_web_apps(apps, schema_editor):
    """Web apps are now offered as capstone projects.

    Each existing web app product gets a *draft* capstone offering (field "web") with the same text, price,
    thumbnail and source file, for staff to review and publish. The product itself is unpublished and kept
    so existing orders, receipts and customer downloads keep working.
    """
    Product = apps.get_model("catalog", "Product")
    CapstoneProject = apps.get_model("capstone", "CapstoneProject")
    for product in Product.objects.filter(category="web_app"):
        if not CapstoneProject.objects.filter(title=product.name[:180]).exists():
            base = product.slug[:190] or "web-app"
            slug, n = base, 2
            while CapstoneProject.objects.filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            CapstoneProject.objects.create(
                title=product.name[:180], slug=slug, field="web", status="draft",
                short_description=product.short_description, description=product.description,
                features=product.features, tech_stack=product.tech_stack, suggested_price=product.price,
                thumbnail=product.thumbnail.name, source_code=product.file.name,
            )
        product.category = "software"
        product.status = "draft"
        product.save(update_fields=["category", "status"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_featured_catalog_help"),
        ("capstone", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(move_web_apps, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="product", name="category",
            field=models.CharField(choices=[("software", "Software"), ("mobile_app", "Mobile App")], default="software", max_length=20),
        ),
    ]
