from django.db import migrations


def forward(apps, schema_editor):
    """Активируем модель nano-banana и устанавливаем корректные параметры."""
    AIModel = apps.get_model("botapp", "AIModel")

    AIModel.objects.filter(slug="nano-banana").update(
        display_name="🍌 Nano Banana",
        api_model_name="gemini-2.5-flash-image",
        provider="gemini",
        is_active=True,
        supports_image_input=True,
        max_input_images=5,
    )


def backward(apps, schema_editor):
    """Деактивируем модель nano-banana."""
    AIModel = apps.get_model("botapp", "AIModel")

    AIModel.objects.filter(slug="nano-banana").update(
        is_active=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0053_update_nano_banana_model"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
