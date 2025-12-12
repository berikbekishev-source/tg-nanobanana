"""Добавление промокода INT200 на 200 токенов."""
from decimal import Decimal
from django.db import migrations
from django.utils import timezone
from datetime import datetime


def forward(apps, schema_editor):
    """Создаём промокод INT200."""
    Promocode = apps.get_model("botapp", "Promocode")

    Promocode.objects.create(
        code="INT200",
        description="Разовый бонус 200 токенов",
        is_percentage=False,
        value=Decimal("200.00"),
        min_deposit=Decimal("0.00"),
        max_uses=None,  # Без ограничения общего количества
        max_uses_per_user=1,  # Разовое использование на пользователя
        current_uses=0,
        valid_from=timezone.now(),
        valid_until=datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        is_active=True,
    )


def backward(apps, schema_editor):
    """Удаляем промокод INT200."""
    Promocode = apps.get_model("botapp", "Promocode")
    Promocode.objects.filter(code="INT200").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0057_update_nano_banana_pricing"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
