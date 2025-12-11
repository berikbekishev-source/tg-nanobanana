from django.db import migrations


def reorder_video_models(apps, schema_editor):
    """Упорядочивает модели видео: Kling рядом, Midjourney внизу."""
    AIModel = apps.get_model("botapp", "AIModel")

    # Все 3 Kling рядом (order 35, 36, 37)
    AIModel.objects.filter(slug="kling-v2-5-turbo").update(order=35)
    AIModel.objects.filter(slug="kling-v2-6").update(order=36)
    AIModel.objects.filter(slug="kling-v2-1").update(order=37)

    # Midjourney video в самый низ (order 80)
    AIModel.objects.filter(slug="midjourney-video").update(order=80)


def reverse_reorder(apps, schema_editor):
    """Возвращает старый порядок."""
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="kling-v2-5-turbo").update(order=35)
    AIModel.objects.filter(slug="kling-v2-6").update(order=59)
    AIModel.objects.filter(slug="kling-v2-1").update(order=61)
    AIModel.objects.filter(slug="midjourney-video").update(order=36)


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0051_add_kling_v21_models"),
    ]

    operations = [
        migrations.RunPython(reorder_video_models, reverse_reorder),
    ]
