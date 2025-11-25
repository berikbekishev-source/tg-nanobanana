from decimal import Decimal

from django.db import migrations


def forward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="nano-banana-pro").update(base_cost_usd=Decimal("0.01"))


def backward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    # Возвращаем прежнее значение на 0.02 USD как более безопасный откат, если понадобилось.
    AIModel.objects.filter(slug="nano-banana-pro").update(base_cost_usd=Decimal("0.02"))


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0033_normalize_nano_banana_models"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
