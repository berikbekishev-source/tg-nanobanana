"""Активирует все модели Kling."""
from django.db import migrations


KLING_SLUGS = [
    "kling-v2-5-turbo",
    "kling-v2-5-turbo-pro",
    "kling-v2-6",
    "kling-v2-6-pro-with-sound",
    "kling-v2-1",
    "kling-v2-1-pro",
    "kling-v2-1-master",
]


def activate_all_kling_models(apps, schema_editor):
    """Активирует все модели Kling."""
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug__in=KLING_SLUGS).update(is_active=True)


def noop(apps, schema_editor):
    """Ничего не делает - модели остаются активными."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0054_activate_nano_banana"),
    ]

    operations = [
        migrations.RunPython(activate_all_kling_models, noop),
    ]
