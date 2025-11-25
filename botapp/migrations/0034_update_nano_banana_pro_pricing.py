from decimal import Decimal

from django.db import migrations


def forward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="nano-banana-pro").update(
        cost_unit="image",
        base_cost_usd=Decimal("0.01"),
        unit_cost_usd=Decimal("0.01"),
    )


def backward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="nano-banana-pro").update(
        cost_unit="generation",
        base_cost_usd=Decimal("0.0000"),
        unit_cost_usd=Decimal("0.0000"),
        price=Decimal("2.00"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0033_normalize_nano_banana_models"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
