"""Активирует модель kling-v2-1-master."""
from django.db import migrations


def activate_kling_v21_master(apps, schema_editor):
    """Активирует модель kling-v2-1-master."""
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="kling-v2-1-master").update(is_active=True)


def deactivate_kling_v21_master(apps, schema_editor):
    """Деактивирует модель kling-v2-1-master."""
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="kling-v2-1-master").update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0054_activate_nano_banana"),
    ]

    operations = [
        migrations.RunPython(activate_kling_v21_master, deactivate_kling_v21_master),
    ]
