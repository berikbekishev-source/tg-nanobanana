"""Обновление цен для моделей Nano Banana."""
from decimal import Decimal
from django.db import migrations


def forward(apps, schema_editor):
    """Устанавливаем новые цены для nano-banana и nano-banana-pro."""
    AIModel = apps.get_model("botapp", "AIModel")

    # nano-banana: 0.02 USD
    AIModel.objects.filter(slug="nano-banana").update(base_cost_usd=Decimal("0.02"))

    # nano-banana-pro: 0.15 USD
    AIModel.objects.filter(slug="nano-banana-pro").update(base_cost_usd=Decimal("0.15"))


def backward(apps, schema_editor):
    """Откат к предыдущим ценам."""
    AIModel = apps.get_model("botapp", "AIModel")

    # Возвращаем предыдущие значения
    AIModel.objects.filter(slug="nano-banana").update(base_cost_usd=Decimal("0.01"))
    AIModel.objects.filter(slug="nano-banana-pro").update(base_cost_usd=Decimal("0.01"))


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0056_add_kling_o1_model"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
