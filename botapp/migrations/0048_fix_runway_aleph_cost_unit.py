# Миграция для исправления cost_unit модели runway_aleph
# Модель должна использовать "generation" (фиксированная цена за генерацию),
# а не "second" (цена за секунду видео)

from django.db import migrations


def fix_runway_aleph_cost_unit(apps, schema_editor):
    """Устанавливает cost_unit='generation' для модели runway_aleph."""
    AIModel = apps.get_model("botapp", "AIModel")

    AIModel.objects.filter(slug="runway_aleph").update(cost_unit="generation")


def revert_runway_aleph_cost_unit(apps, schema_editor):
    """Откат: возвращает cost_unit='second' для модели runway_aleph."""
    AIModel = apps.get_model("botapp", "AIModel")

    AIModel.objects.filter(slug="runway_aleph").update(cost_unit="second")


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0047_update_nano_banana_pro_cost"),
    ]

    operations = [
        migrations.RunPython(fix_runway_aleph_cost_unit, revert_runway_aleph_cost_unit),
    ]
