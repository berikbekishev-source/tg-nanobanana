from django.db import migrations


def forward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")

    # Отключаем старую Nano Banana (Gemini 2.5 Flash)
    AIModel.objects.filter(slug="nano-banana").update(is_active=False)

    # Приводим Nano Banana Pro к актуальной модели Gemini 3 Pro Preview
    AIModel.objects.filter(slug="nano-banana-pro").update(
        api_model_name="publishers/google/models/gemini-3-pro-image-preview",
        provider="gemini_vertex",
        is_active=True,
        supports_image_input=True,
    )


def backward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="nano-banana").update(is_active=True)
    AIModel.objects.filter(slug="nano-banana-pro").update(
        api_model_name="publishers/google/models/gemini-3.0-pro-image-preview",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0036_add_int1000_promocode"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
