from django.db import migrations


def forward(apps, schema_editor):
    """Обновляем модель nano-banana для работы через публичный Gemini API."""
    AIModel = apps.get_model("botapp", "AIModel")

    AIModel.objects.filter(slug="nano-banana").update(
        api_model_name="gemini-2.5-flash-image",
        provider="gemini",
        is_active=True,
        supports_image_input=True,
    )


def backward(apps, schema_editor):
    """Откатываем изменения модели nano-banana."""
    AIModel = apps.get_model("botapp", "AIModel")

    AIModel.objects.filter(slug="nano-banana").update(
        is_active=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0048_fix_runway_aleph_cost_unit"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
