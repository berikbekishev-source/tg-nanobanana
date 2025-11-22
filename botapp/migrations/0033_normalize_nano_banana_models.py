from django.db import migrations


def forward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="nano-banana").update(
        api_model_name="publishers/google/models/gemini-2.5-flash-image"
    )
    AIModel.objects.filter(slug="nano-banana-pro").update(
        api_model_name="publishers/google/models/gemini-3.0-pro-image-preview"
    )


def backward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="nano-banana").update(
        api_model_name="publishers/google/models/gemini-2.5-flash-image-preview"
    )
    AIModel.objects.filter(slug="nano-banana-pro").update(
        api_model_name="publishers/google/models/gemini-3-pro-image-preview"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0032_update_nano_banana_pro_max_images"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
